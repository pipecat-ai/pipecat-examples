# Push-to-Talk Voice AI Agent

A voice AI agent with push-to-talk functionality. Users hold a button to speak, and release it to send their message to the AI.

## How it Works

- **Client**: Hold the "Hold to Talk" button to speak, release to send
- **Server**: Audio input is gated, only flowing to the STT processor when the button is pressed
- **Real-time**: Uses WebRTC for low-latency audio communication

## Quick Start

To run this demo, you'll need two terminal windows.

### Terminal 1: Server Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment:

```bash
cp env.example .env
```

Edit `.env` and add your API keys:

- `CARTESIA_API_KEY`: For text-to-speech
- `OPENAI_API_KEY`: For the LLM
- `DEEPGRAM_API_KEY`: For speech-to-text
- `DAILY_API_KEY`: For WebRTC transport

4. Run the server:

```bash
python bot.py -t daily
```

### Terminal 2: Client Setup

1. Install dependencies:

```bash
npm i
npm i @pipecat-ai/daily-transport
```

2. Configure environment:

```bash
cp env.example .env.local
```

3. Start the client:

```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000)

## Usage

1. Click "Connect" to join the session
2. Hold "Hold to Talk" button and speak
3. Release the button to send your message
4. The AI will respond with audio
5. Click "Disconnect" to end the session

## Architecture

The push-to-talk functionality uses client-server message passing:

- Client sends `{type: "push_to_talk", data: {state: "start"}}` when button is pressed
- Server opens audio input gate, allowing frames to flow to STT
- Client sends `{type: "push_to_talk", data: {state: "stop"}}` when button is released
- Server closes audio input gate, triggering transcript processing

## Deploy your Bot to Pipecat Cloud

Follow the [quickstart instructions](https://docs.pipecat.ai/getting-started/quickstart#step-2%3A-deploy-to-production) to deploy your bot to Pipecat Cloud.
