# Faster Than Realtime

This example demonstrates how to use Pipecat's faster-than-realtime audio delivery.

## How It Works

### The Core Trick: Mismatched Sample Rates

Pipecat's TTS (Cartesia, in this example) produces audio at **24 kHz**. Normally
the bot declares a 24 kHz `CustomAudioSource` to Daily and writes audio at real-time
speed.

With faster-than-realtime enabled, the bot declares the source at **48 kHz** while
still writing 24 kHz PCM bytes. WebRTC pipeline believes it is receiving a
48 kHz stream, so `write_frames()` returns twice as fast — audio is delivered to the
client at **~2× real-time speed**.

```
Bot (Pipecat)                                   Client (browser)
─────────────────────────────────────────────────────────────────
Cartesia TTS → 24 kHz PCM
   │
   │  audio_out_declared_sample_rate=48000
   ▼
Daily CustomAudioSource (thinks it's 48 kHz)
   │  write_frames() returns 2× faster than real-time
   ▼
WebRTC ──────────────────────────────────────► DailyTransport
                                                 │ fasterThanRealtime: true
                                                 ▼
                                               BotAudioPlayer
                                                 │ Capture ctx @ 48 kHz
                                                 │ Playback ctx @ 24 kHz
                                                 ▼
                                               <audio> element (correct pitch)
```

### Pre-buffer (`audio_out_prebuffer_secs`)

TTS jitter means the first few frames may arrive unevenly. The bot accumulates
**500 ms** of audio before sending anything to Daily. Once the threshold is met, all
held frames are flushed at once and subsequent frames are sent immediately. This
ensures a smooth start without sacrificing delivery speed for the rest of the
utterance. The pre-buffer resets automatically on each interruption.

### Client-Side Decoding

Because the audio arrives at 2× speed the browser must undo the rate mismatch before
playing it. The `BotAudioPlayer` inside `@pipecat-ai/daily-transport` uses two
`AudioContext` instances:

1. **Capture context** at 48 kHz — captures the incoming WebRTC track via an
   `AudioWorklet` (`CaptureProcessor`) that converts each 128-sample render quantum
   to `Int16Array` and detects silence.

2. **Playback context** (`WavStreamPlayer`) at 24 kHz — receives those Int16 chunks
   and produces a correctly-pitched `MediaStreamTrack` that plays at the right speed
   and pitch.

**Silence handling**: WebRTC injects all-zero silence between speech bursts, and
because audio arrives at 2× speed that silence queues up twice as fast. The client
discards silence frames when the playback buffer is healthy (≥100 ms), mirroring
the Python pre-buffer logic.

**Interruption**: When the user starts speaking, the bot sends a
`user-started-speaking` app message. The client clears the playback buffer and
rotates an internal track ID so `WavStreamPlayer`'s interrupted-track blacklist
does not block the next utterance.

## Known Limitations

> **Note:** The browser client is a proof of concept. The approach is not stable
> enough for production use today due to the browser limitations described below.

### Echo Cancellation

WebRTC's acoustic echo cancellation (AEC) works by correlating the speaker output
with the microphone input at the OS/browser level. `BotAudioPlayer` intercepts the
Daily track and re-routes it through a synthetic `WavStreamPlayer` output track,
breaking the AEC reference signal. A silent `<audio volume=0>` element is also
attached to the original track to activate Chrome's pipeline, which compounds the
problem. The result is degraded echo cancellation on all browsers, and it is
especially noticeable on Safari.

### iOS / Safari

The dual-`AudioContext` approach is largely broken on iOS Safari. `sinkId: { type: "none" }` — 
used to prevent the capture context from reaching the speakers — is not supported, and iOS 
enforces strict autoplay and audio context resume policies that conflict with how `BotAudioPlayer`
is initialised.

> You can hear both tracks playing at the same time on iOS.

### Comfort Noise Accumulation

The silence detection threshold (`maxAbs < 5`) catches all-zero WebRTC padding. 
It may not catch WebRTC comfort noise (CN) frames, which are low-amplitude but not silent. 
If CN frames pass through as speech they accumulate in the playback buffer at delivery speed, 
potentially causing a growing delay over long conversations.

### CPU Overhead

Running two `AudioContext` instances simultaneously with an `AudioWorklet` is more
expensive than a single context. On mid-range mobile devices this can cause audio
glitches if the CPU is also busy with network or LLM activity.

## Quick Start

### 1. Start the Bot Server

1. Navigate to the `faster-than-realtime` directory:

   ```bash
   cd faster-than-realtime
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Copy the env file and add your API keys:

   ```bash
   cp env.example .env
   ```

4. Start the server:

   ```bash
   uv run bot.py
   ```

### 2. Connect Using the Web Client

For client setup, refer to the [Client README](client/README.md).

## Requirements

- Python 3.11+
- Node.js 18+ (for the web client)
- Daily API key
- Cartesia API key (used for both STT and TTS)
- OpenAI API key
- Modern web browser with WebRTC support (Chrome recommended)
