# Pipecat Development Runner Examples

Examples demonstrating the unified development runner for building voice AI bots across multiple transport types.

## Prerequisites

1. Set up venv and install dependencies:

```bash
uv sync
```

2. Set up your API keys in `.env`:

```bash
# Required for all examples
DEEPGRAM_API_KEY=your_deepgram_key
CARTESIA_API_KEY=your_cartesia_key
OPENAI_API_KEY=your_openai_key

# For Daily transport
DAILY_API_KEY=your_daily_key

# For telephony transports
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TELNYX_API_KEY=your_telnyx_key
PLIVO_AUTH_ID=your_plivo_id
PLIVO_AUTH_TOKEN=your_plivo_token
```

## Examples

### 01-create-transport-bot.py (recommended)

One bot across **all** transports using `create_transport`. It selects the right
transport from the runner arguments and builds it — including telephony
serializers — from the factory functions in `transport_params`. This is the
recommended way to construct transports.

```bash
# WebRTC (default)
python 01-create-transport-bot.py
# Opens http://localhost:7860/client

# Daily
python 01-create-transport-bot.py -t daily

# Telephony (requires public proxy)
python 01-create-transport-bot.py -t twilio -x yourproxy.ngrok.io
python 01-create-transport-bot.py -t telnyx -x yourproxy.ngrok.io
python 01-create-transport-bot.py -t plivo -x yourproxy.ngrok.io

# Headless behavioral eval — available for free, no transport_params entry needed
python 01-create-transport-bot.py -t eval
```

### 02-verbose-transport-bot.py

The manual equivalent for **Daily and SmallWebRTC** — branching on the
runner-args type and constructing each transport by hand. Use this when you need
full control over transport setup, or to understand what `create_transport` does
for you.

Telephony is intentionally omitted: those transports need provider serializers
that `create_transport` builds automatically, and you should not hand-roll them.

```bash
# WebRTC (default)
python 02-verbose-transport-bot.py

# Daily
python 02-verbose-transport-bot.py -t daily
```

## Key Concepts

- **Runner**: HTTP service that spawns bots on-demand and handles transport infrastructure
- **Runner Arguments**: Transport-specific data passed to your bot (room URLs, WebSocket connections, etc.)
- **`create_transport`**: Builds the right transport from the runner arguments and a `transport_params` dict of factory functions — the recommended pattern, and the only one that handles telephony serializers and the eval transport for you
- **Environment Detection**: `ENV=local` enables conditional features like Krisp audio filtering

## Transport Types

| Transport | Usage                                       | Access                       |
| --------- | ------------------------------------------- | ---------------------------- |
| WebRTC    | `python bot.py`                             | http://localhost:7860/client |
| Daily     | `python bot.py -t daily`                    | http://localhost:7860        |
| Twilio    | `python bot.py -t twilio -x proxy.ngrok.io` | Phone calls                  |
| Telnyx    | `python bot.py -t telnyx -x proxy.ngrok.io` | Phone calls                  |
| Plivo     | `python bot.py -t plivo -x proxy.ngrok.io`  | Phone calls                  |
| Eval      | `python bot.py -t eval`                     | Headless behavioral testing  |

For detailed documentation, see the [Development Runner Guide](https://docs.pipecat.ai/server/utilities/runner/guide).
