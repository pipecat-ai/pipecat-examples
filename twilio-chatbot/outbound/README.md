# Twilio Chatbot: Outbound

This project is a Pipecat-based chatbot that integrates with Twilio to make outbound calls with personalized call information. The project includes FastAPI endpoints for initiating outbound calls and handling WebSocket connections with call context.

## How It Works

When you want to make an outbound call:

1. **Send POST request**: `POST /dialout` with a phone number to call
2. **Server initiates call**: Uses Twilio's REST API to make the outbound call
3. **Call answered**: When answered, Twilio fetches TwiML from your server's `/twiml` endpoint
4. **Server returns TwiML**: Tells Twilio to start a WebSocket stream to your bot
5. **WebSocket connection**: Audio streams between the called person and your bot
6. **Call information**: Phone numbers are passed via TwiML Parameters to your bot

## Architecture

```
curl request → /dialout endpoint → Twilio REST API → Call initiated →
TwiML fetched → WebSocket connection → Bot conversation
```

## Prerequisites

### Twilio

- A Twilio account with:
  - Account SID and Auth Token
  - A purchased phone number that supports voice calls

### AI Services

- Google API key for the LLM inference
- Deepgram API key for speech-to-text
- Cartesia API key for text-to-speech

### System

- Python 3.10+
- `uv` package manager
- ngrok (for local development)
- Docker (for production deployment)

## Setup

1. Set up a virtual environment and install dependencies:

```bash
cd outbound
uv sync
```

2. Get your Twilio credentials:

- **Account SID & Auth Token**: Found in your [Twilio Console Dashboard](https://console.twilio.com/)
- **Phone Number**: [Purchase a phone number](https://console.twilio.com/us1/develop/phone-numbers/manage/search) that supports voice calls

3. Set up environment variables:

```bash
cp env.example .env
# Edit .env with your API keys
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

1. Start the outbound bot server:

   ```bash
   uv run server.py
   ```

The server will start on port 7860.

2. Using a new terminal, expose your server to the internet (for development)

   ```bash
   ngrok http 7860
   ```

   > Tip: Use the `--subdomain` flag for a reusable ngrok URL.

   Copy the ngrok URL (e.g., `https://abc123.ngrok.io`) and update `LOCAL_SERVER_URL` in your `.env` file.

3. No additional Twilio configuration needed

   Unlike inbound calling, outbound calls don't require webhook configuration in the Twilio console. The server will make direct API calls to Twilio to initiate calls.

## Making an Outbound Call

With the server running and exposed via ngrok, you can initiate outbound calls:

```bash
curl -X POST https://your-ngrok-url.ngrok.io/dialout \
  -H "Content-Type: application/json" \
  -d '{
    "to_number": "+15551234567",
    "from_number": "+15559876543"
  }'
```

Replace:

- `your-ngrok-url.ngrok.io` with your actual ngrok URL
- `+15551234567` with the phone number to call (E.164 format)
- `+15559876543` with your Twilio phone number (E.164 format)

> Note: the `from_number` must be a phone number owned by your Twilio account

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

# Keep your existing Twilio and AI service keys
```

### 3. Deploy the Server

The `server.py` handles outbound call initiation and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (initiates calls, serves TwiML responses)

When `ENV=production`, the server automatically routes WebSocket connections to your Pipecat Cloud bot.

> Alternatively, you can test your Pipecat Cloud deployment by running your server locally.

### Call your Bot

As you did before, initiate a call via `curl` command to trigger your bot to dial a number.

## Accessing Call Information in Your Bot

Your bot automatically receives call information through Twilio Stream Parameters. In this example, the phone numbers (`to_number` and `from_number`) are passed as parameters and extracted by the `parse_telephony_websocket` function.

You can extend the `DialoutRequest` model in `server_utils.py` to include additional custom data (customer info, campaign data, etc.) and pass it through as stream parameters for personalized conversations. See `bot.py` for implementation details.
