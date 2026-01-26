# Gemini Phone Bots

A telephone-based conversational agent built with Pipecat, powered by Google's Gemini APIs and Twilio. This bot plays "Two Truths and a Lie". The bot will provide three statements and you have to guess which one is false.

Learn how to run and deploy these bots on Pipecat Cloud.

## Try it! 📞

Call **1-970-LIVE-API** (1-970-548-3274) to talk to a Gemini Live Pipecat bot over the phone.

## Prerequisites

### Environment

- Python 3.10 or later
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager installed

### Service API keys

You'll need API keys for the following services:

- [Gemini](https://aistudio.google.com/) LLMs: Live API and Text completions
- [Google STT & TTS](https://console.cloud.google.com) for Speech-to-Text and Text-to-Speech
- [Twilio](https://www.twilio.com/try-twilio) for phone calling

> 💡 **Tip**: Sign up these services. You'll need them for both local and cloud deployment.

## Setup

1. Clone this repository

   ```bash
   git clone https://github.com/daily-co/pcc-gemini-twilio.git
   cd pcc-gemini-twilio
   ```

2. Configure your API keys:

   Create a `.env` file:

   ```bash
   cp env.example .env
   ```

   Then, add your API keys:

   ```ini
   GOOGLE_API_KEY=
   GOOGLE_CREDENTIALS_PATH=./credentials.json
   TWILIO_ACCOUNT_SID=
   TWILIO_AUTH_TOKEN=
   ```

   > If you're running bot-cascade.py, you'll need to add a `credentials.json` file containing your Google Service Account credentials.

3. Set up a virtual environment and install dependencies

   ```bash
   uv sync
   ```

## Run your bot locally

For local development, we'll use Pipecat's P2P WebRTC transport, `SmallWebRTCTransport`. This transports is free to run and allows for faster iteration for development and testing.

Run the bot using:

```bash
uv run bot.py
```

**Open http://localhost:7860 in your browser** and click `Connect` to start talking to your bot.

> 💡 First run note: The initial startup may take ~20 seconds as Pipecat downloads required models and imports.

## Deploy to Production

Transform your local bot into a production-ready service. Pipecat Cloud handles scaling, monitoring, and global deployment.

### Prerequisites

1. [Sign up for Pipecat Cloud](https://pipecat.daily.co/sign-up).

2. Set up Docker for building your bot image:

   - **Install [Docker](https://www.docker.com/)** on your system
   - **Create a [Docker Hub](https://hub.docker.com/) account**
   - **Login to Docker Hub:**

     ```bash
     docker login
     ```

3. Log in with the `pipecatcloud` CLI (installed with the project) is used to manage your deployment and secrets.

   ```bash
   uv run pcc auth login
   ```

   > Tip: Use the CLI with the `pcc` command alias.

### Configure Twilio

1. [Purchase a phone number](https://help.twilio.com/articles/223135247-How-to-Search-for-and-Buy-a-Twilio-Phone-Number-from-Console) from Twilio, if you haven't already. Ensure the number has voice capabilities.

2. Retrieve your Pipecat Cloud organization name using the pipecatcloud CLI. This information is required when creating the TwiML configuration.

   ```bash
   pcc organizations list
   ```

3. Create a [TwiML Bin](https://help.twilio.com/articles/360043489573-Getting-started-with-TwiML-Bins) with the following configuration:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <Response>
   <Connect>
      <Stream url="wss://api.pipecat.daily.co/ws/twilio">
         <Parameter name="_pipecatCloudServiceHost"
            value="AGENT_NAME.ORGANIZATION_NAME"/>
      </Stream>
   </Connect>
   </Response>
   ```

   Replace the placeholder values:

   - `AGENT_NAME` with your deployed bot’s name (e.g., my-first-agent)
   - `ORGANIZATION_NAME` with your organization name from step 2

   For example, if your agent is named “pcc-gemini-twilio” and your organization is “industrious-purple-cat-123”, your value would be: pcc-gemini-twilio.industrious-purple-cat-123

4. Assign the TwiML Bin to your Twilio phone number:

   - Navigate to the "Phone Numbers" section in your Twilio dashboard (Phone Numbers > Manage > Active numbers)
   - Select your phone number from the list
   - In the "Configure" tab, under “Voice Configuration” section, find “A call comes in”
     - Set this dropdown to “TwiML Bin”
     - Select the "TwiML Bin" you created in step 3
   - Click Save to apply your changes

### Configure your deployment

The `pcc-deploy.toml` file tells Pipecat Cloud how to run your bot. **Update the `image` field** with your Docker Hub username by editing `pcc-deploy.toml`.

```ini
agent_name = "pcc-gemini-twilio"
image = "YOUR_DOCKERHUB_USERNAME/pcc-gemini-twilio:0.1" # 👈 Update this line
secret_set = "pcc-gemini-twilio-secrets"

[scaling]
	min_agents = 1
```

**Understanding the TOML file settings:**

- `agent_name`: Your bot's name in Pipecat Cloud
- `image`: The Docker image to deploy (format: `username/image:version`)
- `secret_set`: Where your API keys are stored securely
- `min_agents`: Number of bot instances to keep ready (1 = instant start)

> 💡 Tip: [Set up `image_credentials`](https://docs.pipecat.ai/deployment/pipecat-cloud/fundamentals/secrets#image-pull-secrets) in your TOML file for authenticated image pulls

### Configure secrets

Upload your API keys to Pipecat Cloud's secure storage:

```bash
uv run pcc secrets set pcc-gemini-twilio-secrets --file .env
```

This creates a secret set called `pcc-gemini-twilio-secrets` (matching your TOML file) and uploads all your API keys from `.env`.

### Build and deploy

Build your Docker image and push to Docker Hub:

```bash
uv run pcc docker build-push
```

Deploy to Pipecat Cloud:

```bash
uv run pcc deploy
```

### Call your bot

Call the Twilio number you set up earlier to speak with your bot! 🚀

## What's Next?

- **🔧 Customize your bot**: Modify `bot.py` to change personality, add functions, or integrate with your data
- **📚 Learn more**: Check out [Pipecat's docs](https://docs.pipecat.ai/) for advanced features
- **⚙️ Provide custom data**: [Learn how to provide custom data](https://docs.pipecat.ai/guides/telephony/twilio-websockets#custom-parameters-with-twiml) to your bot at run time
- **💬 Get help**: Join [Pipecat's Discord](https://discord.gg/pipecat) to connect with the community
