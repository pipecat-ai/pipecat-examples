# PhoneLLM Example

[PhoneLLM](https://huggingface.co/pipecat-ai/phonellm-alpha-1) is an open-weights 30B language model from the Pipecat team, fine-tuned for voice agents that handle phone calls — faster and cheaper than larger general-purpose models.

> [!TIP]
> **Quickstart:** using [Claude Code](https://claude.com/claude-code)? Run `/setup` in this repo — a committed skill (`.claude/skills/setup/`) that steps through everything below, health-checking along the way and asking for input only where needed. The rest of this README is the manual path.

This repo is a [Pipecat](https://github.com/pipecat-ai/pipecat) voice agent that runs PhoneLLM on [Modal](https://modal.com), with Deepgram Flux for speech-to-text and Deepgram Aura for text-to-speech.

```
Deepgram Flux (STT) → Pipecat PhoneLLM Alpha 1 on Modal (LLM) → Deepgram Aura (TTS)
```

## Install the CLIs

```bash
uv tool install "pipecat-ai[cli]"
uv tool install modal
```

## Provision PhoneLLM on Modal

### 1. Log in

```bash
modal setup
```

This opens your browser to authenticate and writes your API credentials to a local Modal profile.

### 2. Create the endpoint

```bash
modal endpoint create --model pipecat-ai/phonellm-alpha-1
```

Modal provisions an [Auto Endpoint](https://modal.com/docs/guide/endpoints) — a production-ready, OpenAI-compatible inference server for PhoneLLM. **Note the endpoint URL it prints; you'll need it below.** This process can take ~20 minutes.

> **Note:** The CLI can't retrieve the endpoint URL after the fact — `modal endpoint list` shows status but not the URL. If you lose it, find it on the endpoint's page in the [Modal dashboard](https://modal.com/) (`modal dashboard` opens it).

### 3. Check that it's running

List your endpoints and their status (`provisioning` → `live`):

```bash
modal endpoint list
```

Once it's running, you can send a quick authenticated request using your local Modal credentials (no token required):

```bash
modal curl <endpoint-url>/v1/models
```

A JSON response listing `pipecat-ai/phonellm-alpha-1` means the endpoint is healthy.

> **Note:** Endpoints scale to zero when idle. The first request after creation (or after a quiet period) returns 503 while the model spins up — this can take several minutes for a 30B model, and the container logs (`modal app logs`) may go quiet during kernel compilation. Keep retrying.

### 4. Create a proxy token

The bot authenticates with a workspace proxy token rather than your local credentials:

```bash
modal workspace proxy-tokens create
```

This prints a token ID (`wk-...`) and secret (`ws-...`). Save the secret now — it can't be retrieved later. Combined as `<token-id>.<token-secret>`, they form the API key the bot sends as a Bearer token.

On workspaces with RBAC enabled, new tokens start with no environment access, and the endpoint rejects them with `401 "Webhook token not found"`. Allow the token into the environment the endpoint lives in (`main` unless you created it elsewhere):

```bash
modal workspace proxy-tokens allow <token-id> main
```

### 5. Verify end to end (optional)

Test the exact request path the bot will use — proxy-token auth against the chat completions API:

```bash
curl "<endpoint-url>/v1/chat/completions" \
  -H "Authorization: Bearer <token-id>.<token-secret>" \
  -H "Content-Type: application/json" \
  -d '{"model": "pipecat-ai/phonellm-alpha-1", "messages": [{"role": "user", "content": "Hello!"}]}'
```

## Configure the bot

```bash
cd server
cp .env.example .env
```

In `.env`, set:

- `MODAL_ENDPOINT_URL` — the endpoint URL from `modal endpoint create` (or the Modal dashboard)
- `MODAL_API_KEY` — the proxy token, combined as `<token-id>.<token-secret>` (`wk-....ws-...`)
- `DEEPGRAM_API_KEY` — your [Deepgram](https://console.deepgram.com) API key

## Run the bot

Install dependencies and start the bot:

```bash
uv sync
uv run bot.py
```

Open http://localhost:7860 in your browser and talk to it.

### Test it headless

The repo ships a behavioral smoke test that drives the whole pipeline — greeting, a factual answer, and multi-turn context — against the live endpoint, no microphone needed. Boot the bot with the eval transport, then run the scenario from a second terminal (both from `server/`):

```bash
uv run bot.py -t eval
uv run pipecat eval run evals/phonellm_smoke.yaml -v
```

The checks are deterministic, so no judge LLM is required.

## Deploying to Pipecat Cloud

The quickest path is a [cloud build](https://docs.pipecat.ai/pipecat-cloud/guides/cloud-builds): `pipecat cloud deploy` uploads your source and builds the image on Pipecat Cloud from the committed `server/Dockerfile` — no local Docker, no container registry. The deploy config is already in `server/pcc-deploy.toml`. You'll need a [Pipecat Cloud account](https://pipecat.daily.co) and the cloud plugin:

```bash
uv tool install "pipecat-ai[cli]" --with pipecatcloud
```

### 1. Log in (one time)

```bash
pipecat cloud auth login
```

### 2. Upload your secrets

A deployed bot doesn't have your local `.env`, so push it as a secret set (the name matches `secret_set` in `pcc-deploy.toml`). From `server/`:

```bash
pipecat cloud secrets set phonellm-example-secrets --file .env --skip
```

Re-run this whenever a key changes.

### 3. Deploy

From `server/`:

```bash
pipecat cloud deploy
```

The CLI tars up the project (excluding `.env`, `.venv`, etc.), builds the image in the cloud, and deploys it. Builds are content-hashed, so redeploying unchanged code reuses the cached build and is nearly instant.

### 4. Check on it

```bash
pipecat cloud agent status phonellm-example
pipecat cloud agent logs phonellm-example
```

> **Note:** The `[krisp_viva]` block in `pcc-deploy.toml` enables Krisp noise cancellation on Cloud; the bot skips it automatically when running locally.

## Cleaning up

To permanently stop the endpoint and its containers (the `ep-...` ID comes from `modal endpoint list`):

```bash
modal endpoint stop <endpoint-id>
```
