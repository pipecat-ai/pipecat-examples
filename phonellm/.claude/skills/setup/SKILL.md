---
name: setup
description: Walk through this repo's full setup start to finish — install the Pipecat and Modal CLIs, provision PhoneLLM on Modal, create and authorize a proxy token, configure server/.env, health-check the endpoint, sync dependencies, and verify the bot with a headless eval. Use when setting up the project fresh, when the bot can't reach its services, or when the user asks to (re)initialize the project.
---

# PhoneLLM Example setup

Step through the README's setup flow end to end, verifying each step before moving on.
Ask the user whenever a step needs their input or approval — never invent credentials,
never create billable infrastructure without confirming first, and never print secret
values to the terminal (write them straight to `server/.env`).

Work from the repo root. The bot lives in `server/`.

## 1. CLIs

Check `pipecat --version` and `modal --version`. Install whichever is missing:

```bash
uv tool install "pipecat-ai[cli]"
uv tool install modal
```

## 2. Modal auth

Check auth with `modal profile current` (fast, non-interactive). If it fails, the user
must log in themselves — it's a browser flow. Ask them to run:

```
! modal setup
```

There is no `modal login`; `modal setup` is the auth command.

## 3. PhoneLLM endpoint

Check for an existing endpoint: `modal endpoint list --json`, looking for a live
`phonellm-alpha-1`. If present, skip to step 4.

If absent, **ask the user before creating** (it provisions GPU infrastructure —
takes ~20–30 minutes and bills their workspace):

```bash
modal endpoint create --model pipecat-ai/phonellm-alpha-1
```

**Capture the endpoint URL from the create output immediately** — the CLI cannot
retrieve it later (`modal endpoint list` shows status only). Then poll
`modal endpoint list --json` every ~30s (in the background) until status is `live`.

## 4. Endpoint URL

If `MODAL_ENDPOINT_URL` is already in `server/.env`, keep it. If you just ran
`endpoint create`, use the URL from its output. Otherwise **ask the user to paste it**
from their create-output scrollback or the endpoint's page in the Modal dashboard
(`modal dashboard`). Do not guess hostnames — the URL's label is not derivable from
the endpoint name.

## 5. Proxy token

If `MODAL_API_KEY` is already in `server/.env`, keep it. Otherwise create one:

```bash
modal workspace proxy-tokens create --json
```

Combine as `<token-id>.<token-secret>` (`wk-....ws-...`) and write it to `server/.env`
without echoing the secret. The secret is shown once and cannot be retrieved later.

On RBAC workspaces the new token has no environment access and the endpoint will
return `401 "Webhook token not found"`. Authorize it (the endpoint lives in `main`
unless created elsewhere):

```bash
modal workspace proxy-tokens allow <token-id> main
```

## 6. Configure .env

If `server/.env` doesn't exist, `cp server/.env.example server/.env`. Ensure it has:

- `DEEPGRAM_API_KEY` — **ask the user for it** if missing; never invent keys.
- `MODAL_ENDPOINT_URL` — from step 4.
- `MODAL_API_KEY` — from step 5.

## 7. Health-check the endpoint

```bash
curl -s --max-time 60 -w "\nHTTP %{http_code}\n" "$MODAL_ENDPOINT_URL/v1/models" \
  -H "Authorization: Bearer $MODAL_API_KEY"
```

Interpret the result:

- **200** with a model list naming `pipecat-ai/phonellm-alpha-1` — healthy, continue.
- **503, empty body** — scale-to-zero cold start; the request itself triggers spin-up.
  Retry every ~30s (in the background). A 30B model can take several minutes. An
  *instant* 503 that persists well past 10 minutes suggests a wrong URL — re-verify
  with the user rather than retrying forever.
- **401 "Webhook token not found"** — the RBAC `allow` step (5) is missing.

Optionally verify the exact request path the bot uses:

```bash
curl -s "$MODAL_ENDPOINT_URL/v1/chat/completions" \
  -H "Authorization: Bearer $MODAL_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "pipecat-ai/phonellm-alpha-1", "messages": [{"role": "user", "content": "Hello!"}]}'
```

## 8. Dependencies and lint

```bash
cd server && uv sync
uv run ruff check bot.py && uv run pyright bot.py
```

## 9. Verify the bot headless

Boot the bot with the eval transport (background, keep the log):

```bash
uv run bot.py -t eval 2>&1 | tee /tmp/phonellm-eval-bot.log
```

Confirm it reaches "Bot ready!" with no traceback, then in a second shell run the
smoke scenario (deterministic checks only — no judge LLM needed):

```bash
uv run pipecat eval run evals/phonellm_smoke.yaml -v
```

If port 7860 is taken (e.g. the user's own `uv run bot.py` is running — check with
`lsof -nP -iTCP:7860 -sTCP:LISTEN`), don't kill their process: boot the eval bot on
another port with `--port 7861` and pass `--bot-url ws://localhost:7861` to the eval.

All turns passing proves the whole pipeline against the live endpoint: greeting,
a factual answer ("Berlin"), and multi-turn context ("Paris"). On failure, grep the
bot log for the traceback before re-running; a 503 from the LLM means the endpoint
went cold again — warm it (step 7) and re-run.

## 10. Done

Tell the user to start the bot and talk to it:

```bash
uv run bot.py
```

Browser test UI: http://localhost:7860.
