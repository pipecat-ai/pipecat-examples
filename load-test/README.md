# Load Test Bot

A Pipecat bot designed for load testing that generates video using GStreamer. This bot doesn't require any external API services and can run indefinitely for testing purposes.

## Features

- **Video Generation**: Generates a continuous video test pattern using GStreamer's videotestsrc
- **No External APIs**: Self-contained and doesn't require API keys
- **Pipecat Cloud Ready**: Includes deployment configuration

## Setup

1. Install dependencies:

```bash
uv sync
```

This will create a `uv.lock` file required for Docker builds.

2. Create environment file:

```bash
cp env.example .env
```

3. (Local only) Install GStreamer on your system:

**macOS:**
```bash
brew install gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly
```

**Ubuntu/Debian:**
```bash
sudo apt-get install libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
```

## Running Locally

Run with WebRTC transport:

```bash
uv run bot.py -t daily
```

The bot will:
- Generate a continuous video test pattern (bouncing ball)
- Output video until disconnected

## Deployment to Pipecat Cloud

1. Generate the lock file:

```bash
uv sync
```

2. Update `pcc-deploy.toml` with your Docker Hub username.

3. Log in to Pipecat Cloud:

```bash
pipecat cloud auth login
```

4. Configure secrets:

```bash
pipecat cloud secrets set load-test-secrets --file .env
```

5. Build and push Docker image:

```bash
pipecat cloud docker build-push
```

6. Deploy to Pipecat Cloud:

```bash
pipecat cloud deploy
```

**Note**: The `uv.lock` file is required for Docker builds but is not committed to the repository. Always run `uv sync` before deploying.

## Starting Multiple Agents

Use `start_agents.py` to spawn multiple load test bots that join a specific Daily room:

1. Set environment variables:

```bash
export DAILY_ROOM_URL=https://yourdomain.daily.co/yourroom
export DAILY_API_KEY=your_daily_api_key
export PIPECAT_API_KEY=your_pipecat_api_key
```

2. Run the script:

```bash
uv run start_agents.py
```

This will start 5 agents (configurable via `NUM_AGENTS` in the script), each with a unique name (LoadTestBot-1, LoadTestBot-2, etc.).

The script includes:
- **Rate limit handling**: Exponential backoff with tenacity on 429 responses
- **Auto-leave timeout**: Bots automatically leave after 10 minutes

## Configuration

The bot can be configured by modifying the parameters in `bot.py`:

- `GStreamerPipelineSource`:
  - `pipeline`: GStreamer pipeline string (default: videotestsrc with ball pattern)
  - `video_width`: Output video width (default: 1280)
  - `video_height`: Output video height (default: 720)

## How It Works

The bot uses Pipecat's `GStreamerPipelineSource` processor that:

1. Creates a GStreamer pipeline with `videotestsrc` to generate video
2. Converts frames to RGB format at the specified resolution
3. Continuously pushes `OutputImageRawFrame` objects to the transport

This makes it ideal for load testing scenarios where consistent video output is needed without external dependencies.
