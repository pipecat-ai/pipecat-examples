# Daily PSTN dial-out simple chatbot

This project demonstrates how to create a voice bot that uses Daily's PSTN capabilities to make calls to phone numbers.

## How It Works

1. The server receives a request with the phone number to dial out to
2. The server creates a Daily room with SIP capabilities
3. The server starts the bot process (locally or via Pipecat Cloud based on ENV)
4. When the bot has joined, it starts the dial-out process and rings the number provided
5. The user answers the phone and is brought into the call
6. The end user and bot are connected, and the bot handles the conversation

## Prerequisites

### Daily

- A Daily account with an API key (or Daily API key from Pipecat Cloud account)
- A phone number purchased through Daily
- Dial-out must be enabled on your domain. Find out more by reading this [document and filling in the form](https://docs.daily.co/guides/products/dial-in-dial-out#main)

### AI Services

- Deepgram API key for speech-to-text
- OpenAI API key for the LLM inference
- Cartesia API key for text-to-speech

### System

- Python 3.10+
- `uv` package manager (recommended) or pip
- ngrok (for local development)
- Docker (for production deployment)

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

3. Buy a phone number

   Instructions on how to do that can be found at this [docs link](https://docs.daily.co/reference/rest-api/phone-numbers/buy-phone-number)

4. Request dial-out enablement

   For compliance reasons, to enable dial-out for your Daily account, you must request enablement via the form. You can find out more about dial-out, and the form at the [link here](https://docs.daily.co/guides/products/dial-in-dial-out#main)

## Environment Configuration

The bot supports two deployment modes controlled by the `ENV` variable:

### Local Development (`ENV=local`)

- Uses your local server for handling dial-out requests and starting the bot
- Default configuration for development and testing

### Production (`ENV=production`)

- Bot is deployed to Pipecat Cloud; requires `PIPECAT_API_KEY` and `PIPECAT_AGENT_NAME`
- Set these when deploying to production environments
- Your FastAPI server runs either locally or deployed to your infrastructure

## Run the Bot Locally

1. Start the server:

   ```bash
   uv run server.py
   ```

2. Test the dial-out functionality

   With server.py running, send the following curl command from your terminal:

   ```bash
   curl -X POST "http://localhost:7860/start" \
     -H "Content-Type: application/json" \
     -d '{
       "dialout_settings": {
         "phone_number": "+1234567890"
       }
     }'
   ```

   The server should create a room, the bot will join and then ring the number provided. Answer the call to speak with the bot.

## Production Deployment

You can deploy your bot to Pipecat Cloud and server to your infrastructure to run this bot in a production environment.

#### Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) for tips on how to create secrets, build and push a docker image, and deploy your agent to Pipecat Cloud.

You'll only deploy your `bot.py` file.

#### Deploy the Server

The `server.py` handles dial-out requests and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (receives requests and starts the bot)

#### Environment Variables for Production

Add these to your production environment:

```bash
ENV=production
PIPECAT_API_KEY=your_pipecat_cloud_api_key
PIPECAT_AGENT_NAME=your-agent-name
```

The server automatically detects the environment and routes bot starting requests accordingly.

## Troubleshooting

### I get an error about dial-out not being enabled

- Check that your room has `enable_dialout=True` set
- Check that your meeting token is an owner token (The bot does this for you automatically)
- Check that you have purchased a phone number to ring from
- Check that the phone number you are trying to ring is correct, and is a US or Canadian number.

### Call connects but no bot is heard

- Ensure your Daily API key is correct and has SIP capabilities
- Verify that the Cartesia API key and voice ID are correct

### Bot starts but disconnects immediately

- Check the Daily logs for any error messages
- Ensure your server has stable internet connectivity
