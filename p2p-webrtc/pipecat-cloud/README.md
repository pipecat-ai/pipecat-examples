# Voice Bot Starter

A voice-based conversational agent built with Pipecat using `SmallWebRTCTransport`.

---

## Features

- **Real-time voice conversations** powered by:
  - [Deepgram](https://deepgram.com) (Speech-to-Text, STT)
  - [OpenAI](https://openai.com) (Language Model, LLM)
  - [Cartesia](https://cartesia.ai) (Text-to-Speech, TTS)
- **Voice Activity Detection** with [Silero](https://github.com/snakers4/silero-vad)
- **Natural interruptions** – the bot can stop speaking when you talk

---

## Required API Keys

Before running the bot, set these environment variables:

- `OPENAI_API_KEY`
- `DEEPGRAM_API_KEY`
- `CARTESIA_API_KEY`

---

## Setup

1. **Install dependencies** inside a virtual environment:

    ```bash
    uv sync
    ```

2. **Configure environment variables:**

    ```bash
    cp env.example .env
    # Open .env and add your API keys
    ```

---

## Environment Configuration

The bot supports two deployment modes via the `ENV` variable:

### 🖥️ Local Development (`ENV=local`)

- Default mode for testing and iteration on your machine.

### Production (`ENV=production`)

- Use this mode when deploying to **Pipecat Cloud**.

---

## Running Locally

Start the outbound bot server:

```bash
uv run bot.py
```

The server will start on **port 7860**.

---

## Deploying to Production

1. Update your production `.env` file with the Pipecat Cloud details:

    ```bash
    # Set to production mode
    ENV=production

    # Keep your existing AI service keys
    ```

2. Follow the official [Pipecat Quickstart Guide](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) to deploy your bot to **Pipecat Cloud**.

---

## Resources

- [Pipecat Documentation](https://docs.pipecat.ai)
- [Deepgram API](https://developers.deepgram.com)
- [OpenAI API](https://platform.openai.com/docs)
- [Cartesia API](https://cartesia.ai/docs)

---
