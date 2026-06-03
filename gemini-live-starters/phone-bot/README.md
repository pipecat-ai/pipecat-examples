# Gemini Phone Bots

A telephone-based conversational agent built with Pipecat, powered by Google's Gemini APIs and Twilio. This bot plays "Two Truths and a Lie". The bot will provide three statements and you have to guess which one is false.

Learn how to run and deploy these bots on Pipecat Cloud.

## Try it! 📞

Call **1-970-LIVE-API** (1-970-548-3274) to talk to a Gemini Live Pipecat bot over the phone.

## Prerequisites

### Environment

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager installed

### Service API keys

You'll need API keys for the following services:

- [Gemini](https://aistudio.google.com/) LLMs: Live API and Text completions
- [Google STT & TTS](https://console.cloud.google.com) for Speech-to-Text and Text-to-Speech
- [Twilio](https://www.twilio.com/try-twilio) for phone calling

> 💡 **Tip**: Sign up these services. You'll need them for both local and cloud deployment.

> **Regional note (Latin America and other regions):** The Gemini Live WebSocket API via AI Studio (`generativelanguage.googleapis.com`) is not reliably available in all regions, including Latin America. If you experience connection timeouts, use **Vertex AI** instead — see the [Regional Setup (Vertex AI)](#regional-setup-vertex-ai) section below.

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

   > If you're running bot-cascade.py, or using the Vertex AI backend (recommended for Latin America and other regions), you'll need to add a `credentials.json` file containing your Google Service Account credentials. See [Regional Setup (Vertex AI)](#regional-setup-vertex-ai) below.

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

The `pcc-deploy.toml` file tells Pipecat Cloud how to deploy and run your bot.

```ini
agent_name = "pcc-gemini-twilio"
secret_set = "pcc-gemini-twilio-secrets"

[scaling]
	min_agents = 1
```

**Understanding the TOML file settings:**

- `agent_name`: Your bot's name in Pipecat Cloud
- `secret_set`: Where your API keys are stored securely
- `min_agents`: Number of bot instances to keep ready (1 = instant start)

### Configure secrets

Upload your API keys to Pipecat Cloud's secure storage:

```bash
uv run pcc secrets set pcc-gemini-twilio-secrets --file .env
```

This creates a secret set called `pcc-gemini-twilio-secrets` (matching your TOML file) and uploads all your API keys from `.env`.

### Deploy

Pipecat Cloud will build your image in the cloud and deploy it when you run:

```bash
uv run pcc deploy
```

### Call your bot

Call the Twilio number you set up earlier to speak with your bot! 🚀

## Regional Setup (Vertex AI)

If you are located in **Latin America or another region where the Gemini Live AI Studio endpoint is unavailable**, you need to use **Google Vertex AI** instead of the default AI Studio backend. The standard `GeminiLiveLLMService` will time out because `generativelanguage.googleapis.com` does not serve all regions. Vertex AI lets you pin requests to a US region (`us-central1`) regardless of your location.

### Why this is needed

The Gemini Live WebSocket API via AI Studio is not available in all regions. Switching to Vertex AI routes your requests through a GCP region that supports the API (e.g., `us-central1`), bypassing the regional restriction entirely.

### Steps

1. **Use a GCP project with billing enabled.** Auto-created AI Studio projects work, but you must enable the Vertex AI API manually.

2. **Enable the Vertex AI API** on your GCP project:

   Go to [APIs & Services > Vertex AI API](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com) in the GCP Console and click **Enable**. Without this step, the WebSocket connection will close with a `1008 policy violation` error.

3. **Create a Service Account** with the **Vertex AI User** role and download a JSON key. Save it as `credentials.json` in the project root (it is gitignored — do not commit it).

4. **Update your `.env`** to include:

   ```ini
   GOOGLE_CLOUD_PROJECT=your-gcp-project-id
   GOOGLE_CREDENTIALS_PATH=./credentials.json
   TWILIO_ACCOUNT_SID=
   TWILIO_AUTH_TOKEN=
   ```

5. **Update `bot.py`** to use `GeminiLiveVertexLLMService`:

   ```python
   from pipecat.services.google.gemini_live.llm import InputParams
   from pipecat.services.google.gemini_live.llm_vertex import GeminiLiveVertexLLMService

   llm = GeminiLiveVertexLLMService(
       project_id=os.getenv("GOOGLE_CLOUD_PROJECT"),
       credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH"),
       location="us-central1",
       model="google/gemini-live-2.5-flash-native-audio",
       voice_id="Charon",
       system_instruction=instructions,
       tools=tools,
       params=InputParams(thinking=ThinkingConfig(thinking_budget=0)),
   )
   ```

> **Network note:** Some ISPs and home networks block WebSocket upgrade requests entirely. If you experience timeouts even after switching to Vertex AI, try running the bot on a mobile hotspot or through a VPN to rule out a network-level block.

## What's Next?

- **🔧 Customize your bot**: Modify `bot.py` to change personality, add functions, or integrate with your data
- **📚 Learn more**: Check out [Pipecat's docs](https://docs.pipecat.ai/) for advanced features
- **⚙️ Provide custom data**: [Learn how to provide custom data](https://docs.pipecat.ai/guides/telephony/twilio-websockets#custom-parameters-with-twiml) to your bot at run time
- **💬 Get help**: Join [Pipecat's Discord](https://discord.gg/pipecat) to connect with the community
