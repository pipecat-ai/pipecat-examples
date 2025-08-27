# Twilio Chatbot: Outbound Calling

This project demonstrates how to create a voice bot that can make outbound phone calls using Twilio's Programmable Voice API and Media Streams, powered by Pipecat.

## How it works

1. The server receives a POST request with a phone number to call
2. The server uses Twilio's REST API to initiate an outbound call
3. When the call is answered, Twilio fetches TwiML from the server
4. The TwiML connects the call to a WebSocket for real-time audio streaming
5. The bot engages in conversation with the person who answered the call

## Architecture

```
curl request → /start endpoint → Twilio REST API → Call initiated →
TwiML fetched → WebSocket connection → Bot conversation
```

## Prerequisites

### Twilio

- A Twilio account with:
  - Account SID and Auth Token
  - A purchased phone number that supports voice calls

### AI Services

- OpenAI API key for the bot's intelligence
- Deepgram API key for speech-to-text
- Cartesia API key for text-to-speech

### System

- Python 3.10+
- `uv` package manager

## Setup

1. **Install dependencies**

```bash
cd twilio-chatbot
uv sync
```

2. **Set up environment variables**

```bash
cp env.example .env
# Edit .env with your API keys
```

Your `.env` file should contain:

```bash
OPENAI_API_KEY=sk-your-openai-key
DEEPGRAM_API_KEY=your-deepgram-key
CARTESIA_API_KEY=your-cartesia-key
TWILIO_ACCOUNT_SID=ACyour-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_PHONE_NUMBER=+1234567890
```

3. **Get your Twilio credentials**

- **Account SID & Auth Token**: Found in your [Twilio Console Dashboard](https://console.twilio.com/)
- **Phone Number**: [Purchase a phone number](https://console.twilio.com/us1/develop/phone-numbers/manage/search) that supports voice calls

## Running the Server

1. **Start the outbound bot server**

```bash
cd outbound
uv run server.py
```

The server will start on port 8765.

2. **Expose your server to the internet** (for development)

In another terminal:

```bash
ngrok http 8765
```

Copy the ngrok URL (e.g., `https://abc123.ngrok.io`)

> 💡 Tip: Use `--subdomain` in your `ngrok` command for a reusable URL.

## Making an Outbound Call

With the server running and exposed via ngrok, you can initiate an outbound call to a specified number:

```bash
curl -X POST "https://your-ngrok-url.ngrok.io/start" \
  -H "Content-Type: application/json" \
  -d '{
    "dialout_settings": {
      "phone_number": "+1234567890"
    }
  }'
```

Replace:

- `your-ngrok-url.ngrok.io` with your actual ngrok URL
- `+1234567890` with the phone number you want to call

## What Happens During a Call

1. **Call Initiation**: The server receives your request and calls Twilio's API
2. **Phone Rings**: Twilio places the call to the specified number
3. **Call Answered**: When someone picks up, Twilio requests TwiML from your server
4. **WebSocket Connection**: TwiML instructs Twilio to connect audio to your WebSocket
5. **Bot Conversation**: The bot immediately greets the person and explains why it's calling
6. **Real-time Audio**: Audio flows bidirectionally through Twilio Media Streams

## API Endpoints

- **`POST /start`** - Initiate an outbound call

  - Body: `{"dialout_settings": {"phone_number": "+1234567890"}}`
  - Response: `{"call_sid": "CA...", "status": "call_initiated", "phone_number": "+1234567890"}`

- **`POST /twiml`** - Serves TwiML instructions (called by Twilio)

  - Returns XML that connects the call to the WebSocket

- **`WebSocket /ws`** - Handles real-time audio streaming with Twilio
