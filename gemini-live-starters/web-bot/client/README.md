# Voice UI Kit Client

A Next.js application showcasing screensharing with the Voice UI Kit and Gemini Live Multimodal model.

## Features

- **Real-time conversation** with Gemini via Pipecat
- **Screen sharing** (desktop) with resizable panels
- **Device controls** for camera, microphone, and speakers
- **Live transcripts** for both user and bot
- **Audio visualization** of bot responses
- **Event logs panel** with toggle and resize capabilities

## Quick Start

1. **Install dependencies**:

   ```bash
   npm install
   ```

2. **Configure environment**:

   ```bash
   cp env.example .env.local
   # Edit .env.local to connect to your bot deployed on Pipecat Cloud
   ```

3. **Start development server**:

   ```bash
   npm run dev
   ```

4. **Open** [http://localhost:3000](http://localhost:3000) and click **Connect**

## Configuration

### Local Development

The .env.local file automatically falls back to the `http://localhost:7860/start` endpoint, which will hit the bot's built-in FastAPI server and start a room. No changes are needed.

### Pipecat Cloud Deployment

Set your agent credentials in `.env.local`:

```bash
BOT_START_URL=https://api.pipecat.daily.co/v1/public/<agent-name>/start
BOT_START_PUBLIC_API_KEY=pk_your_api_key_here
```

## Usage

1. **Connect** to establish a session with the bot
2. **Select devices** using the dropdown menus
3. **Share screen** (desktop only) to let Gemini analyze your screen
4. **View transcripts** and **audio visualization** in real-time
5. **Toggle logs** and **resize panels** as needed

## Mobile Support

Screen sharing is disabled on mobile devices. A warning message will be displayed.

## Tech Stack

- **Next.js 15.5.4** with React 19.1.0
- **Pipecat Voice UI Kit** for real-time communication
- **Tailwind CSS 4** for styling
- **Lucide React** for icons
