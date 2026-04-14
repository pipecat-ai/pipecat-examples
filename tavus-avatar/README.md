# Tavus Avatar

This example demonstrates how to build an AI-powered conversational avatar using [Tavus](https://www.tavus.io/) and Pipecat. Tavus generates realistic talking avatar video in real-time, synchronized with your text-to-speech output.

There are two approaches to integrating Tavus with Pipecat, each provided as a separate project:

## Two Integration Modes

### 1. Transport (`transport/`)

Uses `TavusTransport` as the transport layer. Tavus manages the video room directly — there is no separate Daily or WebRTC transport. When the bot connects, an `on_connected` event fires and the **conversation URL** is logged to the console. Copy this URL and open it in your browser to join the avatar conversation.

### 2. Video Service (`video_service/`)

Uses `TavusVideoService` as a video processing service within a standard Daily or WebRTC transport pipeline. When using the WebRTC transport, it runs a local web server — open your browser at the URL below. When using Daily transport, you can join the Daily room directly instead.

```
http://localhost:7860/client
```

## Prerequisites

- Docker
- Make
- [Tavus Account](https://platform.tavus.io/auth/sign-up?plan=free) — API key and a trained Replica ID
- [Deepgram](https://deepgram.com/) API key (STT)
- [Cartesia](https://cartesia.ai/) API key (TTS)
- [Google AI](https://ai.google.dev/) API key (LLM)

## Quick Start

Both projects use Docker and a Makefile. The steps are the same for each:

1. **Navigate to the project directory**

   ```bash
   cd transport/
   # or
   cd video_service/
   ```

2. **Set up environment variables**

   ```bash
   cp .env.example .env
   # Edit .env and fill in your API keys
   ```

3. **Run the bot**

   ```bash
   make run
   ```

   This will generate the lockfile, build the Docker image, and start the container.

### Accessing the conversation

- **Transport**: Check the container logs (`make logs`) for the conversation URL:

  ```
  conversation_url: https://tavus.daily.co/<room-name>
  ```

  Open this URL in your browser to join the room and talk to the avatar.

- **Video Service**: Open [http://localhost:7860/client](http://localhost:7860/client) in your browser.

## Other Makefile Commands

| Command      | Description                              |
| ------------ | ---------------------------------------- |
| `make build` | Build the Docker image                   |
| `make run`   | Build and run the container              |
| `make stop`  | Stop and remove the container            |
| `make logs`  | Tail the container logs                  |
| `make clean` | Stop the container and remove the image  |

## Learn More

- [Pipecat Docs](https://docs.pipecat.ai/api-reference/server/services/video/tavus)
- [Tavus Docs](https://docs.tavus.io/sections/integrations/pipecat)