# Arize Tracing with Per-Turn Audio Links

Combines OpenInference/Arize tracing with per-turn audio recording. Each conversation turn gets its own root trace, and that turn span carries two attributes — `audio.user.url` and `audio.bot.url` — pointing to S3-hosted WAVs of just that turn's user utterance and bot reply.

The end-to-end flow:

1. `AudioBufferProcessor(enable_turn_audio=True)` fires `on_user_turn_audio_data` at `UserStoppedSpeakingFrame` and `on_bot_turn_audio_data` at `BotStoppedSpeakingFrame`.
2. For each event we generate a presigned S3 GET URL **synchronously** (no S3 round-trip) using a deterministic key, set it as an attribute on the active `OpenInferenceObserver._turn_span`, and kick off the actual `put_object` upload as a background task.
3. The Arize/Phoenix span carries the URL immediately — the link starts working as soon as the upload lands.

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) installed
- Service accounts: Deepgram, Cartesia, Google (Gemini), AWS S3
- Either an Arize account *or* a local Phoenix server for trace viewing

## Setup

### 1. Install dependencies

```bash
uv sync
```

For local trace viewing with Phoenix instead of Arize:

```bash
uv sync --group phoenix
```

### 2. Create an S3 bucket and IAM user

The example uses a **long-lived IAM user** (not assumed-role / STS) so presigned URLs are valid for up to 7 days.

Run the helper script to create the bucket (if it doesn't already exist) and an IAM user with the minimal `s3:PutObject` + `s3:GetObject` policy, and emit access keys:

```bash
AWS_PROFILE=your_aws_profile ./create_s3_user.sh <BUCKET_NAME>
```

Requires `aws` CLI and `jq`. The script:

- Creates `<BUCKET_NAME>` in your configured region (defaults to `us-east-1`) with a public-access block applied. If the bucket already exists, it's left as-is.
- Creates IAM user `pipecat-turn-audio-uploader` with an inline policy granting `s3:PutObject` + `s3:GetObject` on the bucket.
- Prints `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, and `AWS_BUCKET_NAME` lines ready to paste into `.env`.

   To create the user manually instead, attach this inline policy (substitute `<BUCKET>`):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["s3:PutObject", "s3:GetObject"],
       "Resource": "arn:aws:s3:::<BUCKET>/*"
     }]
   }
   ```

### 3. Configure `.env`

Copy `env.example` → `.env` and fill in the values:

```bash
cp env.example .env
```

| Variable | Required? | Notes |
| --- | --- | --- |
| `DEEPGRAM_API_KEY` | yes | STT |
| `CARTESIA_API_KEY` | yes | TTS |
| `GOOGLE_API_KEY` | yes | Gemini LLM |
| `AWS_ACCESS_KEY_ID` | yes | Long-lived IAM user key |
| `AWS_SECRET_ACCESS_KEY` | yes | Long-lived IAM user secret |
| `AWS_DEFAULT_REGION` | yes | e.g. `us-east-1` |
| `AWS_BUCKET_NAME` | yes | Bucket the per-turn WAVs go into |
| `AWS_S3_PREFIX` | no | Path prefix inside the bucket. Default `pipecat-turn-audio` |
| `ARIZE_API_KEY` | one of these | App.arize.com → Settings → API Keys → User API Keys |
| `ARIZE_SPACE_ID` | one of these | App.arize.com → Settings → Space Settings (top right) |
| `ARIZE_PROJECT_NAME` | optional | Defaults to `default` |
| `PHOENIX_PROJECT_NAME` | one of these | Used if `ARIZE_*` not set |
| `PHOENIX_COLLECTOR_ENDPOINT` | optional | Default `http://localhost:6006` |

The bot picks **Arize** if both `ARIZE_API_KEY` and `ARIZE_SPACE_ID` are set; otherwise it falls back to Phoenix.

### 4. (Phoenix only) Start the Phoenix server

In a separate terminal:

```bash
uv run phoenix serve
```

Phoenix UI: <http://localhost:6006>

### 5. Run the bot

```bash
uv run bot.py -t webrtc
```

You should see:

```
🚀 Bot ready!
   → Open http://localhost:7860/client in your browser
```

Open that URL, click "Connect", and have a conversation. Each user-utterance/bot-reply pair becomes one `pipecat.conversation.turn` trace.

Other transports:

```bash
uv run bot.py -t daily      # Daily.co room
uv run bot.py -t twilio     # Twilio Media Streams
uv run bot.py --help        # See all flags
```

## Viewing the audio

In the Arize (or Phoenix) trace UI, open a `pipecat.conversation.turn` span and look at its attributes. `audio.user.url` and `audio.bot.url` are clickable HTTPS links — paste in a browser to play, or feed to an `<audio>` tag.

URLs are signed for **7 days** by default (`url_expiry_seconds` in `TurnAudioUploader`).

S3 layout per conversation:

```
s3://<bucket>/<prefix>/<conversation_id>/turn-0001/user.wav
s3://<bucket>/<prefix>/<conversation_id>/turn-0001/bot.wav
s3://<bucket>/<prefix>/<conversation_id>/turn-0002/user.wav
...
```

## Notes

- We compose with the existing `OpenInferenceObserver` rather than subclassing — `audio_buffer` event handlers reach into `oi_observer._turn_span` to set attributes. Touches a private-ish field, but keeps the example readable.
- Per-turn audio is small (~100 KB – 1 MB), so a single `put_object` is plenty; no multipart needed.
- The presigned URL is generated **before** the upload completes. The link 404s briefly until the upload lands; if the upload fails the link stays dead. Look for `Failed to upload turn audio` in logs.

## Troubleshooting

- **`OpenInferenceObserver not found on PipelineTask`** — `PipecatInstrumentor.instrument()` failed to wrap `PipelineTask.__init__`. Confirm the import path of `PipecatInstrumentor` and that `instrument()` is called *before* `PipelineTask(...)` is constructed.
- **`audio.user.url` / `audio.bot.url` missing on a span** — turn ended faster than the audio handler fired. Check the debug log file (`pipecat-test-conversation-001_*.log`) for `No active turn span; skipping ... audio attribute`.
- **Link 404s in the trace** — the background `put_object` hasn't finished or failed. Check logs for `Uploaded turn audio to s3://...` or `Failed to upload turn audio`.
- **Link expires too soon** — bump `url_expiry_seconds` in `bot_utils/turn_audio_uploader.py` (max 7 days for SigV4).

## References

- [openinference-instrumentation-pipecat](https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-pipecat)
- [AudioBufferProcessor turn events](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/processors/audio/audio_buffer_processor.py)
- Sister examples: [`open-telemetry/arize`](../arize), [`audio-recording-s3-multipart-upload`](../../audio-recording-s3-multipart-upload)
