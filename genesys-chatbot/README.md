# Genesys Voice Bot Examples

This directory contains an example of a voice bot that integrates with Genesys Cloud using Pipecat. The bot talks to callers through Audio Connector, which streams the call's audio both ways over a WebSocket.

## Examples

### 🔽 [Inbound Calling](./inbound/)

Demonstrates how to handle incoming phone calls where users call your Genesys Cloud number and interact with a voice bot.

### 🔼 Outbound Calling

The same bot can handle outbound calls, but Genesys Cloud places them, not the bot. Genesys has no API that dials a single number into a flow; calls without an agent come from an outbound campaign. To have the bot call people:

1. Create an Architect **outbound call flow** with a **Call Audio Connector** action, like the inbound flow.
2. Create a **contact list** and an **agentless voice campaign** that dials it. In the campaign's **call analysis responses**, send answered calls to the outbound flow.
3. Place a call by adding a contact to the list with the Genesys Cloud API, `POST /api/v2/outbound/contactlists/{contactListId}/contacts`. With `priority=true`, the campaign dials that contact next.

To personalize the call, pass the contact's columns to the bot as **Session Variables - Inputs** on the Call Audio Connector action; the bot reads them from `serializer.input_variables`.

These steps haven't been tested end to end with this example.

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
