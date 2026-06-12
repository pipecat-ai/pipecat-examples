# Outbound Sales Bot

Meet Hailey, an outbound sales agent built with Pipecat. She calls a list of leads in batches of 5 over Daily PSTN, introduces herself ("Hi, this is Hailey from Pipecat Labs. Am I speaking with Beau?"), and tries to reach the person who handles IT decisions. She either gets transferred or collects the decision maker's contact info, saves it to `results.csv`, says thanks, and hangs up.

The example also shows the new **Pipecat evals** feature: the same bot runs in a text-only eval mode so you can test its behavior in seconds, with no phone calls and no audio.

This project was scaffolded with the Pipecat CLI:

```bash
pipecat init outbound-sales --bot-type telephony -t daily_pstn_dialout \
  --daily-pstn-mode dial-out -m cascade \
  --stt deepgram_stt --llm openai_llm --tts cartesia_tts --eval
```

## How It Works

```
leads.csv → dialer.py → server.py /dialout → Daily room + dial-out
                                              ↓
results.csv ← bot.py (Hailey) ← call answered
```

1. `dialer.py` reads `leads.csv` and starts calls in batches of 5
2. For each lead, `server.py` creates a Daily room with dial-out enabled and starts a bot
3. The bot dials the lead's number; when they answer, Hailey runs the conversation
4. Hailey saves contact info with the `save_contact_info` tool and hangs up with the `end_call` tool
5. Every finished call appends one row to `results.csv`; the dialer polls that file to know when a batch is done, then starts the next batch

## Configuration

- **Bot Type**: Telephony
- **Transport(s)**: Daily PSTN (Dial-out), plus an eval transport for testing
- **Pipeline**: Cascade
  - **STT**: Deepgram
  - **LLM**: OpenAI
  - **TTS**: Cartesia

> **Note**: This example currently installs `pipecat-ai` from the `main` branch on GitHub, because the CLI and evals features are newer than the latest PyPI release. Once 1.4.0 ships, switch the dependency in `server/pyproject.toml` to the PyPI version.

## Setup

All commands run from the `server/` directory.

1. Create a virtual environment and install dependencies

   ```bash
   cd server
   uv sync
   ```

2. Set up environment variables

   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. Buy a phone number

   Instructions on how to do that can be found at this [docs link](https://docs.daily.co/reference/rest-api/phone-numbers/buy-phone-number)

4. Request dial-out enablement

   For compliance reasons, to enable dial-out for your Daily account, you must request enablement via the form. You can find out more about dial-out, and the form, at the [link here](https://docs.daily.co/guides/products/dial-in-dial-out#main)

## Test Hailey with Evals (no phone needed)

Evals drive the bot over a local WebSocket in text mode: no telephony, no audio, no waiting. An OpenAI model (gpt-4o-mini) judges the responses, so only `OPENAI_API_KEY` is needed.

Run the whole suite (spawns a fresh bot per scenario):

```bash
uv run pipecat eval suite evals.yaml
```

Expected output:

```
  ✓ bot.py gatekeeper_refusal (8089ms)
  ✓ bot.py happy_path (14954ms)
  ✓ bot.py transfer_path (18785ms)

  3/3 passed  ·  19.3s
```

The scenarios live in `scenarios/`:

- `happy_path.yaml`: the lead hands over the IT director's contact info
- `transfer_path.yaml`: a gatekeeper transfers Hailey to the IT director
- `gatekeeper_refusal.yaml`: "take us off your list"; Hailey must not argue

To iterate on a single scenario:

```bash
# Terminal 1 (Hailey exits when she hangs up, so restart between runs)
uv run bot.py -t eval

# Terminal 2
uv run pipecat eval run scenarios/happy_path.yaml -v
```

This is the fast dev loop: tweak the system prompt in `bot.py`, re-run the suite, repeat.

## Run a Real Call

You'll need two terminal windows open:

1. **Terminal 1**: Start the webhook server:

   ```bash
   uv run server.py
   ```

   This runs on port 8080 and handles dial-out requests.

2. **Terminal 2**: Start the bot server:

   ```bash
   uv run bot.py -t daily
   ```

   This runs on port 7860 and handles the bot logic.

3. **Test a single call**

   ```bash
   curl -X POST "http://localhost:8080/dialout" \
     -H "Content-Type: application/json" \
     -d '{
       "dialout_settings": { "phone_number": "+15551234567" },
       "lead": { "phone": "+15551234567", "name": "Beau", "company": "Acme Robotics" }
     }'
   ```

   Answer the call and have a chat with Hailey. When the call ends, check `results.csv` for the outcome.

## Run a Batch Campaign

Edit `leads.csv` with real numbers (`phone,name,company`), then with both servers running:

```bash
uv run dialer.py
```

The dialer calls in batches of 5, waits for every call in a batch to finish (or time out after 6 minutes), then starts the next batch. Leads that already have a row in `results.csv` are skipped, so you can stop and re-run it.

`results.csv` columns: timestamp, call_id, lead phone/name/company, outcome, contact name/role/phone/email, notes. Outcomes are `contact_captured`, `refused`, `wrong_number`, `transferred_no_info`, `other`, `hung_up`, `no_answer`, `dialout_error`, `timeout`, or `error`.

> **Production note**: the dialer learns a call finished by polling `results.csv`, which works locally because all bot sessions run in one process on one filesystem. On Pipecat Cloud each bot runs in its own container, so report outcomes to a webhook or shared storage (database, S3) instead.

## Environment Configuration

The bot supports two deployment modes controlled by the `ENV` variable:

### Local Development (`ENV=local`)

- Uses your local server for handling dial-out requests and starting the bot
- Default configuration for development and testing

### Production (`ENV=production`)

- Bot is deployed to Pipecat Cloud; requires `PIPECAT_API_KEY` and `PIPECAT_AGENT_NAME`
- Set these when deploying to production environments
- Your FastAPI server runs either locally or deployed to your infrastructure

## Project Structure

```
outbound-sales/
├── server/                  # Python bot server
│   ├── bot.py               # Hailey: pipeline, tools, dial-out + eval modes
│   ├── server.py            # FastAPI webhook server for Daily PSTN dial-out
│   ├── server_utils.py      # Data models, room creation, bot starting
│   ├── dialer.py            # Batch dialer (5 calls at a time)
│   ├── results.py           # Shared results.csv helpers
│   ├── leads.csv            # Who to call (phone,name,company)
│   ├── evals.yaml           # Eval suite manifest
│   ├── scenarios/           # Text-mode eval scenarios
│   ├── pyproject.toml       # Python dependencies
│   ├── .env.example         # Environment variables template
│   ├── Dockerfile           # Container image for Pipecat Cloud
│   └── pcc-deploy.toml      # Pipecat Cloud deployment config
├── .gitignore
└── README.md
```

Key pieces in `bot.py`:

- **Dual-mode entry point**: `bot()` detects eval runs (`-t eval`) and serves the eval WebSocket transport instead of dialing out. Real calls use `DailyTransport` with full audio.
- **`save_contact_info` tool**: stores the decision maker's name, role, phone, and email on the call result.
- **`end_call` tool**: flushes the pipeline (so the goodbye and tool events are delivered), then shuts down gracefully. Hanging up is just the bot leaving the Daily room.
- **`DialoutManager`**: retries the dial-out up to 5 times before giving up.

## Deploying to Pipecat Cloud

This project is configured for deployment to Pipecat Cloud. You can learn how to deploy in the [Pipecat Quickstart Guide](https://docs.pipecat.ai/getting-started/quickstart#step-2-deploy-to-production).

Refer to the [Pipecat Cloud Documentation](https://docs.pipecat.ai/deployment/pipecat-cloud/introduction) to learn more about configuring, deploying, and managing your agents. Remember the production note above: `results.csv` aggregation needs replacing with a webhook or shared storage when bots run in separate containers.

## Learn More

- [Pipecat Documentation](https://docs.pipecat.ai/)
- [Pipecat GitHub](https://github.com/pipecat-ai/pipecat)
- [Pipecat Examples](https://github.com/pipecat-ai/pipecat-examples)
- [Discord Community](https://discord.gg/pipecat)
