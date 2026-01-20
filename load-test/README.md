# Load Test Bot

A Pipecat bot designed for load testing that generates video and audio frames programmatically. This bot doesn't require any external API services and can run indefinitely for testing purposes.

## Features

- **Video Generation**: Generates numbered frames with cycling colors (red, green, blue, yellow, magenta, cyan)
- **Audio Generation**: Produces periodic beep sounds using numpy
- **No External APIs**: Self-contained and doesn't require API keys
- **Pipecat Cloud Ready**: Includes deployment configuration

## Setup

1. Install dependencies:

```bash
uv sync
```

2. Create environment file (no API keys needed):

```bash
cp env.example .env
```

## Running Locally

Run with WebRTC transport:

```bash
uv run python bot.py
```

The bot will:
- Generate video frames at 30 fps with numbered, colored backgrounds
- Generate audio beeps every 2 seconds
- Output continuously until disconnected

## Deployment to Pipecat Cloud

1. Build and tag the Docker image:

```bash
uv sync
docker build -t your_username/load-test:0.1 .
```

2. Push to Docker registry:

```bash
docker push your_username/load-test:0.1
```

3. Update `pcc-deploy.toml` with your image name and credentials.

4. Deploy using Pipecat Cloud CLI:

```bash
pcc deploy
```

## Configuration

The bot can be configured by modifying the parameters in `bot.py`:

- `FrameGeneratorProcessor`:
  - `width`, `height`: Video frame dimensions (default: 640x480)
  - `fps`: Frames per second (default: 30)

- `AudioGeneratorProcessor`:
  - `sample_rate`: Audio sample rate (default: 16000 Hz)
  - `beep_interval`: Time between beeps in seconds (default: 2.0)
  - `frequency`: Beep frequency in Hz (default: 440 Hz - A4 note)
  - `duration`: Beep duration in seconds (default: 0.2)

## How It Works

The bot uses two main processors:

1. **FrameGeneratorProcessor**: Continuously generates `OutputImageRawFrame` objects with:
   - Incrementing frame numbers
   - Cycling background colors
   - Large text display for easy identification

2. **AudioGeneratorProcessor**: Continuously generates `OutputAudioRawFrame` objects with:
   - Sine wave beeps at 440 Hz
   - Smooth fade in/out to prevent clicks
   - Configurable interval between beeps

Both processors run asynchronously and push frames to the transport output continuously, making this ideal for load testing scenarios.
