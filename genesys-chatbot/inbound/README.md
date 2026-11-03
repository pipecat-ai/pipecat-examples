# Genesys Chatbot: Inbound

This project is a Pipecat-based chatbot that answers inbound phone calls in Genesys Cloud through Audio Connector, which streams the call's audio both ways over a WebSocket.

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Customizing your Bot](#customizing-your-bot)

## How It Works

When someone calls your Genesys Cloud number:

1. **Genesys runs your call flow**: The number's call route sends the call to an Architect inbound call flow, whose **Call Audio Connector** action hands the call to your Audio Connector integration.
2. **Genesys opens a WebSocket to your bot**: Genesys connects to the integration's Base Connection URI with the action's Connector ID appended, and sends your API key in the `X-API-KEY` header. The bot connects through a generic WebSocket endpoint, the development runner's locally or Pipecat Cloud's in production, and checks the key before it starts.
3. **The bot opens the session**: Genesys sends an `open` message with the caller's details, and the bot answers it with `GenesysAudioHookSerializer` before starting its pipeline. From then on, the serializer answers Genesys's `ping` and `close` messages and converts audio between Genesys's 8 kHz μ-law and the pipeline.
4. **Bot starts responding**: When the pipeline starts, the bot greets the caller. When the bot's session ends, the call continues in the Architect flow after the Call Audio Connector action.

## Prerequisites

### Genesys Cloud

- A Genesys Cloud org with:
  - The **Audio Connector** premium app, installed from AppFoundry
  - Permission to manage integrations, Architect flows and call routing
  - A phone number, for example one bought in **Digital and Telephony > Telephony > Number Management**

### AI Services

- OpenAI API key for the LLM inference
- Deepgram API key for speech-to-text
- Cartesia API key for text-to-speech

### System

- Python 3.11+
- `uv` package manager
- ngrok (for local development), with a reserved domain so the integration's URL stays the same
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

3. Generate the credentials Genesys will use to connect, and add them to `.env`:

   ```sh
   echo "GENESYS_API_KEY=$(openssl rand -hex 24)" >> .env
   echo "GENESYS_CLIENT_SECRET=$(openssl rand -base64 32)" >> .env
   ```

## Local Development

### Run your bot and ngrok

1. Run your bot with the `websocket` transport:

   ```sh
   uv run bot.py -t websocket
   ```

   > Note: This bot uses [Pipecat's development runner](https://docs.pipecat.ai/server/utilities/runner/guide), which runs a FastAPI server. Its `/ws-client` endpoint passes the WebSocket to the bot without interpreting Genesys's messages, the same way Pipecat Cloud's generic WebSocket endpoint does.

2. In a new terminal, start ngrok with your reserved domain:

   ```sh
   ngrok http 7860 --url=https://your-domain.ngrok.app
   ```

### Configure Genesys Cloud

The menu paths below are from the Genesys Cloud **Menu** at the top left. You can also find each page by name with the search bar.

1. Create the Audio Connector integration:

   - Go to **IT and Integrations > Integrations** and click **Add integration**
   - Find **Audio Connector** and click **Install**
   - On the **Details** tab, give the integration a name
   - On **Configuration > Properties**, set **Base Connection URI** to `wss://your-domain.ngrok.app/ws-client`
   - On **Configuration > Credentials**, click **Configure** and enter `GENESYS_API_KEY` as the **API Key** and `GENESYS_CLIENT_SECRET` as the **Client Secret** from your `.env`
   - Click **Save & Activate**

2. Create the call flow:

   - Go to **Orchestration > Architect**, open **Inbound Call** flows, and click **Add**
   - Add a reusable task, then drag **Bot > Call Audio Connector** into it
   - Select your integration and set **Connector ID** to any value, for example `local`; Genesys connects to `wss://your-domain.ngrok.app/ws-client/local`, and the runner ignores the last segment
   - Drag **Disconnect > Disconnect** after the action
   - Open the task's menu and choose **Set this as the starting task**, then clear its **Initial Greeting** so the bot speaks first
   - Click **Publish**

3. Route your number to the flow:

   - Search for **Call Routing** and click **Add**
   - Name the call route, set **Route to** to your flow, and add your number under **Inbound numbers**
   - Click **Create**

### Call your Bot

Place a call to your Genesys Cloud number. The bot will answer and start the conversation.

## Production Deployment

To deploy your bot for inbound calling, we'll use [Pipecat Cloud](https://pipecat.daily.co/) and its [generic WebSocket endpoint](https://docs.pipecat.ai/pipecat-cloud/guides/generic-websocket), which relays Genesys's messages to the bot unchanged.

### Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) for tips on how to create secrets, build and push a docker image, and deploy your agent to Pipecat Cloud. Include `GENESYS_API_KEY` in the agent's secret set.

`pcc-deploy.toml` sets `websocket_auth = "none"`, because Genesys connects directly and can't request a session token first. The bot's `X-API-KEY` check takes the token's place.

### Update the Genesys integration for production

Point the integration and the flow at Pipecat Cloud's generic WebSocket endpoint:

- Set the integration's **Base Connection URI** to `wss://api.pipecat.daily.co/ws/generic`
- Set the Call Audio Connector action's **Connector ID** to `AGENT_NAME.ORGANIZATION_NAME`, then publish the flow

Genesys connects to `wss://api.pipecat.daily.co/ws/generic/AGENT_NAME.ORGANIZATION_NAME`, where:

- `AGENT_NAME` is the name of the agent that you deployed to Pipecat Cloud
- `ORGANIZATION_NAME` is the name of your Pipecat Cloud organization

Genesys only sends calls to an integration that is active, so reactivate the integration after changing its configuration.

> If the bot is deployed to a region other than us-west (default), add the region to the URI. For example, if deployed in `eu-central`, the URI becomes `wss://eu-central.api.pipecat.daily.co/ws/generic`.

Genesys also signs each connection request with the Client Secret. This example only checks the API key, so verify the signature before you rely on it in production.

## Customizing your Bot

When Genesys opens the session, the serializer stores what Genesys sent about the call:

- `serializer.participant` holds the caller's details, such as `ani` (the caller's number) and `dnis` (the number they called)
- `serializer.input_variables` holds the **Session Variables - Inputs** set on the Call Audio Connector action
- `serializer.set_output_variables({...})` returns values to the flow as **Session Variables - Outputs**, so the flow can route the call after the bot finishes

Genesys pauses the audio stream on its own, for example while the caller is on hold, and the serializer fires `on_paused` and `on_resumed`. To pause or resume it yourself, queue `OutputTransportMessageUrgentFrame(message=serializer.create_pause_request())` or `serializer.create_resume_request()`.
