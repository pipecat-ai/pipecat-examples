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
- OpenAI API key for the bot's intelligence
- Cartesia API key for text-to-speech
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

4. Create and configure a programmable SIP domain

- Visit this link to [create a new SIP domain:](https://console.twilio.com/us1/develop/voice/manage/sip-domains?frameUrl=%2Fconsole%2Fvoice%2Fsip%2Fendpoints%3Fx-target-region%3Dus1)
- Press the plus button to create a new SIP domain
- Give the SIP domain a friendly name. For example "Daily SIP domain"
- Specify a SIP URI, for example "daily.sip.twilio.com"
- Under "Voice Authentication", press the plus button next to IP Access Control Lists. We are going to white list the entire IP spectrum
- Give it a friendly name such as "first half"
- For CIDR Network Address specify 0.0.0.0 and for the subnet specify 1
- Again, specify "first half" for the friendly name and click "Create ACL"
- Now let's do the same again and add another IP Access Control List by pressing the plus button
- Give it a friendly name such as "second half".
- For the CIDR Network Address specify 128.0.0.0 and for the subnet specify 1
- Lastly, specify the friendly name "second half" again
- Make sure both IP Access control list appears selected in the dropdown
- Under "Call Control Configuration", specify the following:
  - Configure with: Webhooks, TwiML Bins, Functions, Studio, Proxy
  - A call comes in: TwiML Bin > Select the name of the TwiML bin you made earlier
- Leave everything else blank and scroll to the bottom of the page. Click Save

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
uv run pcc secrets set quickstart-secrets --file .env
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
