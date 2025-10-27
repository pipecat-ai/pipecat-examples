# Daily + Twilio SIP dial-out Voice Bot

This project demonstrates how to create a voice bot that uses Daily's SIP capabilities with Twilio to make outbound calls to phone numbers.

## How It Works

1. The server receives a dial-out request with the SIP URI to call
2. The server creates a Daily room with SIP capabilities
3. The server starts the bot process (locally or via Pipecat Cloud based on ENV)
4. The bot joins the room and initiates the dial-out to the specified SIP URI
5. Twilio receives the SIP request and processes it via configured TwiML
6. Twilio rings the number found within the SIP URI
7. The bot automatically retries on failure (up to 5 attempts)
8. When the call is answered, the bot conducts the conversation

## Project Structure

This example is organized to be production-ready and easy to customize:

- **`server.py`** - FastAPI server that handles dial-out requests

  - Receives dial-out requests via `/dialout` endpoint
  - Creates Daily rooms with SIP capabilities
  - Routes to local or production bot deployment
  - Uses shared HTTP session for optimal performance

- **`server_utils.py`** - Utility functions for Twilio and Daily API interactions

  - Data models for dial-out requests and agent configuration
  - Room creation logic
  - Bot starting logic (production and local modes)
  - Easy to extend with custom business logic

- **`bot.py`** - The voice bot implementation
  - `DialoutManager` class for retry logic
  - Handles the conversation with the person being called
  - Deployed to Pipecat Cloud in production or run locally for development

## Prerequisites

### Twilio

- A Twilio account with a phone number that supports voice
- A correctly configured SIP domain (see setup instructions below)

### Daily

- A Daily account with an API key (or Daily API key from Pipecat Cloud account)

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

3. Create a TwiML Bin

   Visit this link to create your [TwiML Bin](https://www.twilio.com/docs/serverless/twiml-bins)

   - Login to the account that has your purchased Twilio phone number
   - Press the plus button on the TwiML Bin dashboard to write a new TwiML that Twilio will host for you
   - Give it a friendly name. For example "daily sip uri twiml bin"
   - For the TWIML code, use something like:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <Response>
     <Dial answerOnBridge="true" callerId="+1234567890">{{#e164}}{{To}}{{/e164}}</Dial>
   </Response>
   ```

   - callerId must be a valid number that you own on [Twilio](https://console.twilio.com/us1/develop/phone-numbers/manage/incoming)
   - answerOnBridge="true|false" based on your use-case
   - Save the file. We will use this when creating the SIP domain

4. Create and configure a SIP domain

   This allows Daily to make outbound calls through Twilio.

   **Create the SIP Domain:**

   - Go to [Twilio Console > Voice > SIP Domains](https://console.twilio.com/us1/develop/voice/manage/sip-domains)
   - Click the **+** button to create a new domain
   - **Domain Name**: Choose something like `daily.sip.twilio.com`
   - **Friendly Name**: `Daily SIP Domain`

   **Configure Authentication (Allow all traffic):**

   - Under "Voice Authentication", click **+** next to "IP Access Control Lists"
   - Create **first ACL**:
     - **Friendly Name**: `Allow All - Part 1`
     - **CIDR**: `0.0.0.0/1` (covers 0.0.0.0 to 127.255.255.255)
   - Create **second ACL**:
     - **Friendly Name**: `Allow All - Part 2`
     - **CIDR**: `128.0.0.0/1` (covers 128.0.0.0 to 255.255.255.255)
   - Make sure both ACLs are selected in the dropdown

   **Configure Call Handling:**

   - Under "Call Control Configuration":
     - **Configure with**: `TwiML Bins`
     - **A call comes in**: Select your TwiML bin from step 3
   - Click **Save**

   > **Why these settings?** The IP ranges allow Daily's servers to connect from anywhere, and the TwiML bin tells Twilio how to handle the calls.

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
         "sip_uri": "sip:+1234567890@daily.sip.twilio.com"
       }
     }'
   ```

   Replace:

   - The phone number (starting with +1) with the phone number you want to call
   - `daily.sip.twilio.com` with the SIP domain you configured in step 4

   The server will create a room, start the bot, and the bot will dial out to the provided SIP URI. Answer the call to speak with the bot.

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
    sip_uri: str
    # Add your custom fields here
    customer_name: str | None = None
    account_id: str | None = None
```

Then populate this data in `server.py` before starting the bot:

```python
# Example: Look up customer information
customer_info = await get_customer_by_phone(dialout_request.dialout_settings.sip_uri)

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

### Call is not being initiated

- Check that your server.py is running on port 8080
- Check that your bot.py is running on port 7860
- Verify that the SIP URI format is correct: `sip:+1234567890@your-domain.sip.twilio.com`

### Call connects but no bot is heard

- Ensure your Daily API key is correct and has SIP capabilities
- Verify that the Cartesia API key and voice ID are correct
- Check that your Twilio SIP domain is correctly configured with the TwiML bin

### Bot starts but disconnects immediately

- Check the Daily logs for any error messages
- Ensure your server has stable internet connectivity
- Verify that your Twilio IP Access Control Lists allow all traffic

### Twilio SIP domain issues

- Make sure both IP ACLs (0.0.0.0/1 and 128.0.0.0/1) are created and selected
- Verify that the TwiML bin has a valid caller ID from your Twilio account
- Check that the SIP domain name matches what you're using in the SIP URI
