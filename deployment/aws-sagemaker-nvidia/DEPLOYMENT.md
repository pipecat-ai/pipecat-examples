# Deploying NVIDIA NIM Containers to AWS SageMaker

This guide walks you through deploying NVIDIA NIM containers (Magpie TTS and Nemotron ASR Streaming) to SageMaker endpoints. Every step has an automation script — you should not need to type raw AWS CLI commands.

---

## Overview

### Setup (run once, or when updating the NIM version / wrapper)
```
create_iam.sh       → IAM role + deployer user (requires AWS admin credentials)
pull_nim.sh         → pull a NIM container from NVIDIA NGC
build_wrapper.sh    → build the SageMaker wrapper on top of the local NIM image
push_to_ecr.sh      → push the wrapper image to AWS ECR
```

### Deployment
```
create_model.sh     → register the wrapper image as a SageMaker Model
create_endpoint.sh  → deploy the endpoint (waits for InService)
```

### Observability
```
logs_endpoint.sh    → stream live CloudWatch logs from the endpoint container
list_endpoints.sh   → show all endpoints and their status
```

### Teardown
```
delete_endpoint.sh  → tear down an endpoint and its config
delete_model.sh     → delete the SageMaker model
```

All scripts that operate on a specific NIM accept it as the first argument (`magpie` or `nemotron-asr`). If omitted, they prompt interactively.

---

## Prerequisites

| Tool | Notes |
|---|---|
| Docker Desktop | Running locally |
| AWS CLI v2 | [Install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| Python 3.10+ | For Pipecat integration |
| AWS admin account | Needed to run the IAM setup script once |
| NVIDIA NGC API key | See Step 2 below |

---

## Environment Setup

### 1. Copy the environment template

```bash
cp env.example .env
```

Fill in values as you go through the steps — the scripts will tell you what's missing.

### 2. Get your NVIDIA NGC API key

1. Go to [build.nvidia.com](https://build.nvidia.com) and create a free NVIDIA developer account.
2. Generate an API key.
3. Add it to `.env`:
   ```
   NGC_API_KEY=nvapi-xxxxxxxxxxxxxxxx
   ```

This key is used both to pull NIM containers from `nvcr.io` and by the NIM container at runtime to download model weights.

### 3. Set your AWS region

```
AWS_REGION=us-west-2
```

---

## Setup

### Step 1 — Create IAM resources

```bash
./scripts/create_iam.sh
```

Run this **once**, as an AWS admin user (your personal `aws configure` credentials — not the deployer credentials, which don't exist yet).

Creates:
- **`magpie-sagemaker-execution-role`** — the IAM role SageMaker assumes when running endpoints. Needs ECR access to pull container images.
- **`magpie-sagemaker-deployer`** — an IAM user with the minimum permissions to push to ECR and manage SageMaker models and endpoints.

At the end, the script prints the deployer access keys. Add them to `.env`:

```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
SAGEMAKER_EXECUTION_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/magpie-sagemaker-execution-role
```

**Deployer permissions** — the `magpie-sagemaker-deployer` user has a single inline policy with only:

| Permission group | Actions |
|---|---|
| ECR — authenticate | `ecr:GetAuthorizationToken` |
| ECR — push image | `CreateRepository`, `DescribeRepositories`, `BatchCheckLayerAvailability`, `BatchGetImage`, `GetDownloadUrlForLayer`, `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload`, `PutImage` |
| SageMaker — deploy | `CreateModel`, `DescribeModel`, `DeleteModel`, `CreateEndpointConfig`, `DescribeEndpointConfig`, `DeleteEndpointConfig`, `CreateEndpoint`, `DescribeEndpoint`, `DeleteEndpoint`, `InvokeEndpoint` |
| IAM — pass role | `iam:PassRole` scoped to the execution role only |

---

### Step 2 — Pull the NIM container

```bash
./scripts/pull_nim.sh magpie             # Magpie TTS
./scripts/pull_nim.sh nemotron-asr       # Nemotron ASR Streaming
```

Always pulls `linux/amd64` — the platform SageMaker GPU instances run on. Important on Apple Silicon, where Docker would otherwise pull the wrong architecture.

Available image tags:
- Magpie TTS: https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/magpie-tts-multilingual/tags
- Nemotron ASR: https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/nemotron-asr-streaming/tags

To pull a specific version, set `MAGPIE_IMAGE_TAG` or `NEMOTRON_ASR_IMAGE_TAG` in `.env`, or pass the tag as the second argument:

```bash
./scripts/pull_nim.sh magpie 1.7.0
./scripts/pull_nim.sh nemotron-asr latest
```

---

### Step 3 — Build the SageMaker wrapper

```bash
./scripts/build_wrapper.sh magpie
./scripts/build_wrapper.sh nemotron-asr
```

Builds the wrapper image locally on top of the NIM image already in your local Docker cache. Does not re-pull from NVIDIA's registry. The script auto-detects the NIM entrypoint via `docker inspect` and bakes it in as a build-arg.

The wrapper is a thin FastAPI application that runs alongside NIM inside the same container and translates SageMaker's expected interface into the NIM's actual API. See the wrapper READMEs for details:
- [sagemaker-wrapper/magpie/README.md](sagemaker-wrapper/magpie/README.md)
- [sagemaker-wrapper/nemotron-asr/README.md](sagemaker-wrapper/nemotron-asr/README.md)

---

### Step 4 — Push the wrapper to ECR

```bash
./scripts/push_to_ecr.sh magpie
./scripts/push_to_ecr.sh nemotron-asr
```

Pushes only the wrapper image — that is the only image SageMaker needs. The first push uploads all layers (NIM + wrapper); subsequent pushes only upload layers that changed (wrapper changes only).

At the end the script prints the ECR image URI — add it to `.env`:

```
# Magpie TTS
ECR_MAGPIE_IMAGE_URI=<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/magpie-tts-sagemaker:latest

# Nemotron ASR
ECR_ASR_IMAGE_URI=<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/nemotron-asr-sagemaker:latest
```

---

## Deployment — Magpie TTS

### Step 1 — Create the SageMaker Model

```bash
./scripts/create_model.sh magpie
```

Registers the wrapper ECR image as a SageMaker Model. Passes runtime environment variables to the container:

| Variable | Purpose |
|---|---|
| `NGC_API_KEY` | NIM downloads model weights using this key |
| `NIM_HTTP_API_PORT` | NIM's internal HTTP port (default `9000`) |
| `NIM_GRPC_API_PORT` | NIM's gRPC port (default `50051`) |

Requires in `.env`: `ECR_MAGPIE_IMAGE_URI`, `SAGEMAKER_EXECUTION_ROLE_ARN`, `SAGEMAKER_MAGPIE_MODEL_NAME`, `NGC_API_KEY`.

### Step 2 — Deploy the Endpoint

```bash
./scripts/create_endpoint.sh magpie
```

Creates the endpoint configuration and deploys the endpoint, then waits for it to become `InService`, polling every 30 seconds. If deployment fails, it prints the failure reason.

Configurable via `.env`:

| Variable | Default | Notes |
|---|---|---|
| `SAGEMAKER_MAGPIE_ENDPOINT_CONFIG_NAME` | `magpie-tts-config` | |
| `SAGEMAKER_MAGPIE_ENDPOINT_NAME` | `magpie-tts-endpoint` | |
| `SAGEMAKER_MAGPIE_INSTANCE_TYPE` | `ml.g6.2xlarge` | See instance table below |
| `SAGEMAKER_MAGPIE_INSTANCE_COUNT` | `1` | |
| `SAGEMAKER_CONTAINER_STARTUP_TIMEOUT` | `3600` | Seconds SageMaker waits for health checks to pass |

**GPU instance options:**

| Instance | GPU | VRAM | Notes |
|---|---|---|---|
| `ml.g6.2xlarge` | 1x L4 | 24 GB | **Recommended** — newer CUDA driver, lower cost |
| `ml.g6.4xlarge` | 1x L4 | 24 GB | More CPU/RAM for concurrency |
| `ml.g6.12xlarge` | 4x L4 | 96 GB | High-throughput production |
| `ml.g5.2xlarge` | 1x A10G | 24 GB | May fail with NIM 1.7.0 — see CUDA note below |
| `ml.g5.4xlarge` | 1x A10G | 24 GB | May fail with NIM 1.7.0 — see CUDA note below |

> **CUDA driver note:** NIM 1.7.0 (Riva 2.15.0) requires CUDA 12.4+ on the host. `ml.g5` instances on SageMaker may ship an older CUDA driver that is missing the `cuCtxCreate_v4` symbol, causing `riva-deploy` to fail at startup. `ml.g6` instances (L4 GPU) ship newer drivers and are the recommended choice.

> Can take more than **30 minutes** to be ready.

### Step 3 — Validate the Endpoint

```bash
python client/test/test_magpie_http.py --endpoint <endpoint-name>
python client/test/test_magpie_ws.py   --endpoint <endpoint-name>
```

See [client/README.md](client/README.md) for all available options.

Synthesis parameters (all optional — set in `.env`):

| Variable | Default | Notes |
|---|---|---|
| `MAGPIE_VOICE` | `Magpie-Multilingual.EN-US.Aria` | Voice name |
| `MAGPIE_LANGUAGE_CODE` | `en-US` | Language code |
| `MAGPIE_SAMPLE_RATE_HZ` | `22050` | Output sample rate |

---

## Deployment — Nemotron ASR Streaming

### Step 1 — Create the SageMaker Model

```bash
./scripts/create_model.sh nemotron-asr
```

Registers the wrapper ECR image as a SageMaker Model. In addition to the common variables, this also injects `NIM_TAGS_SELECTOR=mode=str`, which is required to enable streaming mode in the Nemotron ASR NIM.

Requires in `.env`: `ECR_ASR_IMAGE_URI`, `SAGEMAKER_EXECUTION_ROLE_ARN`, `SAGEMAKER_ASR_MODEL_NAME`, `NGC_API_KEY`.

### Step 2 — Deploy the Endpoint

```bash
./scripts/create_endpoint.sh nemotron-asr
```

Configurable via `.env`:

| Variable | Default | Notes |
|---|---|---|
| `SAGEMAKER_ASR_ENDPOINT_CONFIG_NAME` | `nemotron-asr-config` | |
| `SAGEMAKER_ASR_ENDPOINT_NAME` | `nemotron-asr-endpoint` | |
| `SAGEMAKER_ASR_INSTANCE_TYPE` | `ml.g6.2xlarge` | See instance table above |
| `SAGEMAKER_ASR_INSTANCE_COUNT` | `1` | |
| `SAGEMAKER_CONTAINER_STARTUP_TIMEOUT` | `3600` | Seconds SageMaker waits for health checks to pass |

> Can take more than **30 minutes** to be ready.

### Step 3 — Validate the Endpoint

```bash
python client/test/test_asr_ws.py --endpoint <endpoint-name> --audio /path/to/audio.wav
```

See [client/README.md](client/README.md) for all available options.

Test parameters (all optional — defaults shown):

| Variable | Default | Notes |
|---|---|---|
| `NEMOTRON_ASR_LANGUAGE_CODE` | `en-US` | BCP-47 language code |
| `NEMOTRON_ASR_SAMPLE_RATE_HZ` | `16000` | PCM input sample rate (ignored for WAV) |

---

## Observability

### Stream endpoint logs

```bash
./scripts/logs_endpoint.sh magpie             # follow mode (Ctrl+C to stop)
./scripts/logs_endpoint.sh nemotron-asr
./scripts/logs_endpoint.sh magpie --no-follow # print the last hour of logs and exit
```

SageMaker writes all container output (both NIM and the FastAPI wrapper) to CloudWatch Logs under `/aws/sagemaker/Endpoints/<endpoint-name>`. The script streams from that log group directly.

Logs appear only after the container starts. During the initial deployment the log group may not exist yet — the script will tell you if that's the case.

### List all endpoints

```bash
./scripts/list_endpoints.sh
```

Shows all endpoints in your region with their current status. Highlights any that are still deploying or have failed (with the failure reason).

---

## Teardown

### Delete an endpoint

```bash
./scripts/delete_endpoint.sh magpie
./scripts/delete_endpoint.sh nemotron-asr
```

Deletes the endpoint and its endpoint configuration.

> Delete the endpoint when not in use to avoid ongoing charges. The ECR image and SageMaker model are not billed by uptime.

### Delete a model

```bash
./scripts/delete_model.sh magpie
./scripts/delete_model.sh nemotron-asr
```

Deletes the SageMaker Model object. Make sure the endpoint is deleted first.

---

## Next steps

Once an endpoint is `InService`, head to the [client examples](client/README.md)
to run test clients and Pipecat voice bots against the endpoint.
