# Plivo Chatbot: Outbound

This project is a Pipecat-based chatbot that integrates with Plivo to make outbound calls with personalized custom data. The project includes FastAPI endpoints for initiating outbound calls and handling WebSocket connections with custom data.

## How It Works

When you want to make an outbound call:

1. **Send POST request**: `POST /start` with a phone number to call
2. **Server initiates call**: Uses Plivo's REST API to make the outbound call
3. **Call answered**: When answered, Plivo fetches XML from your server's `/answer` endpoint
4. **Server returns XML**: Tells Plivo to start a WebSocket stream to your bot
5. **WebSocket connection**: Audio streams between the called person and your bot
6. **Call information**: Phone numbers are passed via Plivo's `extraHeaders` to your bot

## Architecture

```
curl request → /start endpoint → Plivo REST API → Call initiated →
Answer XML fetched → WebSocket connection → Bot conversation
```

## Prerequisites

### Plivo

- A Plivo account with:
  - Auth ID and Auth Token
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

```bash
cd outbound
uv sync
```

2. Get your Plivo credentials:

- **Auth ID and Auth Token**: Found in your [Plivo Console](https://console.plivo.com/dashboard/)
- **Phone Number**: [Purchase a phone number](https://console.plivo.com/phone-numbers/search/) that supports voice calls

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

   Copy the ngrok URL (e.g., `https://abc123.ngrok.io`)

3. No additional Plivo configuration needed

   Unlike inbound calling, outbound calls don't require webhook configuration in the Plivo console. The server will make direct API calls to Plivo to initiate calls.

## Making an Outbound Call

With the server running and exposed via ngrok, you can initiate outbound calls:

### Basic Call

```bash
curl -X POST https://your-ngrok-url.ngrok.io/start \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890"
  }'
```

### Call with Custom Data

You can include custom data that will be available to your bot. **Note**: Plivo has character restrictions on extraHeaders - see their documentation for supported characters.

```bash
curl -X POST https://your-ngrok-url.ngrok.io/start \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "custom_data": {
      "user": {
        "id": "user123",
        "firstName": "John",
        "lastName": "Doe",
        "accountType": "premium"
      }
    }
  }'
```

**Important**: Plivo has restrictions on which characters are supported in extraHeaders. If certain characters don't appear in your bot, check Plivo's extraHeaders documentation for the current character limitations.

Replace:

- `your-ngrok-url.ngrok.io` with your actual ngrok URL
- `+1234567890` with the phone number you want to call

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

# Keep your existing Plivo and AI service keys
```

### 3. Deploy the Server

The `server.py` handles outbound call initiation and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (initiates calls, serves XML responses)

When `ENV=production`, the server automatically routes WebSocket connections to your Pipecat Cloud bot.

> Alternatively, you can test your Pipecat Cloud deployment by running your server locally.

### Call your Bot

As you did before, initiate a call via `curl` command to trigger your bot to dial a number.

## Accessing Call Information in Your Bot

Your bot automatically receives call information and custom data through Plivo's `extraHeaders`:

- **Phone Numbers**: `from` and `to` are always available
- **Custom Data**: Any data you include in the `custom_data` field

The Pipecat development runner extracts this data using the `parse_telephony_websocket` function:

```python
async def bot(runner_args: RunnerArguments):
    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)

    if transport_type == "plivo":
        # Phone numbers
        from_number = call_data["from"]
        to_number = call_data["to"]

        # Custom data
        params = call_data["custom_parameters"]
        user_id = params.get("user_id")           # "user123"
        first_name = params.get("user_firstName") # "John"
        last_name = params.get("user_lastName")   # "Doe"
        account_type = params.get("user_accountType") # "premium"

        # Use this data to personalize the conversation
        print(f"Call from {from_number} to {to_number}")
        print(f"User: {first_name} {last_name} (ID: {user_id}, Type: {account_type})")
```

This allows your bot to provide personalized responses based on the caller and context.
