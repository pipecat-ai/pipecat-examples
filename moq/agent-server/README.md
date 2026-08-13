# MoQ Direct-Mode Voice Agent

An announcement-driven, multi-session voice-agent host built on Pipecat's MoQ
(Media over QUIC) transport. One long-lived process dials a MoQ relay once,
discovers clients by announcement, and runs a fresh STT → LLM → TTS pipeline per
client — no `/start` control plane, no one-process-per-session hosting.

**The relay is the control plane.** Nothing has to reach this process over HTTP
for a call to start, so the host works behind NAT and a client needs only the
relay URL. That's the difference from a standard Pipecat bot run through
`pipecat.runner` (`-t moq`), where a browser POSTs `/start` to bring up one bot.
The runner is still the right default for most MoQ use cases — see
`examples/transports/transports-moq.py` in the main
[pipecat](https://github.com/pipecat-ai/pipecat) repo. Reach for the pattern
here when you want one process serving many concurrent calls behind a relay.

## How it works

Each client mints its own session id and publishes its microphone under it. The
host watches the request prefix and answers on the matching response path:

```
{request_prefix}/{id}     <- the client publishes its mic here
{response_prefix}/{id}    <- the bot publishes its reply here
```

Two clients can never collide, because every call lives on its own pair of
paths. Request and response sit under **separate** prefixes on purpose: the host
only announces on `request/*`, so it never discovers its own replies, and a
per-client token can be scoped tightly — publish `request/<id>`, subscribe
`response/<id>` — so one client can't read another's audio or spoof a reply.

Each session is an ordinary `MOQTransport` in client mode, pointed at its pair
of paths via `MOQParams.response_path` / `request_path`. That costs one relay
connection per call, and keeps the host on supported API — no transport
internals are touched.

## Files

- **`direct_host.py`** — `MOQDirectHost`: dials the relay, discovers clients,
  runs one bot per session id, and enforces the host lifecycle guards.
- **`bot.py`** — `run_bot(transport, session_id)`: the pipeline for one call.
  Knows nothing about relays or discovery.
- **`server.py`** — the process you run. Wires the two together and takes
  configuration from CLI flags or the environment.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- API keys: Deepgram (STT), OpenAI (LLM), Cartesia (TTS)
- A running MoQ relay. This host discovers clients through the relay's
  announcement stream, so unlike `-t moq --moq-serve` it doesn't bind its own
  socket and always needs one.

## Running locally

```bash
uv sync
cp env.example .env      # then fill in the three API keys
uv run server.py --relay-url http://localhost:4443 --no-verify-ssl
```

The host logs `MoQ direct host ready; waiting for clients to announce` and then
starts a pipeline every time a client announces under `request/*`.

To connect, point a MoQ client at the same relay and publish your mic under
`request/<some-id>`; the bot replies under `response/<some-id>`.

## Lifecycle guards

These matter wherever instances are billed or capped — a deployed host with no
exit holds an agent slot forever.

| Setting | Default | What it bounds |
| --- | --- | --- |
| `--host-idle-secs` | 0 | Exits the host after this long with no live calls. `0` runs until stopped — right for a long-lived service, wrong for a capped per-instance deployment. |
| `--peer-wait-secs` | 60 | How long a session waits for the announcing client's media. |
| `--max-sessions` | 8 | Concurrent pipelines; further clients wait for a slot. |
| `MOQ_SESSION_IDLE_SECS` | 300 | A call with no speech in either direction. This one belongs to the bot, since its `PipelineWorker` enforces it. Idle counts *speech* frames, not media, so an abandoned open tab publishing silent mic audio still ages out. `0` disables. |

Client departures aren't announced by the relay (moq-ffi exposes no deactivation
event), so a call ends when its transport sees the client's streams close,
bounded by the guards above.

## Deploying

`--from-env` takes every host setting from `MOQ_*` variables, so the same built
image serves every deployment — e.g. as a systemd unit co-located with a relay,
dialing its internal Unix socket:

```bash
export DEEPGRAM_API_KEY=... OPENAI_API_KEY=... CARTESIA_API_KEY=...
export MOQ_RELAY_URL=unix:///run/moq/internal.sock
export MOQ_REQUEST_PREFIX=demo/pipecat/request
export MOQ_RESPONSE_PREFIX=demo/pipecat/response
uv run server.py --from-env
```

See `env.example` for every variable, and `uv run server.py --help` for the
equivalent flags.

## Customizing

- **Different services**: swap `DeepgramSTTService` / `OpenAILLMService` /
  `CartesiaTTSService` in `bot.py` for any other Pipecat service.
- **Admission control**: `MOQDirectHost` takes a `should_serve` callback
  (announcement → bool) to gate which announced clients get a session — e.g.
  self-electing one relay edge per client across a multi-relay fleet.
