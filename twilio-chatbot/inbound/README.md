# Twilio Chatbot: Inbound

This project is a Pipecat-based chatbot that integrates with Twilio to handle inbound phone calls via WebSocket connections and provide real-time voice conversations.

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Configuration](#environment-configuration)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Customizing your Bot](#customizing-your-bot)
- [Testing](#testing)

## How It Works

When someone calls your Twilio number:

1. **Twilio sends WebSocket messages**: Twilio processes the associated TwiML Bin and starts a WebSocket stream to your bot (local or Pipecat Cloud)
2. **Parse the WebSocket messages**: Your bot parses the WebSocket connection messages to set up the corresponding Pipecat transport
3. **(Optional) Look up the caller**: Optionally, look up the caller using Twilio's REST API to retrieve custom information about the call and personalize your bot's behavior
4. **Bot starts responding**: Once the pipeline is started, your bot will initiate the conversation

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
- Requires the agent name and organization name from your Pipecat Cloud deployment
- Set these when deploying to production environments
- WebSocket connections route through Pipecat Cloud infrastructure

## Local Development

### Configure Twilio

1. Start ngrok:
   In a new terminal, start ngrok to tunnel the local server:

   ```sh
   ngrok http 7860
   ```

   > Tip: Use the `--subdomain` flag for a reusable ngrok URL.

2. Create a TwiML Bin:

   - Go to your Twilio Console: https://console.twilio.com/
   - Navigate to TwiML Bins > My TwiML Bins
   - Click the `+` to create a new TwiML Bin
   - Name your bin and add the TwiML containing your ngrok URL:

     ```xml
     <?xml version="1.0" encoding="UTF-8"?>
     <Response>
     <Connect>
        <Stream url="wss://your-url.ngrok.io/ws" />
     </Connect>
     </Response>
     ```

   - Click "Save"

3. Assign the TwiML Bin to your number:

   - Navigate to Phone Numbers > Manage > Active numbers
   - Click on your Twilio phone number
   - In the "Voice Configuration" section:
     - Set "A call comes in" to "TwiML Bin"
     - Select the name of your TwiML Bin from step 2
   - Click "Save configuration"

### Run your Bot

Run your bot by passing in the `twilio` command line arg

```bash
uv run bot.py -t twilio
```

> Note: This bot uses [Pipecat's development runner](https://docs.pipecat.ai/server/utilities/runner/guide), which runs a FastAPI server that handles and routes incoming WebSocket messages to your bot.

### Call your Bot

Place a call to the number associated with your bot. The bot will answer and start the conversation.

## Production Deployment

To deploy your twilio-chatbot for inbound calling, we'll use [Pipecat Cloud](https://pipecat.daily.co/).

### Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) for tips on how to create secrets, build and push a docker image, and deploy your agent to Pipecat Cloud.

### Update TwiML for Production

Update your TwiML Bin to point directly to Pipecat Cloud's WebSocket endpoint.

In your Twilio Console, update the TwiML Bin to include your Pipecat Cloud agent and organization name:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://api.pipecat.daily.co/ws/twilio">
      <Parameter name="_pipecatCloudServiceHost"
         value="AGENT_NAME.ORGANIZATION_NAME"/>
    </Stream>
  </Connect>
</Response>
```

where:

- `AGENT_NAME` is the name of the agent that you deployed to Pipecat Cloud
- `ORGANIZATION_NAME` is the name of your Pipecat Cloud organization

### Call your Bot

Place a call to the number associated with your bot. The bot will answer and start the conversation.

## Customizing your Bot

The `bot.py` example file is configured to look up the caller's phone number by calling Twilio's REST API using the Call SID. With this information, you can:

- Perform a lookup in your own database to retrieve customer information
- Personalize the bot's greeting and behavior based on the caller

## Testing

It is also possible to test the server without making phone calls by using one of these clients:

- [python](client/python/README.md): This Python client enables automated testing of the server via WebSocket without the need to make actual phone calls.
- [typescript](client/typescript/README.md): This typescript client enables manual testing of the server via WebSocket without the need to make actual phone calls.
