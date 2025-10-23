# Daily PSTN dial-out simple chatbot

This project demonstrates how to create a voice bot that uses Daily's PSTN capabilities to make outbound calls to phone numbers.

## How It Works

1. The server receives a dial-out request with the phone number to call
2. The server creates a Daily room with dial-out capabilities
3. The server starts the bot process (locally or via Pipecat Cloud based on ENV)
4. The bot joins the room and initiates the dial-out to the specified number
5. The bot automatically retries on failure (up to 5 attempts)
6. When the call is answered, the bot conducts the conversation

## Project Structure

This example is organized to be production-ready and easy to customize:

- **`server.py`** - FastAPI server that handles dial-out requests

  - Receives dial-out requests via `/dialout` endpoint
  - Creates Daily rooms with dial-out capabilities
  - Routes to local or production bot deployment
  - Uses shared HTTP session for optimal performance

- **`server_utils.py`** - Utility functions for Daily API interactions

  - Data models for dial-out requests and agent configuration
  - Room creation logic
  - Bot starting logic (production and local modes)
  - Easy to extend with custom business logic

- **`bot.py`** - The voice bot implementation
  - `DialoutManager` class for retry logic
  - Handles the conversation with the person being called
  - Deployed to Pipecat Cloud in production or run locally for development

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

You'll need two terminal windows open:

1. **Terminal 1**: Start the webhook server:

   ```bash
   uv run server.py
   ```

   This runs on port 8080 and handles dial-out requests.

2. **Terminal 2**: Start the bot server:

   ```bash
   uv run bot.py -t daily
   ```

   This runs on port 7860 and handles the bot logic.

3. **Test the dial-out functionality**

   With both servers running, send a dial-out request:

   ```bash
   curl -X POST "http://localhost:8080/dialout" \
     -H "Content-Type: application/json" \
     -d '{
       "dialout_settings": {
         "phone_number": "+1234567890"
       }
     }'
   ```

   The server will create a room, start the bot, and the bot will call the specified number. Answer the call to speak with the bot.

## Production Deployment

You can deploy your bot to Pipecat Cloud and server to your infrastructure to run this bot in a production environment.

### Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) for tips on how to create secrets, build and push a docker image, and deploy your agent to Pipecat Cloud.

You'll only deploy your `bot.py` file.

### Deploy the Server

The `server.py` handles dial-out requests and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (receives dial-out requests and starts the bot)

### Environment Variables for Production

Add these to your production environment:

```bash
ENV=production
PIPECAT_API_KEY=your_pipecat_cloud_api_key
PIPECAT_AGENT_NAME=your-agent-name
```

The server automatically detects the environment and routes bot starting requests accordingly.

## Customization

This example is designed to be easily customized for your use case:

### Adding Custom Data to Dial-out Requests

You can extend the `DialoutSettings` model in `server_utils.py` to pass custom data:

```python
class DialoutSettings(BaseModel):
    phone_number: str
    caller_id: str | None = None
    # Add your custom fields here
    customer_name: str | None = None
    account_id: str | None = None
```

Then populate this data in `server.py` before starting the bot:

```python
# Example: Look up customer information
customer_info = await get_customer_by_phone(dialout_request.dialout_settings.phone_number)

agent_request = AgentRequest(
    room_url=daily_room_config.room_url,
    token=daily_room_config.token,
    dialout_settings=dialout_request.dialout_settings,
    # Your custom data
    customer_name=customer_info.name,
    account_id=customer_info.id,
)
```

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
