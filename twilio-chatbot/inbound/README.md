# Twilio Chatbot: Inbound

This project is a Pipecat-based chatbot that integrates with Twilio to handle WebSocket connections and provide real-time communication. The project includes FastAPI endpoints for starting a call and handling WebSocket connections.

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Configuration](#environment-configuration)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Accessing Call Information](#accessing-call-information)

## How It Works

When someone calls your Twilio number:

1. **Twilio calls your webhook**: `POST https://your-server.com/` with call info (CallSid, From, To)
2. **Server returns TwiML**: Tells Twilio to start a WebSocket stream to your bot
3. **WebSocket connection**: Audio streams between caller and your bot
4. **Body data**: Any query parameters in the webhook URL are passed as body data to your bot

The bot can receive custom data for personalized responses by including query parameters in the webhook URL.

## Prerequisites

### Twilio

- A Twilio account with:
  - Account SID and Auth Token
  - A purchased phone number that supports voice calls

### AI Services

- OpenAI API key for the LLM inference
- Deepgram API key for speech-to-text
- Cartesia API key for text-to-speech

### System

- Python 3.10+
- `uv` package manager
- ngrok (for local development)
- Docker (for production deployment)

## Setup

1. Set up a virtual environment and install dependencies:

   ```sh
   cd inbound
   uv sync
   ```

2. Create an .env file and add API keys:

   ```sh
   cp env.example .env
   ```

## Environment Configuration

The bot supports two deployment modes controlled by the `ENV` variable:

### Local Development (`ENV=local`)

- Uses your local server or ngrok URL for WebSocket connections
- Default configuration for development and testing
- WebSocket connections go directly to your running server

### Production (`ENV=production`)

- Uses Pipecat Cloud WebSocket URLs automatically
- Requires `AGENT_NAME` and `ORGANIZATION_NAME` from your Pipecat Cloud deployment
- Set these when deploying to production environments
- WebSocket connections route through Pipecat Cloud infrastructure

## Local Development

### Configure Twilio Webhook

1. Start ngrok:
   In a new terminal, start ngrok to tunnel the local server:

   ```sh
   ngrok http 7860
   ```

   > Tip: Use the `--subdomain` flag for a reusable ngrok URL.

2. Update the Twilio Webhook:

   - Go to your Twilio Console: https://console.twilio.com/
   - Navigate to Phone Numbers > Manage > Active numbers
   - Click on your Twilio phone number
   - In the "Voice Configuration" section:
     - Set "A call comes in" to "Webhook"
     - Enter your ngrok URL: `https://your-subdomain.ngrok.io/`
     - Ensure "HTTP POST" is selected
   - Click "Save configuration"

### Run the Local Server

`server.py` runs a FastAPI server, which Twilio uses to coordinate the inbound call. Run the server using:

```bash
uv run server.py
```

### Call your Bot

Place a call to the number associated with your bot. The bot will answer and start the conversation.

## Production Deployment

To deploy your twilio-chatbot for inbound calling, we'll use [Pipecat Cloud](https://pipecat.daily.co/).

### Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) for tips on how to create secrets, build and push a docker image, and deploy your agent to Pipecat Cloud.

### Configure Production Environment

Update your production `.env` file with the Pipecat Cloud details:

```bash
# Set to production mode
ENV=production

# Your Pipecat Cloud deployment details
AGENT_NAME=your-agent-name
ORGANIZATION_NAME=your-org-name

# Keep your existing Twilio and AI service keys
```

### Deploy the Server

The `server.py` handles inbound call webhooks and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (receives webhooks, serves TwiML responses)

When `ENV=production`, the server automatically routes WebSocket connections to your Pipecat Cloud bot.

### Update Twilio Webhook URL

Update your Twilio phone number's webhook URL to point to your production server instead of ngrok:

- Change from: `https://your-subdomain.ngrok.io/`
- To: `https://your-production-domain.com/`

> Alternatively, you can test your Pipecat Cloud deployment by running your server locally.

### Call your Bot

Place a call to the number associated with your bot. The bot will answer and start the conversation.

## Accessing Call Information in Your Bot

Your bot automatically receives call information through Twilio's `Parameters`. In your `bot.py`, you can access this information from the WebSocket connection. The Pipecat development runner extracts this data using the `parse_telephony_websocket` function. This allows your bot to provide personalized responses based on who's calling and which number they called.

## Testing

It is also possible to test the server without making phone calls by using one of these clients:

- [python](client/python/README.md): This Python client enables automated testing of the server via WebSocket without the need to make actual phone calls.
- [typescript](client/typescript/README.md): This typescript client enables manual testing of the server via WebSocket without the need to make actual phone calls.
