# IVR Navigation Bot

This project demonstrates how to create a voice bot that can automatically navigate Interactive Voice Response (IVR) phone systems using AI-powered decision making.

## How It Works

1. The server receives a request with the phone number to dial out to
2. The server creates a Daily room with SIP capabilities and starts the bot
3. The bot dials the specified number and connects to an IVR system
4. The IVR Navigator automatically detects menu options and navigates toward the specified goal
5. The bot uses DTMF tones and natural language responses to traverse the phone menu
6. Once the goal is reached, the bot ends the call

## Expected Navigation Path

When calling the test number (+1-412-314-6113), the bot will navigate through Daily Pharmacy's IVR system:

1. **Main Menu**: "Press 1 for prescription services, Press 2 for pharmacy hours..."

   - Bot selects option 1 (prescription services)

2. **Date of Birth Verification**: "Please enter your date of birth..."

   - Bot enters: 01011970 (configured for Mark Backman)

3. **Prescription Number**: "Please enter your 7 digit prescription number..."

   - Bot enters: 1234567 (configured prescription)

4. **Prescription Found**: "I found your prescription for Ibuprofen 800mg..."
   - Bot receives status information and completes the call

The IVR Navigator handles this navigation automatically using the goal and patient information configured in the bot.

## Prerequisites

### Daily

- A Daily account with an API key (or Daily API key from Pipecat Cloud account)
- A phone number purchased through Daily with dial-out enabled

For detailed setup instructions on purchasing phone numbers and enabling dial-out, see the [Daily PSTN dial-out example](https://github.com/pipecat-ai/pipecat-examples/tree/main/phone-chatbot/daily-pstn-dial-out).

### AI Services

- Deepgram API key for speech-to-text
- OpenAI API key for the LLM inference
- Cartesia API key for text-to-speech

### System

- Python 3.10+
- `uv` package manager (recommended) or pip
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

1. Start the server:

   ```bash
   uv run server.py
   ```

2. Test the IVR navigation functionality

   With server.py running, send the following curl command from your terminal:

   ```bash
   curl -X POST "http://localhost:7860/start" \
     -H "Content-Type: application/json" \
     -d '{
       "dialout_settings": {
         "phone_number": "+14123146113"
       }
     }'
   ```

   The server will create a room, the bot will join and dial the test IVR system. The bot will automatically navigate through the Daily Pharmacy IVR menu to obtain prescription status information for the user.

3. **Observe the call (optional)**

   You can join the Daily room to listen in on the IVR navigation. When the bot starts, you'll see a message in the console like:

   ```
   Joining https://YOUR-ACCOUNT.daily.co/AUTO-GENERATED-ROOM
   ```

   Open this URL in your browser to observe the bot navigating through the IVR system in real-time.

## Production Deployment

You can deploy your bot to Pipecat Cloud and server to your infrastructure to run this bot in a production environment.

#### Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) for tips on how to create secrets, build and push a docker image, and deploy your agent to Pipecat Cloud.

You'll only deploy your `bot.py` file.

#### Deploy the Server

The `server.py` handles dial-out requests and should be deployed separately from your bot:

- **Bot**: Runs on Pipecat Cloud (handles the conversation)
- **Server**: Runs on your infrastructure (receives requests and starts the bot)

#### Environment Variables for Production

Add these to your production environment:

```bash
ENV=production
PIPECAT_API_KEY=your_pipecat_cloud_api_key
PIPECAT_AGENT_NAME=your-agent-name
```

The server automatically detects the environment and routes bot starting requests accordingly.

## Learn More About IVR Navigation

For comprehensive information about IVR navigation capabilities, configuration options, and advanced usage patterns, see the [IVR Navigation Guide](https://docs.pipecat.ai/guides/fundamentals/ivr).

## Troubleshooting

### IVR navigation gets stuck

- Check that the bot's goal and patient information match the IVR system's expected inputs
- Review the bot logs for navigation decision details

### Call connects but no bot is heard

- Ensure your Daily API key is correct and has SIP capabilities
- Verify that the Cartesia API key and voice ID are correct
- Check that dial-out is enabled on your Daily domain

### Bot starts but disconnects immediately

- Check the Daily logs for any error messages
- Ensure your server has stable internet connectivity
