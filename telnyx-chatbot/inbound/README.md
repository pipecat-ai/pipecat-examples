# Telnyx Chatbot: Inbound

This project is a Pipecat-based chatbot that integrates with Telnyx to handle WebSocket connections and provide real-time communication. The project includes FastAPI endpoints for starting a call and handling WebSocket connections.

## Table of Contents

- [Telnyx Chatbot](#telnyx-chatbot)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Requirements](#requirements)
  - [Installation](#installation)
  - [Configure Telnyx TeXML application](#configure-telnyx-texml-application)
  - [Running the Application](#running-the-application)
    - [Using Python (Option 1)](#using-python-option-1)
    - [Using Docker (Option 2)](#using-docker-option-2)
  - [Usage](#usage)

## Prerequisites

### Telnyx

- A Telnyx account with:
  - API Key
  - A purchased phone number that supports voice calls

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

   ```sh
   cd inbound
   uv sync
   ```

2. Create an .env file and add API keys:

   ```sh
   cp env.example .env
   ```

## Local development

To run the twilio-chatbot for inbound calling locally, we'll first set up an ngrok tunnel and a TeXML application. Then, we'll run our bot and call into it to speak with the bot.

### Configure Telnyx TeXML application

1. Start ngrok:
   In a new terminal, start ngrok to tunnel the local server:

   ```sh
   ngrok http 7860
   ```

   > Tip: Use the `--subdomain` flag for a reusable ngrok URL.

2. If you haven't already, purchase a number from Telnyx.

   - Log in to the Telnyx developer portal: https://portal.telnyx.com/
   - Buy a number: https://portal.telnyx.com/#/numbers/buy-numbers

3. Create a Telnyx TeXML application:

   - Go to your TeXML configuration page: https://portal.telnyx.com/#/call-control/texml
   - Create a new TeXML app, if one doesn't exist already:
     - Add an application name
     - Under Webhooks, select POST as the "Voice Method"
     - Select "Custom URL" under Webhook URL Method
     - Enter your ngrok URL in the "Webhook URL" field (e.g. https://your-name.ngrok.io)
     - Click "Create" to save
       Note: You'll see subsequent pages to set up SIP and Outbound, both are not required, so just skip.
   - Navigate to "Manage Numbers" (https://portal.telnyx.com/#/numbers/my-numbers) and under SIP connection, select the pencil icon to edit and select the TeXML application that you just created.

### Run your bot

The bot.py file uses the Pipecat development runner, which runs a FastAPI server in order to receive connections.

1. To get started, we'll run our bot.py file:

```bash
uv run bot.py --transport telnyx --proxy your_ngrok_url
```

> Replace `your_ngrok_url` with your ngrok URL (e.g. your-subdomain.ngrok.io)

2. Call the number associated with your TeXML applicaiton. Your bot will answer and begin talking to you!

## Production deployment

To deploy your telnyx-chatbot for inbound calling, we'll use [Pipecat Cloud](https://pipecat.daily.co/).

### Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) for tips on how to create secrets, build and push a docker image, and deploy your agent to Pipecat Cloud.

### Configure Telnyx TeXML application

We'll create a new TeXML application that returns TeXML and uses a different number. This will enable your bot to run without a FastAPI server and will provide you with a separate phone number to use for production testing.

1. If you haven't already, purchase a number from Telnyx.

   - Log in to the Telnyx developer portal: https://portal.telnyx.com/
   - Buy a number: https://portal.telnyx.com/#/numbers/buy-numbers

2. Create your TeXML Bin:

   - Go to your TeXML Bin configuration page: https://portal.telnyx.com/#/call-control/texml-bin
   - Create a new TeXML Bin
   - In the "Name" field, provide a name
   - Leave the "URL" field blank
   - In the "Content" field, add the TeXML:

     ```bash
     <?xml version="1.0" encoding="UTF-8"?>
     <Response>
        <Connect>
           <Stream url="wss://api.pipecat.daily.co/ws/telnyx?serviceHost=AGENT_NAME.ORGANIZATION_NAME" bidirectionalMode="rtp"></Stream>
        </Connect>
        <Pause length="40"/>
     </Response>
     ```

   Replace:

   - `AGENT_NAME` with the name of the agent you deployed in the previous stepyour deployed agent name
   - `ORGANIZATION_NAME` with your Pipecat Cloud organization name

   - Click "Save" to save your TeXML Bin

3. Create a Telnyx TeXML application:

   - Go to your TeXML configuration page: https://portal.telnyx.com/#/call-control/texml
   - Create a new TeXML app, if one doesn't exist already:
     - Add an application name
     - Under Webhooks, select POST as the "Voice Method"
     - Select "TeXML Bin URL" under Webhook URL Method
     - In the "TeXML Bins" dropdown, select the TeXML Bin we created in the previous step
     - Click "Create" to save
       Note: You'll see subsequent pages to set up SIP and Outbound, both are not required, so just skip.
   - Navigate to "Manage Numbers" (https://portal.telnyx.com/#/numbers/my-numbers) and under SIP connection, select the pencil icon to edit and select the TeXML application that you just created.

### Call your Bot

Your bot file is now deployed to Pipecat Cloud and Telnyx is configured to receive calls. Dial the number associated with your bot to start a conversation!
