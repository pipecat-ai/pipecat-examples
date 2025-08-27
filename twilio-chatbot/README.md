# Twilio Voice Bot Examples

This repository contains examples of voice bots that integrate with Twilio's Programmable Voice API using Pipecat. The examples demonstrate both inbound and outbound calling scenarios using Twilio Media Streams for real-time audio processing.

## Examples

### 🔽 [Inbound Calling](./inbound/)

Demonstrates how to handle incoming phone calls where users call your Twilio number and interact with a voice bot.

### 🔼 [Outbound Calling](./outbound/)

Shows how to initiate outbound phone calls programmatically where your bot calls users.

## Architecture

Both examples use the same core architecture:

```
Phone Call ↔ Twilio ↔ Media Streams (WebSocket) ↔ Pipecat ↔ AI Services
```

**Components:**

- **Twilio**: Handles phone call routing and audio transport
- **Media Streams**: Real-time bidirectional audio over WebSocket
- **Pipecat**: Audio processing pipeline and AI service orchestration
- **AI Services**: OpenAI (LLM), Deepgram (STT), Cartesia (TTS)

## Getting Help

- **Detailed Setup**: See individual README files in `inbound/` and `outbound/` directories
- **Pipecat Documentation**: [docs.pipecat.ai](https://docs.pipecat.ai)
- **Twilio Documentation**: [twilio.com/docs](https://www.twilio.com/docs)
