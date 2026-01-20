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

3. Create environment file (no API keys needed):

```bash
cp env.example .env
```

## Running Locally

Run with WebRTC transport:

```bash
uv run python bot.py
```

The bot will:
- Play the daily.y4m video file at 30 fps
- Loop continuously until disconnected

## Deployment to Pipecat Cloud

1. Make sure you have the daily.y4m video file in the load-test directory

2. Generate the lock file and build the Docker image:

```bash
uv sync
docker build -t your_username/load-test:0.1 .
```

3. Push to Docker registry:

```bash
docker push your_username/load-test:0.1
```

4. Update `pcc-deploy.toml` with your image name and credentials.

5. Deploy using Pipecat Cloud CLI:

```bash
pcc deploy
```

**Note**: 
- The `uv.lock` file is required for Docker builds but is not committed to the repository. Always run `uv sync` before building the Docker image.
- The `daily.y4m` video file must be present in the load-test directory before building the Docker image.

## Configuration

The bot can be configured by modifying the parameters in `bot.py`:

- `Y4MVideoPlayer`:
  - `video_path`: Path to the Y4M video file (default: "./daily.y4m")
  - `fps`: Frames per second for playback (default: 30)

## How It Works

The bot uses a `Y4MVideoPlayer` processor that:

1. Loads the Y4M video file on startup
2. Parses the Y4M header to extract video dimensions and format
3. Reads all frames into memory
4. Continuously loops through frames, converting YUV420 to RGB
5. Pushes frames to the transport output at the specified fps

The processor runs asynchronously and plays the video continuously until client disconnection, making this ideal for load testing scenarios.
