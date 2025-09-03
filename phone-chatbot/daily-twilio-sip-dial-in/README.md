# Daily + Twilio SIP dial-in Voice Bot

This project demonstrates how to create a voice bot that can receive phone calls via Twilio and use Daily's SIP capabilities to enable voice conversations. It supports both local development and Pipecat Cloud deployment.

## How It Works

1. Twilio receives an incoming call to your phone number
2. Twilio calls your webhook server (`/call` endpoint)
3. The server creates a Daily room with SIP capabilities
4. The server starts the bot with the room details and call information
5. The caller is put on hold with music, in this case a US ringtone
6. The bot joins the Daily room and signals readiness
7. Twilio forwards the call to Daily's SIP endpoint
8. The caller and bot are connected, and the bot handles the conversation

## Prerequisites

- A Daily account with an API key for room creation
- A Twilio account with a phone number that supports voice
- OpenAI API key for the bot's intelligence
- Cartesia API key for text-to-speech
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager installed

## Setup

1. Create a virtual environment and install dependencies

```bash
uv sync
```

2. Set up environment variables

Copy the example file and fill in your API keys:

```bash
cp .env.example .env
# Edit .env with your API keys
```

3. Configure your Twilio webhook

In the Twilio console:

- Go to your phone number's configuration
- Set the webhook for "A call comes in" to your server's URL + "/call"
- For local testing, you can use ngrok to expose your local server

```bash
ngrok http 7860
# Then use the provided URL (e.g., https://abc123.ngrok.io/call) in Twilio
```

## Running the Bot

### Local Development

Running the bot locally requires two terminal windows:

1. In terminal 1, start the server (handles both webhooks and bot starting):

   ```bash
   uv run server.py
   ```

2. In terminal 2, use ngrok to expose the server:

   ```bash
   ngrok http 7860
   ```

3. Call the Twilio phone number to talk to your bot.

## Deploy to Pipecat Cloud

### Prerequisites

Configure your machine with the required Pipecat Cloud and Docker prerequisites. See the [Quickstart](https://docs.pipecat.ai/getting-started/quickstart#prerequisites-2) guide for details.

### Configure your Deployment

Update the `pcc-deploy.toml` file with:

- `agent_name`: Your bot’s name in Pipecat Cloud
- `image`: The Docker image to deploy (format: username/image:version)
- `image_credentials`: Your Docker registry image pull secret to authenticate your image pull
- `secret_set`: Where your API keys are stored securely

### Create a Secrets Set

Create the secrets set from your .env file:

```bash
uv run pcc secrets set quickstart-secrets --file .env
```

### Build and deploy

Build your Docker image and push to Docker Hub:

```bash
uv run pcc docker build-push
```

Deploy to Pipecat Cloud:

```bash
uv run pcc deploy
```

### Run your Server

The `server.py` file is a FastAPI server that handles the Twilio incoming webhook. For a production deployment, this server should be run separately from your Pipecat Cloud bot. This would be a server environment that runs the FastAPI server persistently, so that it can handle inbound requests.

For the sake of testing the Pipecat Cloud deployment, we'll run the server locally and expose it to the internet via ngrok:

In terminal 1:

```bash
uv run server.py
```

In terminal 2:

```bash
ngrok http 7860
```

> Note: Ensure that the `ENVIRONMENT` variable is set to `production` to use the Pipecat Cloud hosted bot.

### Test your Deployment

Call your Twilio number to talk to your bot!
