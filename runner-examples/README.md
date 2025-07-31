# Pipecat Development Runner Examples

Examples demonstrating the unified development runner for building voice AI bots across multiple transport types.

## Prerequisites

```bash
pip install pipecat-ai[runner]
```

Set up your API keys in `.env`:

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

### 01-single-transport-bot.py

Basic WebRTC bot demonstrating the runner fundamentals.

```bash
python 01-single-transport-bot.py
# Opens http://localhost:7860/client
```

### 02-two-transport-bot.py

Bot supporting Daily and WebRTC with manual transport detection.

```bash
# WebRTC (default)
python 02-two-transport-bot.py

# Daily
python 02-two-transport-bot.py -t daily
```

### 03-all-transport-bot.py

Comprehensive bot supporting all five transport types with manual setup and telephony auto-detection.

```bash
# WebRTC
python 03-all-transport-bot.py

# Daily
python 03-all-transport-bot.py -t daily

# Telephony (requires public proxy)
python 03-all-transport-bot.py -t twilio -x yourproxy.ngrok.io
python 03-all-transport-bot.py -t telnyx -x yourproxy.ngrok.io
python 03-all-transport-bot.py -t plivo -x yourproxy.ngrok.io
```

### 04-all-transport-factory-bot.py

Clean implementation using the `create_transport` utility with factory functions.

```bash
# Same usage as 03, but with simplified code
python 04-all-transport-factory-bot.py -t daily
```

## Key Concepts

- **Runner**: HTTP service that spawns bots on-demand and handles transport infrastructure
- **Runner Arguments**: Transport-specific data passed to your bot (room URLs, WebSocket connections, etc.)
- **Transport Factory**: Clean pattern for configuring multiple transports with lazy instantiation
- **Environment Detection**: `ENV=local` enables conditional features like Krisp audio filtering

## Transport Types

| Transport | Usage                                       | Access                       |
| --------- | ------------------------------------------- | ---------------------------- |
| WebRTC    | `python bot.py`                             | http://localhost:7860/client |
| Daily     | `python bot.py -t daily`                    | http://localhost:7860        |
| Twilio    | `python bot.py -t twilio -x proxy.ngrok.io` | Phone calls                  |
| Telnyx    | `python bot.py -t telnyx -x proxy.ngrok.io` | Phone calls                  |
| Plivo     | `python bot.py -t plivo -x proxy.ngrok.io`  | Phone calls                  |

For detailed documentation, see the [Development Runner Guide](https://docs.pipecat.ai/server/utilities/runner/guide).
