# Exotel Chatbot: Outbound

This project is a FastAPI-based chatbot that integrates with Exotel to make outbound calls with personalized call information. The project uses Exotel's Connect API to initiate calls and App Bazaar configuration to handle WebSocket connections.

## How It Works

When you want to make an outbound call:

1. **Send POST request**: `POST /start` with a phone number to call
2. **Server calls Exotel Connect API**: Uses "Connect Two Numbers" API
3. **Exotel calls your bot number first**: Your bot number "answers" and connects to WebSocket
4. **Exotel calls the customer second**: Customer answers and gets connected to your bot
5. **Audio flows**: Customer ↔ Exotel ↔ WebSocket ↔ Your Bot

## Architecture

```
curl request → /start endpoint → Exotel Connect API → Bot number called →
App Bazaar triggers → WebSocket connects → Customer called → Audio bridged
```

## Prerequisites

### Exotel

- An Exotel account with:
  - API Key and API Token
  - Account SID
  - A purchased phone number that supports voice calls (this will be your bot number)
  - Voice streaming enabled (contact support if not available)

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

2. Get your Exotel credentials:

- **API Key & Token**: Found in your [Exotel Console](https://my.exotel.com/) → API Settings
- **Account SID**: Available in your API settings page
- **Phone Number**: [Purchase a phone number](https://my.exotel.com/) that supports voice calls (this becomes your bot number)

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
- WebSocket connections route through Pipecat Cloud infrastructure

## Local Development

### Configure Your Bot Number in App Bazaar

**Important**: Your bot number (EXOTEL_PHONE_NUMBER) must be configured to connect to WebSocket when called.

1. Start ngrok:
   In a new terminal, start ngrok to tunnel the local server:

   ```sh
   ngrok http 7860
   ```

   > Tip: Use the `--subdomain` flag for a reusable ngrok URL.

2. Configure your bot number in App Bazaar:

   - Navigate to **ExoPhones** in your Exotel dashboard
   - Find your bot number (the one in EXOTEL_PHONE_NUMBER)
   - Click edit and create/assign an App Bazaar flow:

     **Create App Bazaar Flow:**

     - Navigate to App Bazaar → Create Custom App
     - Build your call flow:

       **Add Voicebot Applet**

       - Drag the "Voicebot" applet to your call flow
       - Configure the Voicebot Applet:
         - **URL**: `wss://your-ngrok-url.ngrok.io/ws`
         - **Record**: Enable if you want call recordings

       **Optional: Add Hangup Applet**

       - Drag a "Hangup" applet at the end to properly terminate calls

     - Your final flow should look like:

       ```
       Call Start → [Voicebot Applet] → [Hangup Applet]
       ```

     - Save your App Bazaar configuration
     - **Assign this flow to your bot number** in ExoPhones settings

### Run the Local Server

```bash
uv run server.py
```

The server will start on port 7860.

## Making an Outbound Call

With the server running and your bot number configured in App Bazaar, you can initiate an outbound call:

```bash
curl -X POST https://your-ngrok-url.ngrok.io/start \
  -H "Content-Type: application/json" \
  -d '{
    "dialout_settings": {
      "phone_number": "+1234567890"
    }
  }'
```

**What happens:**

1. Your server calls Exotel's Connect API
2. Exotel calls your bot number first (triggers WebSocket connection)
3. Exotel calls the customer number second
4. Both calls are bridged together
5. Customer talks directly to your bot

**Expected response:**

```json
{
  "call_sid": "5570510625ba6bab3d653ab0c479199a",
  "status": "call_initiated",
  "phone_number": "+1234567890"
}
```

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

# Keep your existing Exotel and AI service keys
```

### 3. Deploy the Server

The `server.py` handles outbound call initiation and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (initiates calls, serves WebSocket connections)

When `ENV=production`, the server automatically routes WebSocket connections to your Pipecat Cloud bot.

### 4. Update Your Bot Number's App Bazaar Configuration

Update your bot number's Voicebot Applet configuration for production:

- Navigate to **ExoPhones** → find your bot number → edit the assigned App Bazaar flow
- Update the Voicebot Applet URL to use Pipecat Cloud:

  ```bash
  wss://api.pipecat.daily.co/ws/exotel?serviceHost=AGENT_NAME.ORGANIZATION_NAME
  ```

  Replace:

  - `AGENT_NAME` with your deployed agent's name
  - `ORGANIZATION_NAME` with your organization ID

> Alternatively, you can test your Pipecat Cloud deployment by keeping your bot number pointed to your local server via ngrok.

### Call your Bot

As you did before, initiate a call via `curl` command to trigger your bot to dial a number.

## Accessing Call Information in Your Bot

Your bot automatically receives call information through Exotel's WebSocket messages. The server extracts the `from` and `to` phone numbers and makes them available to your bot.

In your `bot.py`, you can access this information from the WebSocket connection. The Pipecat development runner extracts this data using the `parse_telephony_websocket` function. This allows your bot to provide personalized responses based on who's calling and which number they called.

## Key Differences from Other Providers

- **Connect Two Numbers API**: Exotel calls your bot number first, then the customer
- **Bot Number Configuration**: Your bot number must be pre-configured in App Bazaar
- **No Dynamic XML**: Unlike Plivo/Twilio, no dynamic XML response endpoints needed
- **Call Bridging**: Exotel handles bridging the bot and customer calls automatically
- **Automatic Call Information**: Phone numbers provided automatically in WebSocket messages
