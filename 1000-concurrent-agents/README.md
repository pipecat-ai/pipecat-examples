# 1000 Concurrent Agents Example

Demonstrates how to spawn 1000 concurrent voice agents using Daily rooms and Pipecat Cloud, handling rate limits gracefully.

## Prerequisites

- Python 3.10+
- [Daily](https://daily.co) API key
- [Pipecat Cloud](https://pipecat.ai) account and API key
- [Google](https://ai.google.dev) API key (for Gemini Live)

## Setup

1. Install dependencies:

```bash
uv sync
```

2. Copy `env.example` to `.env` and add your API keys:

```bash
cp env.example .env
```

3. Deploy the bot to Pipecat Cloud:

```bash
pcc deploy
```

Note the agent name from the deployment output (e.g., `1000-concurrent-agents`).

## Usage

Run the orchestration script:

```bash
uv run start_agents.py --agent-name 1000-concurrent-agents
```

Options:
- `--agent-name`: Name of your deployed Pipecat Cloud agent (required)
- `--num-agents`: Number of agents to start (default: 1000)
- `--room-prefix`: Prefix for room names (default: `concurrent-test`)

## How It Works

1. **Batch Room Creation**: Creates all rooms in a single Daily API call using the [batch endpoint](https://docs.daily.co/reference/rest-api/rooms/batch/post)
2. **Room Expiration**: Rooms auto-expire after 10 minutes (no cleanup needed)
3. **Agent Spawning**: Starts agents via Pipecat Cloud with exponential backoff for rate limits
4. **Logging**: Progress and errors logged to `agents.log`

## Architecture

```
start_agents.py
    │
    ├── POST /rooms/batch (1 request → 1000 rooms)
    │
    └── For each room:
            └── Start Pipecat Cloud agent (with rate limit handling)
                    └── bot.py joins room, greets user, waits
```

## Rate Limit Handling

- **Daily**: Batch API avoids per-room rate limits
- **Pipecat Cloud**: Exponential backoff with jitter on 429 responses
