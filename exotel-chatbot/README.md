# Exotel Voice Bot Examples

This repository contains examples of voice bots that integrate with Exotel's Voice API using Pipecat. The examples demonstrate both inbound and outbound calling scenarios using Exotel's WebSocket streaming for real-time audio processing.

## Examples

### 🔽 [Inbound Calling](./inbound/)

Demonstrates how to handle incoming phone calls where users call your Exotel number and interact with a voice bot.

### 🔼 [Outbound Calling](./outbound/)

Shows how to initiate outbound phone calls programmatically where your bot calls users.

## Architecture

Both examples use the same core architecture:

```
Phone Call ↔ Exotel ↔ WebSocket Stream ↔ Pipecat ↔ AI Services
```

**Components:**

- **Exotel**: Handles phone call routing and audio transport
- **WebSocket Stream**: Real-time bidirectional audio streaming
- **Pipecat**: Audio processing pipeline and AI service orchestration
- **AI Services**: OpenAI (LLM), Deepgram (STT), Cartesia (TTS)

## Getting Help

- **Detailed Setup**: See individual README files in `inbound/` and `outbound/` directories
- **Pipecat Documentation**: [docs.pipecat.ai](https://docs.pipecat.ai)
- **Exotel Documentation**: [https://support.exotel.com/support/solutions/articles/3000108630-working-with-the-stream-and-voicebot-applet](https://support.exotel.com/support/solutions/articles/3000108630-working-with-the-stream-and-voicebot-applet)
