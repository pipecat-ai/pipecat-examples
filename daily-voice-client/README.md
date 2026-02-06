# Daily Voice Client

This example demonstrates a simple voice conversation bot using Daily as the WebRTC transport. The bot listens to user speech, transcribes it using Google STT, processes it with Google's Gemini LLM, and responds using Google TTS with natural voice.

The example includes both a Python bot server and a JavaScript/TypeScript web client built with the Pipecat JavaScript SDK.

## Requirements

- **Python 3.10+**
- **Node.js 16+**
- **Daily API key** - Get one at [daily.co](https://www.daily.co/)
- **Google Cloud credentials** - Two types are needed:
  - `GOOGLE_API_KEY` - For the Gemini LLM service
  - `GOOGLE_TEST_CREDENTIALS` - Service account JSON credentials for STT/TTS services
- **Modern web browser with WebRTC support**

## Setup

### 1. Install Python Dependencies

Create your virtual environment and install dependencies:

```bash
uv sync
```

### 2. Configure Environment Variables

Copy the example environment file and add your credentials:

```bash
cp env.example .env
```

Edit `.env` and fill in:
- `DAILY_API_KEY` - Your Daily API key
- `DAILY_ROOM_URL` - (Optional) A specific Daily room URL for local development
- `GOOGLE_API_KEY` - Your Google API key for Gemini
- `GOOGLE_TEST_CREDENTIALS` - Path to your Google Cloud service account JSON file

### 3. Install Client Dependencies

Navigate to the client directory and install dependencies:

```bash
cd client
npm install
cd ..
```

## Running the Example

### 1. Start the Bot Server

From the project root directory, start the bot server:

```bash
uv run bot.py -t daily
```

The server will start on `http://localhost:7860`.

### 2. Start the Client

In a separate terminal, navigate to the client directory and start the development server:

```bash
cd client
npm run dev
```

The client will be available at `http://localhost:5173`.

### 3. Connect and Test

1. Open `http://localhost:5173` in your browser
2. Click the "Connect" button to join the conversation
3. Allow microphone access when prompted
4. The bot will introduce itself and you can start talking

## How It Works

### Bot Server (`bot.py`)

The Python bot uses Pipecat's pipeline architecture:
- **DailyTransport** - Manages WebRTC connection via Daily
- **GoogleSTTService** - Transcribes user speech to text (Chirp 3 model)
- **GoogleLLMService** - Processes conversation with Gemini 2.5 Flash
- **GoogleTTSService** - Generates natural-sounding speech responses
- **LocalSmartTurnAnalyzerV3** - Detects when the user has finished speaking
- **SileroVADAnalyzer** - Voice activity detection for turn-taking

### Web Client (`client/`)

The TypeScript client uses the Pipecat JavaScript SDK:
- **PipecatClient** - Main client for managing the bot connection
- **DailyTransport** - WebRTC transport layer using Daily.co
- Handles audio streaming, transcription display, and connection lifecycle
- Built with Vite for fast development and optimized production builds

## Important Notes

- The bot server **must** be running before connecting with the client
- Ensure all environment variables are correctly configured
- The bot will automatically introduce itself when a client connects
- Audio is streamed in real-time with low latency using WebRTC