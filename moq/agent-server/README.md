# MoQ Voice-Agent Server

An announcement-driven, multi-session voice-agent server built on Pipecat's
[MoQ (Media over QUIC)](https://pipecat.daily.co) transport. One long-lived
process dials a MoQ relay once, discovers clients by announcement, and spawns
a fresh STT → LLM → TTS pipeline per client — no `/start` control plane, no
one-process-per-session hosting.

This is different from a standard Pipecat bot run through `pipecat.runner`
(`-t moq`, one bot per `/start` request). That's still the right default for
most MoQ use cases — see `examples/transports/transports-moq.py` in the main
[pipecat](https://github.com/pipecat-ai/pipecat) repo. Reach for the pattern
here specifically when you want one process serving many concurrent MoQ
sessions behind a relay, with the relay itself acting as the discovery/control
plane instead of an HTTP endpoint.

**This lives here, not in `pipecat-ai`.** `MOQAgentSession` subclasses
`MOQTransport` and reaches into a few of its protected attributes to replace
connection bring-up while reusing its per-session media engine — those
attributes aren't a stable part of the pipecat-ai transport API. Treat
`agent.py` as a reference implementation to copy and adapt for your own
deployment, not a dependency to import from a released package.

## Files

- **`agent.py`** — the reusable pieces: `MOQAgentSession` (one client's
  session, driven by the server) and `MOQAgentServer` (owns the relay
  connection, discovers clients by announcement, dispatches a session per
  client).
- **`bot.py`** — quickstart entry point. Pipeline and prompt are hardcoded in
  the file, config comes from CLI flags. Start here.
- **`server.py`** — same pipeline, but every knob (API keys, LLM model, TTS
  voice, system prompt) comes from the environment instead of code, so one
  built image/service can serve every deployment. Use this as the basis for a
  systemd service or container image co-located with a relay.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- API keys: Deepgram (STT), OpenAI (LLM), Cartesia (TTS)
- A running MoQ relay (e.g. `just relay` in the [moq](https://pypi.org/project/moq-rs/)
  repo, listening on `:4443` by default)

## Running locally

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp env.example .env
```

Edit `.env` and set `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, and `CARTESIA_API_KEY`.

### 3. Start a MoQ relay

This server discovers clients through the relay's announcement stream, so it
needs a relay to dial — unlike the single-bot `-t moq --moq-serve` pattern,
it doesn't bind its own socket. Run one locally on `:4443` (see the upstream
[moq](https://pypi.org/project/moq-rs/) project for relay setup).

### 4. Start the agent server

```bash
uv run bot.py --relay-url http://localhost:4443 --no-verify-ssl
```

The server logs `MoQ voice-agent server ready; waiting for clients to
announce` and then dispatches a new pipeline every time a client announces a
broadcast under `request/*`.

### 5. Connect a client

Point a MoQ client at the relay and publish your mic under
`request/<some-id>`; the agent announces its reply under
`response/<some-id>`. See the main pipecat repo's `MOQ_DEV.md` for the
browser client setup this pairs with.

## Production-style deployment

`server.py` reads everything from the environment instead of CLI flags, so
the same built artifact works across deployments:

```bash
export DEEPGRAM_API_KEY=... OPENAI_API_KEY=... CARTESIA_API_KEY=...
export MOQ_RELAY_URL=unix:///run/moq/internal.sock   # e.g. co-located with the relay
uv run server.py
```

See `env.example` for every variable it reads (`MOQ_VOICE_LLM_MODEL`,
`MOQ_VOICE_TTS_VOICE`, `MOQ_VOICE_SYSTEM_PROMPT`), and `server.py --help` for
the relay/prefix/concurrency flags (`--relay-url`, `--request-prefix`,
`--response-prefix`, `--max-sessions`).

## Customizing

- **Different services**: swap `DeepgramSTTService` / `OpenAILLMService` /
  `CartesiaTTSService` in `bot.py` or `server.py` for any other Pipecat
  service.
- **Admission control**: `MOQAgentServer` takes a `should_serve` callback
  (announcement → bool) if you need to gate which announced clients actually
  get a session — e.g. self-electing one relay edge per client in a
  multi-relay fleet.
- **Concurrency**: `--max-sessions` caps how many pipelines run at once;
  excess announced clients queue.
