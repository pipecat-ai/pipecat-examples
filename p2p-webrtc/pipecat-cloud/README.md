# Voice Bot Starter

A voice-based conversational agent built with Pipecat using `SmallWebRTCTransport`.

Any Pipecat bot that uses `SmallWebRTCTransport` can connect to WhatsApp voice calling, simply configure WhatsApp as described here:
- 👉 [**Pipecat WhatsApp Business Calling API**](https://docs.pipecat.ai/guides/features/whatsapp)  

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

## Run Your Bot Locally

Start your bot:

```bash
uv run bot.py
```

Then open **[http://localhost:7860](http://localhost:7860)** and click **Connect** to start talking to your bot.

> The first startup can take up to ~20 seconds as Pipecat downloads required models and dependencies.

By default, this uses the **SmallWebRTC** prebuilt web UI for quick local testing.

---

### Testing with WhatsApp

If you want to test **WhatsApp calling** instead of the web UI, follow these steps:

1. **Expose your local server** using [ngrok](https://ngrok.com/) or a similar tunneling tool:

   ```bash
   ngrok http --domain=YOUR_NGROK_DOMAIN http://localhost:7860
   ```

2. **Copy the generated HTTPS URL** and set your WhatsApp webhook to:

   ```
   https://YOUR_NGROK_DOMAIN/whatsapp
   ```

   > ✅ **Important:** Always include the `/whatsapp` path at the end of your webhook URL.

3. **Configure your webhook** in your WhatsApp Business account, following the Pipecat documentation:  
   👉 [Configure Webhook — Pipecat WhatsApp Guide](https://docs.pipecat.ai/guides/features/whatsapp#2-configure-webhook)

Once configured, you can make a WhatsApp voice call to your **registered business number** — your Pipecat bot will automatically answer!

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

## Configure WhatsApp Webhook for Production

Before you can receive WhatsApp voice calls in production, you must **set up your webhook** in your WhatsApp Business account.  

Follow the official Pipecat documentation for step-by-step instructions:  
👉 [Configure Webhook — Pipecat WhatsApp Guide](https://docs.pipecat.ai/guides/features/whatsapp#2-configure-webhook)

When configuring for production, use the following format for your webhook URL:
```
https://api.pipecat.daily.co/v1/public/webhooks/$ORGANIZATION_NAME/$AGENT_NAME/whatsapp
```

> ✅ **Tip:**  
> - Replace `$ORGANIZATION_NAME` and `$AGENT_NAME` with the values from your Pipecat Cloud deployment.  
> - Ensure the URL ends with `/whatsapp` — this path is required for correct webhook routing.

---

## Call Your WhatsApp Bot

Once deployed, simply call your registered **WhatsApp Business number** from the WhatsApp app.  
Your Pipecat bot will automatically answer and start the conversation.

---

## Resources

- [Pipecat Documentation](https://docs.pipecat.ai)
- [Deepgram API](https://developers.deepgram.com)
- [OpenAI API](https://platform.openai.com/docs)
- [Cartesia API](https://cartesia.ai/docs)

---
