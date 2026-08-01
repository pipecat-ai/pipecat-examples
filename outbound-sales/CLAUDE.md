# CLAUDE.md - outbound-sales

Hailey, an outbound sales voice agent built with Pipecat. The dialer reads `leads.csv`, server.py creates a Daily room with PSTN dial-out and starts a bot, and Hailey tries to collect the IT decision maker's contact info on the call.

## Layout

All code lives in `server/`. Run every command from there with `uv run`.

- `bot.py`: Hailey's pipeline, tools (`save_contact_info`, `end_call`), dial-out retry logic, and the eval entry point
- `server.py`: FastAPI webhook server (port 8080); `/dialout` starts calls, `/call_result` records outcomes, `/results` is polled by the dialer
- `server_utils.py`: data models, Daily room creation, bot starting, `report_result`
- `dialer.py`: batch dialer, 5 calls at a time
- `scenarios/` + `evals.yaml`: text-mode behavioral evals

## Dev loop

Prefer evals over real calls. They run the same bot in text mode with no telephony:

```bash
uv run pipecat eval suite evals.yaml          # whole suite
uv run bot.py -t eval                          # then: uv run pipecat eval run scenarios/happy_path.yaml -v
```

The bot exits when Hailey hangs up, so restart `bot.py -t eval` between single-scenario runs.

Real calls need two terminals: `uv run server.py` (port 8080) and `uv run bot.py -t daily` (port 7860), plus a purchased Daily phone number and dial-out enablement.

## Rules and gotchas

- **This is a demo: results are NOT saved to files.** Call outcomes are logged to the terminal and held in server.py's memory (`CALL_RESULTS`). A real production app would write them to a database in `/call_result`. Do not add file or CSV persistence.
- The outcome report from the bot doubles as the dialer's "call finished" signal. If you touch the shutdown path in `run_bot`, keep the `report_result` call in the `finally` block.
- In `end_call`, `worker.flush_pipeline()` must run before pushing `EndWorkerFrame`. The eval websocket server closes as soon as the EndFrame passes the input transport, so anything still queued would be lost.
- The first reply is canned (`CannedGreetingGate`), skipping the LLM round-trip. Eval runs push it as LLM response frames because text-mode evals never see TTS output.
- Smart Turn's silence fallback is capped at 1s (`stop_secs=1.0`) on purpose; don't raise it back to the 3s default.
- Calls are recorded with Daily cloud recording, started from the bot's meeting token. There is no local recording code.
- **Before deploying to Pipecat Cloud**, change the fields in `pcc-deploy.toml`: `agent_name`, `image` (it points at the example author's Docker Hub repo), and `secret_set` are all account-specific.
- Python deps come from `pyproject.toml` via `uv sync`; `pipecat-ai` installs from the GitHub `main` branch until 1.4.0 ships on PyPI.
