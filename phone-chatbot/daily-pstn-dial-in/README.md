# Daily PSTN dial-in simple chatbot

This project demonstrates how to create a voice bot that can receive phone calls via Daily's PSTN capabilities to enable voice conversations.

## How It Works

1. Daily receives an incoming call to your phone number
2. Daily calls your webhook server (`/daily-dialin-webhook` endpoint)
3. The webhook creates a Daily room with SIP configuration
4. The webhook starts your bot with the room details and caller information
5. The caller is put on hold with music
6. The bot joins the Daily room and signals readiness
7. Daily forwards the call to the Daily room
8. The caller and bot are connected for the conversation

## Project Structure

This example uses Pipecat's development runner to handle the webhook and bot lifecycle:

- **`bot.py`** - The voice bot implementation
  - Handles the conversation with the caller
  - Uses `DailyDialinRequest` from the runner for type-safe dial-in data
  - Deployed to Pipecat Cloud in production or run locally for development
  - The runner automatically provides webhook handling when using `--dialin` flag

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

   Required environment variables:

   - `DAILY_API_KEY` - Your Daily API key
   - `DEEPGRAM_API_KEY` - For speech-to-text
   - `CARTESIA_API_KEY` - For text-to-speech
   - `OPENAI_API_KEY` - For LLM inference

3. Buy a phone number

   Instructions on how to do that can be found at this [docs link](https://docs.daily.co/reference/rest-api/phone-numbers/buy-phone-number)

4. Set up the dial-in config

   Instructions on how to do that can be found at this [docs link](https://docs.daily.co/reference/rest-api/domainDialinConfig).

   The `room_creation_api` should point to your webhook endpoint. For local testing with ngrok, this will be:

   ```
   https://your-ngrok-url.ngrok.io/daily-dialin-webhook
   ```

   > Tip: If you're using Pipecat Cloud, you can purchase a number using the Pipecat Cloud dashboard (Settings > Telephony).

## Run the Bot Locally

1. **Run your bot with dial-in support**

   ```bash
   uv run bot.py -t daily --dialin
   ```

   This starts a FastAPI server on port 7860 with the `/daily-dialin-webhook` endpoint.

2. **Expose your bot to the internet**

   ```bash
   ngrok http 7860
   ```

   Copy the ngrok URL (e.g., `https://abc123.ngrok.io`).

   > Tip: Use `ngrok http 7860 --subdomain your-subdomain` for a reusable URL.

3. **Configure your Daily phone number**

   Set your phone number's `room_creation_api` webhook to:

   ```
   https://your-ngrok-url.ngrok.io/daily-dialin-webhook
   ```

   Instructions: [Daily Dial-in Config Docs](https://docs.daily.co/reference/rest-api/domainDialinConfig)

4. **Call your bot!**

   Call your configured phone number to talk to your bot.

## Deploy to Pipecat Cloud

1. **Deploy your bot**

   Follow the [Pipecat Cloud quickstart](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) to deploy your `bot.py` file.

   You only need to deploy `bot.py` - Pipecat Cloud automatically handles webhook endpoints and room creation.

2. **Configure your phone number webhook**

   Using the Pipecat Cloud dashboard, configure your phone number's webhook endpoint to point to your deployed agent.

   This will set the webhook URL to:

   ```
   https://api.pipecat.daily.co/v1/public/webhooks/{organization_id}/{agent_name}/dialin
   ```

   Pipecat Cloud will automatically:

   - Receive the webhook
   - Create a Daily room with SIP configuration
   - Start your bot with the dial-in settings
   - Pass caller information via `DailyDialinRequest`

## Customize Your Bot

You can use the caller's phone number to personalize the conversation:

```python
from pipecat.runner.types import DailyDialinRequest, RunnerArguments

async def bot(runner_args: RunnerArguments):
    # Parse dial-in request
    request = DailyDialinRequest.model_validate(runner_args.body)

    # Get caller's phone number
    caller_phone = request.dialin_settings.From

    # Look up customer information from your database
    customer = await get_customer_by_phone(caller_phone)

    # Customize the system prompt
    messages = [
        {
            "role": "system",
            "content": f"You are a helpful assistant for {customer.name}. "
                      f"Their account status is {customer.status}. "
                      "Keep responses concise and conversational."
        }
    ]

    # Use the customized context in your bot...
```

## Troubleshooting

### Call is not being answered

- Check that your dial-in config's `room_creation_api` points to your ngrok URL + `/daily-dialin-webhook`
- Verify the bot is running with `uv run bot.py -t daily --dialin`
- Make sure ngrok is running and pointing to port 7860
- Check the bot logs for webhook reception
- Ensure your `DAILY_API_KEY` has the phone number associated with it

### Call connects but no bot is heard

- Ensure your `DAILY_API_KEY` environment variable is set and has SIP capabilities
- Verify that the `CARTESIA_API_KEY` and voice ID are correct
- Check that `DEEPGRAM_API_KEY` is set for speech-to-text

### Bot starts but disconnects immediately

- Check the bot logs for error messages
- Verify all required environment variables are set
- Ensure your server has stable internet connectivity

### Webhook test fails

- The runner automatically handles Daily's webhook verification test
- Check that the bot is running and accessible via your ngrok URL

## Daily SIP Configuration

The runner automatically configures Daily rooms with SIP capabilities when using `--dialin`:

```python
# The runner calls this for you:
room_config = await configure(session, sip_caller_phone=data.get("From"))
```

This creates a room with these SIP settings:

- `display_name`: Set to the caller's phone number (From field)
- `video`: False (audio-only call)
- `sip_mode`: "dial-in" (for receiving calls)
- `num_endpoints`: 1 (one SIP endpoint for the incoming caller)

The runner passes the caller's phone number and call details to your bot via `DailyDialinRequest` in `runner_args.body`.
