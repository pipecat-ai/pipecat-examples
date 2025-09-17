# Daily + Twilio SIP dial-out Voice Bot

This project demonstrates how to create a voice bot that can make phone calls via Twilio and use Daily's SIP capabilities to enable voice conversations. It supports both local development and Pipecat Cloud deployment.

## How It Works

1. The server receives a POST request with the SIP URI to dial out to
2. The server creates a Daily room with SIP capabilities
3. The server starts the bot with the room details and dial-out configuration
4. When the bot joins the room, it starts the dial-out process to the provided SIP URI
5. Twilio receives the request and processes the SIP URI via configured TwiML
6. Twilio rings the number found within the SIP URI
7. When the user answers the phone, they are connected to the bot
8. The end user and bot are connected, and the bot handles the conversation

## Prerequisites

- A Daily account with an API key for room creation
- A Twilio account with a phone number that supports voice and a correctly configured SIP domain
- OpenAI API key for the LLM inference
- Cartesia API key for text-to-speech
- Deepgram API key for speech-to-text
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager installed

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
  <Dial callerId="+1234567890">{{#e164}}{{To}}{{/e164}}</Dial>
</Response>
```

- callerId must be a valid number that you own on [Twilio](https://console.twilio.com/us1/develop/phone-numbers/manage/incoming)
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

## Running the Bot Locally

1. In your `.env` file, set `ENVIRONMENT=local`

2. Start the server (handles dial-out requests and bot starting):

   ```bash
   uv run server.py
   ```

3. Send a curl request to initiate a call:

```bash
curl -X POST "http://localhost:7860/start" \
  -H "Content-Type: application/json" \
  -d '{
    "dialout_settings": {
      "sip_uri": "sip:+1234567890@daily.sip.twilio.com"
    }
  }'
```

Replace:

- The phone number (starting with +1) with the phone number you want to call
- `daily` with the SIP domain you configured previously

The server will create a room, start the bot, and the bot will dial out to the provided SIP URI. Answer the call to speak with the bot.

## Deploy to Pipecat Cloud

### Prerequisites

Configure your machine with the required Pipecat Cloud and Docker prerequisites. See the [Quickstart](https://docs.pipecat.ai/getting-started/quickstart#prerequisites-2) guide for details.

### Configure your Deployment

Update the `pcc-deploy.toml` file with:

- `agent_name`: Your bot’s name in Pipecat Cloud
- `image`: The Docker image to deploy (format: username/image:version)
- `image_credentials`: Your Docker registry image pull secret to authenticate your image pull
- `secret_set`: Where your API keys are stored securely

### Create a Secrets Set

Create the secrets set from your .env file:

```bash
uv run pcc secrets set daily-twilio-sip-secrets --file .env
```

### Build and deploy

Build your Docker image and push to Docker Hub:

```bash
uv run pcc docker build-push
```

Deploy to Pipecat Cloud:

```bash
uv run pcc deploy
```

### Run your Server

The `server.py` file is a FastAPI server that handles the Twilio incoming webhook. For a production deployment, this server should be run separately from your Pipecat Cloud bot. This would be a server environment that runs the FastAPI server persistently, so that it can handle inbound requests.

For the sake of testing the Pipecat Cloud deployment, we'll run the server locally and expose it to the internet via ngrok:

In terminal 1:

```bash
uv run server.py
```

In terminal 2:

```bash
ngrok http 7860
```

> Note: Ensure that the `ENVIRONMENT` variable is set to `production` to use the Pipecat Cloud hosted bot.

### Test your Deployment

Send a curl request to initiate a call:

```bash
curl -X POST "http://localhost:7860/start" \
  -H "Content-Type: application/json" \
  -d '{
    "dialout_settings": {
      "sip_uri": "sip:+1234567890@daily.sip.twilio.com"
    }
  }'
```
