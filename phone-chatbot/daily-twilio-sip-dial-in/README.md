# Daily + Twilio SIP dial-in Voice Bot

This project demonstrates how to create a voice bot that can receive phone calls via Twilio and use Daily's SIP capabilities to enable voice conversations.

## How It Works

1. Twilio receives an incoming call to your phone number
2. Twilio calls your webhook server (`/call` endpoint in `server.py`)
3. The server creates a Daily room with SIP capabilities
4. The server starts the bot process with the room details (locally or via Pipecat Cloud)
5. The caller is put on hold with music (a US ringtone in this example)
6. The bot joins the Daily room and signals readiness
7. Twilio forwards the call to Daily's SIP endpoint
8. The caller and the bot are connected, and the bot handles the conversation

## Project Structure

This example is organized to be production-ready and easy to customize:

- **`server.py`** - FastAPI webhook server that handles incoming calls

  - Receives Twilio call webhooks
  - Creates Daily rooms with SIP capabilities
  - Routes to local or production bot deployment
  - Uses shared HTTP session for optimal performance

- **`server_utils.py`** - Utility functions for Twilio and Daily API interactions

  - Data models for call data and agent requests
  - Room creation logic
  - Bot starting logic (production and local modes)
  - Easy to extend with custom business logic

- **`bot.py`** - The voice bot implementation
  - Handles the conversation with the caller
  - Deployed to Pipecat Cloud in production or run locally for development

## Prerequisites

### Twilio

- A Twilio account with a phone number that supports voice
- Twilio Account SID and Auth Token

### Daily

- A Daily account with an API key (or Daily API key from Pipecat Cloud account)

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
ngrok http 8080
# Then use the provided URL (e.g., https://abc123.ngrok.io/call) in Twilio
```

## Environment Configuration

The bot supports two deployment modes controlled by the `ENV` variable:

### Local Development (`ENV=local`)

- Uses your local server or ngrok URL for handling the webhook and starting the bot
- Default configuration for development and testing

### Production (`ENV=production`)

- Bot is deployed to Pipecat Cloud; requires `PIPECAT_API_KEY` and `PIPECAT_AGENT_NAME`
- Set these when deploying to production environments
- Your FastAPI server runs either locally or deployed to your infrastructure

## Run the Bot Locally

You'll need three terminal windows open:

1. Terminal 1: Start the webhook server:

   ```bash
   uv run server.py
   ```

2. Terminal 2: Start an ngrok tunnel to expose the FastAPI server running on server.py

   ```bash
   ngrok http 8080
   ```

   Important: Make sure that this URL matches the webhook URL configured in your Twilio phone number settings.

   > Tip: Use the `--subdomain` flag for a reusable ngrok link.

3. Terminal 3: Run your bot:

   ```bash
   uv run bot.py -t daily
   ```

   > The bot.py file includes a FastAPI server. This emulates the Pipecat Cloud service, and is as if you're running with `min_agents=1`.

4. Call your bot!

   Call the Twilio number you configured to talk to your bot.

## Production Deployment

You can deploy your bot to Pipecat Cloud and server to your infrastructure to run this bot in a production environment.

### Multi-Region Deployment (US and EU)

This project supports deploying to both US and EU regions with separate Twilio accounts. The system automatically routes calls based on the dialed phone number:

- **+1 numbers** (US/Canada) → US Pipecat Cloud agent with US Twilio credentials
- **Other numbers** (EU, etc.) → EU Pipecat Cloud agent with EU Twilio credentials

#### Required Environment Variables

Your `.env` file should include credentials for both regions:

```bash
# US Twilio credentials
TWILIO_ACCOUNT_SID=your_us_account_sid
TWILIO_AUTH_TOKEN=your_us_auth_token

# EU Twilio credentials (Ireland)
TWILIO_ACCOUNT_SID_EU=your_eu_account_sid
TWILIO_AUTH_TOKEN_EU=your_eu_auth_token
```

#### Deployment Configuration Files

This project includes two deployment configuration files:

- **`pcc-deploy.toml`** - US region deployment (agent: `daily-twilio-sip-dial-in`)
- **`pcc-deploy-eu.toml`** - EU region deployment (agent: `daily-twilio-sip-dial-in-eu`)

#### Deploy to US Region

1. Create secrets for the US region:

   ```bash
   pipecat cloud secrets set daily-twilio-sip-secrets -f .env -r us-west
   ```

2. Build and push the Docker image:

   ```bash
   pipecat cloud docker build-push
   ```

3. Deploy to US region:

   ```bash
   pipecat cloud deploy
   ```

#### Deploy to EU Region

1. Create secrets for the EU region:

   ```bash
   pipecat cloud secrets set daily-twilio-sip-secrets-eu -f .env -r eu-central
   ```

2. Build and push the EU Docker image (update the image name in `pcc-deploy-eu.toml` first):

   ```bash
   pipecat cloud docker build-push -c pcc-deploy-eu.toml
   ```

3. Deploy to EU region:

   ```bash
   pipecat cloud deploy -c pcc-deploy-eu.toml
   ```

#### How Region Detection Works

The webhook server (`server.py`) and bot (`bot.py`) both detect the region based on the dialed phone number (`to_phone`):

1. **Webhook server**: When a call comes in, `server_utils.py` checks if `to_phone` starts with `+1`. If so, it starts the US agent (`daily-twilio-sip-dial-in`); otherwise, it starts the EU agent (`daily-twilio-sip-dial-in-eu`).

2. **Bot**: When forwarding the call via Twilio, `bot.py` selects the appropriate Twilio credentials based on the same phone number check.

### Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) for tips on how to create secrets, build and push a docker image, and deploy your agent to Pipecat Cloud.

You'll only deploy your `bot.py` file.

### Deploy the Server

The `server.py` handles inbound call webhooks and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (receives webhooks and starts the bot)

### Environment Variables for Production

Add these to your production environment:

```bash
ENV=production
PIPECAT_API_KEY=your_pipecat_cloud_api_key
PIPECAT_AGENT_NAME=your-agent-name
```

The server automatically detects the environment and routes bot starting requests accordingly.

## Adding Custom Data to Agent Requests

You can extend the `AgentRequest` model in `server_utils.py` to pass custom data to your bot:

```python
class AgentRequest(BaseModel):
    room_url: str
    token: str
    call_sid: str
    sip_uri: str
    # Add your custom fields here
    customer_name: str | None = None
    account_id: str | None = None
```

Then populate this data in `server.py` before starting the bot:

```python
# Example: Look up customer information
customer_info = await get_customer_by_phone(call_data.from_phone)

agent_request = AgentRequest(
    room_url=sip_config.room_url,
    token=sip_config.token,
    call_sid=call_data.call_sid,
    sip_uri=sip_config.sip_endpoint,
    customer_name=customer_info.name,
    account_id=customer_info.id,
)
```

## Troubleshooting

### Call is not being answered

- Check that your Twilio webhook is correctly configured to point to your ngrok server and `/call` endpoint
- Make sure the server.py file is running
- Make sure ngrok is correctly setup and pointing to the correct port

### Call connects but no bot is heard

- Ensure your Daily API key is correct and has SIP capabilities
- Verify that the Cartesia API key and voice ID are correct
- Check that your Twilio credentials (Account SID and Auth Token) are correct

### Bot starts but disconnects immediately

- Check the Daily logs for any error messages
- Ensure your server has stable internet connectivity
