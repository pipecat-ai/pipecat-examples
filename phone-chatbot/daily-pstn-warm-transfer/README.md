# Daily PSTN Warm Transfer

A demonstration of how to implement warm call transfers using Pipecat. Unlike cold transfers where the bot immediately disconnects, warm transfers allow the bot to:

1. Put the customer on hold with music
2. Dial out to a specialist
3. Brief the specialist on the customer's issue
4. Connect both parties
5. Fall back gracefully if the transfer fails

## How It Works

1. Daily receives an incoming call to your phone number
2. Daily calls your webhook server (`/start` endpoint)
3. The server creates a Daily room and starts the bot
4. The bot greets the customer and handles the conversation
5. When the customer needs a specialist:
   - Bot speaks a hold message
   - Customer hears hold music
   - Bot dials the specialist
   - Bot briefs the specialist on the customer's issue
   - Both parties are connected
6. If the specialist doesn't answer, the bot returns to the customer

## Architecture Overview

This example uses:

- **Transport**: Daily WebRTC with SIP dial-in/dial-out
- **Speech-to-Text**: Deepgram
- **LLM**: OpenAI GPT-4o
- **Text-to-Speech**: Cartesia
- **Hold Music**: SoundfileMixer (Pipecat built-in)

### Key Components

- **CustomerHoldGate**: Gates customer audio input when on hold
- **BotAudioGate**: Routes bot audio to specialist only during briefing
- **TransferCoordinator**: Orchestrates the transfer flow using frame-based control
- **SoundfileMixer**: Plays hold music to the customer

## Prerequisites

### Daily

- A Daily account with an API key
- A phone number purchased through Daily with dial-in enabled

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

1. Create a virtual environment and install dependencies:

   ```bash
   uv sync
   ```

2. Set up environment variables:

   ```bash
   cp env.example .env
   # Edit .env with your API keys
   ```

3. Add a hold music file:

   Place a mono WAV file named `hold_music.wav` in this directory. The file should be:
   - Mono (single channel)
   - Any sample rate (will be resampled automatically)
   - Royalty-free for your use case

4. Buy a phone number:

   See [Daily docs on purchasing phone numbers](https://docs.daily.co/reference/rest-api/phone-numbers/buy-phone-number).

5. Set up the dial-in config:

   See [Daily docs on domain dial-in config](https://docs.daily.co/reference/rest-api/domainDialinConfig).

   Set `room_creation_api` to your server's `/start` endpoint (e.g., `https://your-ngrok-url.ngrok.io/start`).

## Environment Configuration

The bot supports two deployment modes controlled by the `ENV` variable:

### Local Development (`ENV=local`)

- Uses your local server for handling webhooks
- Default configuration for development and testing

### Production (`ENV=production`)

- Bot is deployed to Pipecat Cloud
- Requires `PIPECAT_API_KEY` and `PIPECAT_AGENT_NAME`

## Run the Bot Locally

1. Start the webhook server:

   ```bash
   uv run server.py
   ```

2. Start an ngrok tunnel:

   ```bash
   ngrok http 7860
   ```

   Make sure this URL matches your Daily dial-in config.

3. Call your bot!

   Call the phone number you configured. Ask to speak with a specialist and the bot will perform a warm transfer.

## Request Format

You can customize transfer targets by including `warm_transfer_config` in the webhook request:

```json
{
  "From": "+15551234567",
  "To": "+15559876543",
  "callId": "abc123",
  "callDomain": "example.daily.co",
  "warm_transfer_config": {
    "transfer_targets": [
      {
        "name": "Sales Team",
        "phone_number": "+15551112222",
        "description": "Handles purchases and pricing"
      },
      {
        "name": "Support Team",
        "phone_number": "+15553334444",
        "extension": "123",
        "description": "Handles technical issues"
      }
    ],
    "transfer_messages": {
      "hold_message": "Let me connect you with a specialist. Please hold.",
      "transfer_failed_message": "I couldn't reach anyone. How else can I help?",
      "connecting_message": "I have the customer ready now."
    }
  }
}
```

If `warm_transfer_config` is not provided, the bot uses default targets from environment variables (`SALES_NUMBER`, `SUPPORT_NUMBER`, `BILLING_NUMBER`).

## Production Deployment

### Deploy to Pipecat Cloud

1. Install the Pipecat CLI:

   ```bash
   pip install pipecat-ai-cli
   ```

2. Deploy your bot:

   ```bash
   pcc deploy
   ```

3. Set environment variables for production:

   ```bash
   ENV=production
   PIPECAT_API_KEY=your_pipecat_cloud_api_key
   PIPECAT_AGENT_NAME=daily-pstn-warm-transfer
   ```

### Deploy the Server

The `server.py` handles inbound call webhooks and should be deployed separately:

- **Bot**: Runs on Pipecat Cloud
- **Server**: Runs on your infrastructure

## What is a Warm Transfer?

A warm transfer differs from a cold transfer:

| Aspect | Cold Transfer | Warm Transfer |
|--------|---------------|---------------|
| Bot leaves call | Immediately when specialist answers | After connecting customer |
| Customer experience | Silence until specialist answers | Hold music while waiting |
| Specialist briefing | None | Bot explains customer's issue |
| Failure handling | Customer disconnected | Bot returns to help customer |

### Warm Transfer Flow

1. **Customer** calls and speaks with the **bot**
2. Customer needs specialist help
3. **Bot** says "Please hold" and puts customer on hold
4. **Customer** hears hold music
5. **Bot** dials the **specialist**
6. When specialist answers, **bot** briefs them
7. **Bot** connects customer to specialist (hold music stops)
8. **Bot** leaves the call
9. **Customer** and **specialist** are now connected

If the specialist doesn't answer, the bot returns to the customer with an apology.

## Troubleshooting

### Customer doesn't hear hold music

- Ensure `hold_music.wav` exists and is a valid mono WAV file
- Check that the SoundfileMixer is properly initialized

### Transfer fails immediately

- Verify the specialist phone number is correct
- Check that dial-out is enabled on your Daily domain
- Ensure the room token has owner permissions

### Bot doesn't return to customer after failed transfer

- Check the `on_dialout_error` event handler logs
- Verify the `CustomerHoldFrame(on_hold=False)` is being pushed

### Call connects but no bot is heard

- Ensure your Daily API key is correct
- Verify Deepgram and Cartesia API keys are correct
