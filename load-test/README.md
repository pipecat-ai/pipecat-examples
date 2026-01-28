# Load Test Bot

A Pipecat bot designed for load testing that plays a video file on loop. This bot doesn't require any external API services and can run indefinitely for testing purposes.

## Features

- **Video Playback**: Plays the daily.y4m video file in a continuous loop
- **No External APIs**: Self-contained and doesn't require API keys
- **Pipecat Cloud Ready**: Includes deployment configuration

## Setup

1. Download the video file:

```bash
curl -L "https://gist.github.com/vipyne/c0c53abf0476a5b10ac7b90f581a35f6/raw/668580587d3fa7802fa4a73156b6a78f0b07f567/daily.y4m.zip" -o daily.y4m.zip
unzip daily.y4m.zip
```

2. Install dependencies:

```bash
uv sync
```

This will create a `uv.lock` file required for Docker builds.

3. Create environment file:

```bash
cp env.example .env
```

## Running Locally

Run with WebRTC transport:

```bash
uv run bot.py -t daily
```

The bot will:
- Play the daily.y4m video file at 30 fps
- Loop continuously until disconnected

## Deployment to Pipecat Cloud

1. Make sure you have the daily.y4m video file in the load-test directory.

2. Generate the lock file:

```bash
uv sync
```

3. Update `pcc-deploy.toml` with your Docker Hub username.

4. Log in to Pipecat Cloud:

```bash
pipecat cloud auth login
```

5. Configure secrets:

```bash
pipecat cloud secrets set load-test-secrets --file .env
```

6. Build and push Docker image:

```bash
pipecat cloud docker build-push
```

7. Deploy to Pipecat Cloud:

```bash
pipecat cloud deploy
```

**Note**:
- The `uv.lock` file is required for Docker builds but is not committed to the repository. Always run `uv sync` before deploying.
- The `daily.y4m` video file must be present in the load-test directory before building the Docker image.

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

This will start 5 agents (configurable via `-n` flag), each with a unique name (LoadTestBot-1, LoadTestBot-2, etc.).

```bash
# Start 10 agents
uv run start_agents.py -n 10
```

The script includes:
- **Rate limit handling**: Exponential backoff with tenacity on 429 responses
- **Auto-leave timeout**: Bots automatically leave after 10 minutes

## Configuration

The bot can be configured by modifying the parameters in `bot.py`:

- `GStreamerPipelineSource`:
  - `pipeline`: GStreamer pipeline string (plays daily.y4m on loop)
  - `video_width`: Output video width (default: 640)
  - `video_height`: Output video height (default: 480)

## How It Works

The bot uses Pipecat's `GStreamerPipelineSource` with a pipeline that:

1. Uses `multifilesrc` with `loop=-1` to play the Y4M file indefinitely
2. Decodes and converts the video with `decodebin` and `videoconvert`
3. Scales to the target resolution with `videoscale`
4. Outputs frames at 30 fps to the transport

This makes it ideal for load testing scenarios where consistent video output is needed without external dependencies.
5. Pushes frames to the transport output at the specified fps

The processor runs asynchronously and plays the video continuously until client disconnection, making this ideal for load testing scenarios.
