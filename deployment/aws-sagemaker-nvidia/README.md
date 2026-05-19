# NVIDIA Models on AWS SageMaker

A practical guide and quickstart for deploying NVIDIA speech AI models (Magpie TTS and Nemotron ASR) to AWS SageMaker, and integrating them with [Pipecat](https://github.com/pipecat-ai/pipecat) for real-time voice applications.

---

## What is NVIDIA Nemotron Speech ASR?

**ASR** stands for *Automatic Speech Recognition* — it converts spoken audio into text.

NVIDIA's **Nemotron Speech ASR** is a state-of-the-art speech recognition model optimized to run on NVIDIA GPUs. It is fast, accurate, and supports multiple languages. Think of it as the "ears" of a voice AI application: it listens to what a user says and turns it into words your application can understand.

- Delivered as a **NIM** (NVIDIA Inference Microservice) — a pre-packaged Docker container that is production-ready out of the box.
- Exposes a REST and WebSocket API on port 9000, and a gRPC API on port 50051.
- Supports real-time streaming transcription via WebSocket (`/v1/realtime?intent=transcription`).
- The **Streaming** variant (`nemotron-asr-streaming`) supports streaming mode only.

## What is NVIDIA Nemotron Magpie TTS?

**TTS** stands for *Text-to-Speech* — it converts text into spoken audio.

**NVIDIA Magpie TTS** (`magpie-tts-multilingual`) is a high-quality, low-latency speech synthesis model built on top of NVIDIA Riva. It can produce natural-sounding voices in multiple languages and is optimized for real-time streaming — meaning audio starts playing before the full sentence is generated.

- Also delivered as a **NIM** container.
- Latest version: `1.7.0` (based on Riva 2.15.0).
- Supports bidirectional streaming for ultra-low latency.

## What is a NIM?

A **NIM (NVIDIA Inference Microservice)** is a ready-to-deploy Docker container that bundles:
- The model weights
- An optimized inference runtime (TensorRT, Triton, etc.)
- A standard API (OpenAI-compatible or gRPC)

You pull it, configure it, and run it — no ML expertise required to get a production-grade endpoint.

## What is AWS SageMaker?

**AWS SageMaker** is Amazon's managed platform for deploying machine learning models at scale. Instead of managing your own GPU servers, SageMaker lets you:

- Deploy a Docker container as a scalable HTTPS endpoint.
- Choose from dozens of GPU instance types (e.g., `ml.g5.2xlarge`).
- Pay only for what you use.
- Get built-in monitoring, auto-scaling, and security.

In short: SageMaker handles the infrastructure so you can focus on your application.

---

## Project Goal

> Deploy NVIDIA Magpie TTS and Nemotron ASR to AWS SageMaker using official NIM containers, and connect them to a Pipecat voice pipeline.

### Why not use the AWS Marketplace listing?

There is a Magpie TTS listing on the AWS Marketplace, but it ships with **Riva 1.10.0** — a significantly older version. The NIM container on NVIDIA NGC uses **Riva 2.15.0**, which has better performance, more voices, and improved streaming support. This project deploys the up-to-date version directly.

---

## Architecture Overview

```
User Audio → Pipecat Pipeline
                 │
                 ├── ASR Service → Nemotron Speech (SageMaker Endpoint)
                 │                     converts speech to text
                 │
                 ├── LLM Service → OpenAILLMService (Nemotron Super 120B — Modal hosted)
                 │                     generates a response
                 │
                 └── TTS Service → NvidiaSageMakerTTSService (Magpie TTS — SageMaker)
                                       converts text back to speech  ← this project
```

STT uses NVIDIA's hosted API at `build.nvidia.com` (requires `NVIDIA_API_KEY`).
LLM uses a Nemotron Super 120B model hosted on Modal (configured via `NEMOTRON_LLM_BASE_URL`).
Only the TTS service is deployed to SageMaker by this project.

---

## Prerequisites

- An **AWS account** with permissions to use ECR, SageMaker, and IAM.
- An **NVIDIA NGC API key** — get one free at [build.nvidia.com](https://build.nvidia.com).
- **Docker** installed locally.
- **AWS CLI** configured (`aws configure`).
- Python 3.11+ and `uv` (or `pip`) for the Pipecat integration.

---

## Deploying

All deployment steps are automated with shell scripts in `scripts/`. The full walkthrough is in **[DEPLOYMENT.md](DEPLOYMENT.md)**.

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for configuration options, instance types, and Pipecat integration.

Once the endpoint is `InService`, test it and run the voice bot — see **[client/README.md](client/README.md)**.

---

## Quick Links

| Resource | URL |
|---|---|
| Deployment guide | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Client examples & voice bot | [client/README.md](client/README.md) |
| Magpie TTS wrapper | [sagemaker-wrapper/magpie/](sagemaker-wrapper/magpie/) |
| Nemotron ASR wrapper | [sagemaker-wrapper/nemotron-asr/](sagemaker-wrapper/nemotron-asr/) |
| AWS SageMaker console | https://console.aws.amazon.com/sagemaker/home#/endpoints |

---

## References

| Resource                                             | URL |
|------------------------------------------------------|---|
| Magpie TTS NIM deploy guide                          | https://build.nvidia.com/nvidia/magpie-tts-multilingual/deploy |
| Magpie NIM container tags                            | https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/magpie-tts-multilingual/tags |
| NVIDIA TTS NIM DOCS                                  | https://docs.nvidia.com/nim/speech/latest/tts/index.html |
| NVIDIA TTS client source code                        | https://github.com/nvidia-riva/python-clients/blob/main/riva/client/realtime.py |
| NVIDIA TTS NIM GetStarted                            | https://docs.nvidia.com/nim/speech/latest/get-started/tutorials/tts.html#step-4-synthesize-speech |
| NVIDIA NIM TTS Realtime API — Client & Server Events | https://docs.nvidia.com/nim/speech/latest/reference/api-references/tts/realtime-tts.html#list-of-client-events|
| Nemotron ASR NIM deploy guide                        | https://build.nvidia.com/nvidia/nemotron-asr-streaming/deploy |
| Nemotron ASR NIM deploy docs                         | https://docs.nvidia.com/nim/speech/latest/asr/deploy-asr-models/nemotron-asr-streaming.html |
| NVIDIA NIM ASR Realtime API — Client & Server Events | https://docs.nvidia.com/nim/speech/latest/reference/api-references/asr/realtime-asr.html |
| NVIDIA ASR client source code                        | https://github.com/nvidia-riva/python-clients/blob/main/scripts/asr/transcribe_file.py |
| AWS SageMaker — bidirectional streaming docs         | https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-inference-code.html |

---

