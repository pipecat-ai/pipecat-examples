# Exotel Chatbot: Inbound

This project is a Pipecat-based chatbot that integrates with Exotel to handle WebSocket connections and provide real-time communication. The project includes FastAPI endpoints for handling WebSocket voice streaming using Exotel's Voicebot Applet.

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Configuration](#environment-configuration)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Accessing Call Information](#accessing-call-information)

## How It Works

When someone calls your Exotel number:

1. **Exotel routes the call**: Through your configured App Bazaar application
2. **Voicebot Applet activates**: Connects to your WebSocket endpoint
3. **WebSocket connection**: Audio streams between caller and your bot
4. **Call information**: Phone numbers and custom parameters are passed via WebSocket messages

The bot automatically receives the caller's and called phone numbers for personalized responses.

## Prerequisites

### Exotel

- An Exotel account with:
  - Voice streaming enabled (contact support if not available)
  - A purchased phone number that supports voice calls

### AI Services

- OpenAI API key for the bot's intelligence
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

### Configure Exotel App Bazaar Application

1. Start ngrok:
   In a new terminal, start ngrok to tunnel the local server:

   ```sh
   ngrok http 7860
   ```

   > Tip: Use the `--subdomain` flag for a reusable ngrok URL.

2. Purchase a number (if you haven't already):

   - Log in to the Exotel dashboard: https://my.exotel.com/
   - Navigate to ExoPhones and purchase a number
   - Note: You may need to complete KYC verification for your account

3. Enable Voice Streaming (if not already enabled):

   Voice streaming may not be enabled by default on all accounts:

   - Contact Exotel support at `hello@exotel.com`
   - Request: "Enable Voicebot Applet for voice streaming for account [Your Account SID]"
   - Include your use case: "AI voice bot integration"

4. Create Custom App in App Bazaar:

   - Navigate to App Bazaar in your Exotel dashboard
   - Click "Create Custom App" or edit an existing app
   - Build your call flow:

     **Add Voicebot Applet**

     - Drag the "Voicebot" applet to your call flow
     - Configure the Voicebot Applet:
       - **URL**: `wss://your-ngrok-url.ngrok.io/ws`
       - **Record**: Enable if you want call recordings

     **Optional: Add Hangup Applet**

     - Drag a "Hangup" applet at the end to properly terminate calls

   - Your final flow should look like:
     ```
     Call Start → [Voicebot Applet] → [Hangup Applet]
     ```

5. Link Number to App:

   - Navigate to "ExoPhones" in your dashboard
   - Find your purchased number
   - Click the edit/pencil icon
   - Under "App", select the custom app you just created
   - Save the configuration

### Run your Bot

The bot.py file uses the Pipecat development runner, which runs a FastAPI server in order to receive connections.

1. To get started, we'll run our bot.py file:

```bash
uv run bot.py --transport exotel --proxy your_ngrok_url
```

> Replace `your_ngrok_url` with your ngrok URL (e.g. your-subdomain.ngrok.io)

### Call your Bot

Place a call to the number associated with your bot. The bot will answer and start the conversation.

## Production Deployment

### 1. Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) to deploy your bot to Pipecat Cloud.

### 2. Configure Production Environment

Update your production `.env` file with the Pipecat Cloud details:

```bash
# Set to production mode
ENV=production

# Your Pipecat Cloud deployment details
AGENT_NAME=your-agent-name
ORGANIZATION_NAME=your-org-name

# Keep your existing Exotel and AI service keys
```

### 3. Deploy the Server

The `server.py` handles inbound call webhooks and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (receives webhooks, serves responses)

When `ENV=production`, the server automatically routes WebSocket connections to your Pipecat Cloud bot.

### 4. Update Exotel App Bazaar Configuration

Update your Voicebot Applet configuration to use your production server:

- Change the WebSocket URL from your ngrok URL to your production server URL — this should be the Pipecat Cloud base URL:

  ```bash
  wss://api.pipecat.daily.co/ws/exotel?serviceHost=AGENT_NAME.ORGANIZATION_NAME
  ```

  Replace:

  - `AGENT_NAME` with your deployed agent's name
  - `ORGANIZATION_NAME` with your organization ID

- Update custom parameters as needed for your production environment

### Call your Bot

Place a call to the number associated with your bot. The bot will answer and start the conversation.

## Accessing Call Information in Your Bot

Your bot automatically receives call information through Exotel's WebSocket messages. The server extracts the `from` and `to` phone numbers and makes them available to your bot.

In your `bot.py`, you can access this information from the WebSocket connection. The Pipecat development runner extracts this data using the `parse_telephony_websocket` function. This allows your bot to provide personalized responses based on who's calling and which number they called.
