# Bot ready signaling

A simple Pipecat example demonstrating how to handle signaling between the
client and the bot, ensuring that the bot starts sending audio only after the
client is ready to play it, so the first words of the greeting are never
clipped.

The handshake uses the standard RTVI `client-ready` / `bot-ready` flow that
ships with Pipecat: `RTVIProcessor` is auto-attached to every `PipelineTask`,
the Pipecat client SDK signals `client-ready` once the transport reaches the
`ready` state, and the bot's `on_client_ready` handler calls `set_bot_ready()`
and pushes the first `TTSSpeakFrame`. No custom `sendAppMessage` plumbing is
needed.

## Quick Start

### First, start the bot server:

1. Navigate to the server directory:

   ```bash
   cd server
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Copy env.example to .env and configure:

   ```bash
   cp env.example .env
   ```

   - Add your API keys

4. Start the server:
   ```bash
   uv run server.py
   ```

### Next, connect using the client app:

For client-side setup, refer to the [JavaScript Guide](client/javascript/README.md).

## Important Note

Ensure the bot server is running before using any client implementations.

## Requirements

- Python 3.10+
- Node.js 16+ (for JavaScript)
- Daily API key
- Cartesia API key
- Modern web browser with WebRTC support
