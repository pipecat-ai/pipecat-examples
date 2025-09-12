# Telnyx Chatbot: Outbound

This project is a Pipecat-based chatbot that integrates with Telnyx to make outbound calls with custom data injection. The project includes FastAPI endpoints for initiating outbound calls and handling WebSocket connections with custom data passed through the `body` parameter.

## How it works

1. The server receives a POST request with a phone number and optional custom data (`body`)
2. The server encodes the custom data as base64 JSON and includes it in the TeXML URL
3. The server uses Telnyx's REST API to initiate an outbound call
4. When the call is answered, Telnyx fetches TeXML from the server (with custom data in query parameters)
5. The TeXML connects the call to a WebSocket with custom data passed through URL parameters
6. The bot receives the decoded custom data and engages in personalized conversation

## Architecture

```
curl request (with body) → /start endpoint → Telnyx REST API → Call initiated →
TeXML fetched (with body in URL) → WebSocket connection (body decoded) → Bot conversation (with custom data)
```

## Prerequisites

### Telnyx

- A Telnyx account with:
  - API Key
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

2. Get your Telnyx credentials:

- **API Key**: Found in your [Telnyx Mission Control Portal](https://portal.telnyx.com/)
- **Account SID**: Get your account_sid by running:

  ```bash
  curl -H "Authorization: Bearer YOUR_API_KEY" https://api.telnyx.com/v2/whoami
  ```

  The `organization_id` in the response is your `TELNYX_ACCOUNT_SID` which you'll add to your `.env` file.

- **Phone Number**: [Purchase a phone number](https://portal.telnyx.com/#/numbers/buy-numbers) that supports voice calls

3. Set up environment variables:

```bash
cp env.example .env
# Edit .env with your API keys
```

> Note: We'll create the TeXML application below which will provide the `TELNYX_APPLICATION_SID` for your `.env` file.

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

3. **Configure your TeXML Application**

   - Go to your TeXML configuration page: https://portal.telnyx.com/#/call-control/texml
   - Create a new TeXML app, if one doesn't exist already:
     - Add an application name
     - Under Webhooks, select POST as the "Voice Method"
     - Select "Custom URL" under Webhook URL Method
     - Enter your ngrok URL in the "Webhook URL" field (e.g. https://your-name.ngrok.io)
     - Click "Create" to save
   - Find the **Application ID** on the page. Save this as your `TELNYX_APPLICATION_SID` in your `.env` file.
   - Navigate to "Manage Numbers" (https://portal.telnyx.com/#/numbers/my-numbers) and under SIP connection, select the pencil icon to edit and select the TeXML application that you just created.

## Making an Outbound Call

With the server running and exposed via ngrok, you can initiate an outbound call to a specified number:

### Basic Call (No Custom Data)

```bash
curl -X POST https://your-ngrok-url.ngrok.io/start \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890"
  }'
```

### Call with Custom Data

```bash
curl -X POST https://your-ngrok-url.ngrok.io/start \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "body": {
      "user_id": "user123",
      "name": "John Doe",
      "account_type": "premium",
      "context": {
        "last_order": "2024-01-15",
        "total_spent": 1250.00
      }
    }
  }'
```

Replace:

- `your-ngrok-url.ngrok.io` with your actual ngrok URL
- `+1234567890` with the phone number you want to call
- Customize the `body` object with any data your bot needs for personalized conversation

### Custom Data Flow

The custom data in the `body` parameter:

1. **Gets encoded** as base64 JSON and added to the TeXML URL query parameters
2. **Passes through** Telnyx's TeXML system to the WebSocket URL
3. **Gets decoded** in the WebSocket endpoint and made available to your bot
4. **Enables personalized** conversations based on user context, preferences, or business data

> **Note**: The `body` parameter is optional. If not provided, the bot will engage in a standard conversation without custom context.

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

# Keep your existing Telnyx and AI service keys
TELNYX_API_KEY=your_key
OPENAI_API_KEY=your_key
# ... etc
```

### 3. Deploy the Server

The `server.py` handles outbound call initiation and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (initiates calls, serves TeXML)

When `ENV=production`, the server automatically routes WebSocket connections to your Pipecat Cloud bot.

> Alternatively, you can test your Pipecat Cloud deployment by running your server locally.

### Call your Bot

As you did before, initiate a call via `curl` command to trigger your bot to dial a number. You can include custom data in the `body` parameter for personalized conversations:

```bash
curl -X POST https://your-production-server.com/start \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "body": {
      "customer_id": "cust_789",
      "subscription_status": "active",
      "support_tier": "premium"
    }
  }'
```

The custom data will be automatically routed through Pipecat Cloud to your deployed bot for personalized interactions.
