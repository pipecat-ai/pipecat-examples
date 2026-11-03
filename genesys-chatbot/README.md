# Genesys Voice Bot Examples

This repository contains an example of a voice bot that integrates with Genesys Cloud using Pipecat. It answers inbound calls through Audio Connector, which streams the call's audio both ways over a WebSocket.

## Examples

### 🔽 [Inbound Calling](./inbound/)

Demonstrates how to handle incoming phone calls where users call your Genesys Cloud number and interact with a voice bot.

## Architecture

```
Phone Call ↔ Genesys Cloud ↔ Audio Connector (WebSocket) ↔ Pipecat ↔ AI Services
```

**Components:**

- **Genesys Cloud**: Handles phone call routing through Architect call flows
- **Audio Connector**: Real-time bidirectional audio over WebSocket, using the AudioHook protocol
- **Pipecat**: Audio processing pipeline and AI service orchestration
- **AI Services**: OpenAI (LLM), Deepgram (STT), Cartesia (TTS)

## Getting Help

- **Detailed Setup**: See the README file in the `inbound/` directory
- **Pipecat Documentation**: [docs.pipecat.ai](https://docs.pipecat.ai)
- **Genesys Cloud Documentation**: [Audio Connector overview](https://help.genesys.cloud/319987)
