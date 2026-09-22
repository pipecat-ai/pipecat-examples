# Bot ready signaling Server

The Pipecat runner serves this bot and gives Pipecat clients an endpoint to connect to.

## Endpoints

- `POST /start` - Pipecat client connection endpoint

## Environment Variables

Copy `env.example` to `.env` and configure:

```ini
# Required API Keys
DAILY_API_KEY=           # Your Daily API key
CARTESIA_API_KEY=        # Your Cartesia API key

# Optional Configuration
DAILY_API_URL=           # Optional: Daily API URL (defaults to https://api.daily.co/v1)
DAILY_ROOM_URL=          # Optional: Fixed room URL, handy for local development
```

## Running the Server

Install dependencies:

```bash
uv sync
```

Run the server:

```bash
uv run bot.py -t daily
```

The runner listens on `localhost:7860`. Pass `--host` or `--port` to change that.
