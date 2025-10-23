# Daily PSTN dial-in simple chatbot

This project demonstrates how to create a voice bot that can receive phone calls via Daily's PSTN capabilities to enable voice conversations.

## How It Works

1. Daily receives an incoming call to your phone number
2. Daily calls your webhook server (`/daily-webhook` endpoint in `server.py`)
3. The server creates a Daily room with dial-in capabilities
4. The server starts the bot process with the room details (locally or via Pipecat Cloud)
5. The caller is put on hold with music
6. The bot joins the Daily room and signals readiness
7. Daily forwards the call to the Daily room
8. The caller and the bot are connected, and the bot handles the conversation

## Project Structure

This example is organized to be production-ready and easy to customize:

- **`server.py`** - FastAPI webhook server that handles incoming calls

  - Receives Daily PSTN webhooks
  - Creates Daily rooms
  - Routes to local or production bot deployment
  - Uses shared HTTP session for optimal performance

- **`server_utils.py`** - Utility functions for Daily API interactions

  - Data models for call data and agent requests
  - Room creation logic
  - Bot starting logic (production and local modes)
  - Easy to extend with custom business logic

- **`bot.py`** - The voice bot implementation
  - Handles the conversation with the caller
  - Deployed to Pipecat Cloud in production or run locally for development

## Prerequisites

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

3. Buy a phone number

   Instructions on how to do that can be found at this [docs link:](https://docs.daily.co/reference/rest-api/phone-numbers/buy-phone-number)

4. Set up the dial-in config

   Instructions on how to do that can be found at this [docs link:](https://docs.daily.co/reference/rest-api/domainDialinConfig).

   Note that the `room_creation_api` is the address and route of your server that will handle the webhook that fires when a call is received. For local testing this will be your `ngrok` tunnel URL and the route should match your server's endpoint. In testing your demo, this will be `https://your-ngrok-url.ngrok.io/daily-webhook`.

   > Tip: If you're using Pipecat Cloud, you can purchase a number using the Pipecat Cloud dashboard (Settings > Telephony).

## Environment Configuration

The bot supports two deployment modes controlled by the `ENV` variable:

### Local Development (`ENV=local`)

- Uses your local server or ngrok URL for handling the dial-in webhook and starting the bot
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

   Important: Make sure that this URL matches the `room_creation_api` URL for your phone number.

   > Tip: Use the `--subdomain` for a reusable ngrok link.

3. Terminal 3: Run your bot:

   ```bash
   uv run bot.py -t daily
   ```

   > The bot.py file includes a FastAPI server. This emulates the Pipecat Cloud service, and is as if you're running with `min_agents=1`.

4. Call your bot!

   Call the number you configured to talk to your bot.

## Production Deployment

You can deploy your bot to Pipecat Cloud and server to your infrastructure to run this bot in a production environment.

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
    call_id: str
    call_domain: str
    # Add your custom fields here
    customer_name: str | None = None
    account_id: str | None = None
```

Then populate this data in `server.py` before starting the bot:

```python
# Example: Look up customer information
customer_info = await get_customer_by_phone(call_data.from_phone)

agent_request = AgentRequest(
    room_url=daily_room_config.room_url,
    token=daily_room_config.token,
    call_id=call_data.call_id,
    call_domain=call_data.call_domain,
    customer_name=customer_info.name,
    account_id=customer_info.id,
)
```

## Troubleshooting

### Call is not being answered

- Check that your dial-in config is correctly configured to point towards your ngrok server and correct endpoint
- Make sure the server.py file is running
- Make sure ngrok is correctly setup and pointing to the correct port

### Call connects but no bot is heard

- Ensure your Daily API key is correct and has SIP capabilities
- Verify that the Cartesia API key and voice ID are correct

### Bot starts but disconnects immediately

- Check the Daily logs for any error messages
- Ensure your server has stable internet connectivity

## Daily SIP Configuration

The bot configures Daily rooms with SIP capabilities using these settings:

```python
sip_params = DailyRoomSipParams(
    display_name="phone-user",  # This will show up in the Daily UI; optional display the dialer's number
    video=False,                # Audio-only call
    sip_mode="dial-in",         # For receiving calls (vs. dial-out)
    num_endpoints=1,            # Number of SIP endpoints to create
)
```

If you're using the Pipecat development runner's Daily util, these args are handled for you when calling `configure()`.
