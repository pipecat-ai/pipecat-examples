# file-upload

This example demonstrates how clients can upload files and images to provide
visual context to the bot during a voice conversation. Users can either select
a local file from their computer or provide a URL pointing to an image or
document. In both cases an optional text prompt can accompany the upload to
guide the LLM's response.

## How it works

1. **Upload.** The client POSTs the file to the upload endpoint the runner
   advertised as `fileUploadUrl` in its `/start` response. The endpoint hands
   the file to the bot's storage backend and returns a URL (`pipecat:<id>`
   for local storage, `gs://`/`s3://` for the cloud-bucket bots).
2. **Send.** The client passes that URL back in an RTVI `send-file` message
   (`client.sendFile`). The bot stores only the URL in the LLM context —
   small files can also be sent inline, skipping the upload.
3. **Resolve.** At completion time the LLM service's `FileResolver` resolves
   the URL per provider: a URL the provider can fetch itself is passed
   straight through, and anything else is downloaded by the bot and inlined.
   The LLM then reasons about the content and responds with audio as it would
   for any other user turn.

## The bots

Three bots share one pipeline (defined in `bot.py`) and differ only in where
uploads are stored:

| Bot          | Storage              | Minted URL      | Read directly by                 |
| ------------ | -------------------- | --------------- | -------------------------------- |
| `bot.py`     | Local disk           | `pipecat:<id>`  | — (always inlined by the bot)    |
| `bot_gcs.py` | Google Cloud Storage | `gs://...`      | Gemini on Vertex AI (`-llm vertex`) |
| `bot_s3.py`  | Amazon S3            | `s3://...`      | AWS Bedrock (`-llm bedrock`)     |

Every bot works with every LLM provider (`-llm anthropic|openai|bedrock|gemini|vertex`).
The "read directly" column is the pass-through fast path: when the provider
can reach the bucket through its own IAM, the bot never touches the bytes.
With any other provider, the bot downloads the file from the bucket with its
own credentials and sends the provider the bytes instead.

The cloud-bucket bots show the host-agnostic way to plug in custom storage:
implement `FileStorage` (`GCSFileStorage`/`S3FileStorage` here) and declare a
`create_file_storage()` function alongside `bot()`. Whichever host runs the
bot discovers the function there, backs its upload endpoint with the returned
storage, and injects it into the bot as `runner_args.file_storage`, which the
bot hands to its LLM service's `FileResolver` — so the same bot file runs
unchanged under the development runner or a cloud platform's base image.
`bot.py` declares no storage of its own and gets the runner's local-disk
default (`-u/--uploads-folder` or `PIPECAT_UPLOADS_FOLDER`).

Concepts this example is meant to demonstrate:

- Client → Server file upload via RTVI (`client.sendFile`)
- Handling both local file uploads and URL-based content references
- `FileResolver` on the LLM service for resolving file URLs per provider,
  including `gs://`/`s3://` pass-through to providers with bucket access
- Custom `FileStorage` backends (local disk, GCS, S3) for the upload
  endpoint, declared host-agnostically via `create_file_storage()`
- `onBotOutput` with per-word spoken highlighting in the client UI

## Configuration

- **Bot Type**: Web
- **Transport(s)**: SmallWebRTC, Daily (WebRTC)
- **Pipeline**: Cascade
  - **STT**: Deepgram
  - **LLM**: Anthropic Claude (default), OpenAI, AWS Bedrock, or Google
    Gemini via the developer API or Vertex AI — select with `-llm`
  - **TTS**: Cartesia

## Setup

### Server

1. **Navigate to server directory**:

   ```bash
   cd server
   ```

2. **Install dependencies**:

   ```bash
   uv sync
   ```

3. **Configure environment variables**:

   ```bash
   cp env.example .env
   # Edit .env and add your API keys
   ```

4. **Run the bot**:

   ```bash
   uv run bot.py
   ```

   Uploaded files are saved to the folder named by `PIPECAT_UPLOADS_FOLDER`
   in `.env` (or pass `-u <path>`). To store uploads in a cloud bucket
   instead, run one of the storage-backend variants (after setting
   `GCS_UPLOADS_BUCKET` / `S3_UPLOADS_BUCKET` and credentials in `.env`):

   ```bash
   uv run bot_gcs.py -llm vertex   # uploads in GCS; Vertex Gemini reads gs:// directly
   uv run bot_s3.py -llm bedrock   # uploads in Amazon S3
   ```

   The runner serves every transport; the caller selects which one (a web/mobile
   client picks its transport when it connects; a telephony provider connects to
   `/ws`).

### Client

1. **Navigate to client directory**:

   ```bash
   cd client
   ```

2. **Install dependencies**:

   ```bash
   npm install
   ```

3. **Configure environment variables**:

   ```bash
   cp env.example .env.local
   # Edit .env.local if needed (defaults to localhost:7860)
   ```

   > **Note:** Environment variables in Vite are bundled into the client and exposed in the browser. For production applications that require secret protection, consider implementing a backend proxy server to handle API requests and manage sensitive credentials securely.

4. **Run development server**:

   ```bash
   npm run dev
   ```

5. **Open browser**:

   http://localhost:5173

## Project Structure

```
file-upload/
├── server/              # Python bot server
│   ├── bot.py           # Main bot (local-disk upload storage)
│   ├── bot_gcs.py       # Same bot, uploads in Google Cloud Storage
│   ├── bot_s3.py        # Same bot, uploads in Amazon S3
│   ├── pyproject.toml   # Python dependencies
│   ├── env.example      # Environment variables template
│   ├── .env             # Your API keys (git-ignored)
│   ├── Dockerfile       # Container image for Pipecat Cloud
│   └── pcc-deploy.toml  # Pipecat Cloud deployment config
├── client/              # Vanilla application
│   ├── src/             # Client source code
│   ├── package.json     # Node dependencies
│   └── ...
├── .gitignore           # Git ignore patterns
└── README.md            # This file
```

## Deploying to Pipecat Cloud

Note that the upload endpoint is currently a development-runner feature, so
files larger than the transport's message size limit can't be uploaded when the
bot is deployed to Pipecat Cloud — production deployments need their own upload
endpoint (see `PipecatClient.uploadFile(file, uploadFileParams)`) until Pipecat
Cloud serves one backed by the same `create_file_storage()` declaration this
example uses. Sending small files, and referencing files by URL, work in both
environments.

This project is configured for deployment to Pipecat Cloud. You can learn how to deploy to Pipecat Cloud in the [Pipecat Quickstart Guide](https://docs.pipecat.ai/getting-started/quickstart#step-2-deploy-to-production).

Refer to the [Pipecat Cloud Documentation](https://docs.pipecat.ai/deployment/pipecat-cloud/introduction) to learn more about configuring, deploying, and managing your agents in Pipecat Cloud.

## Building with an AI coding agent

Extending this bot with Claude Code, Codex, or another AI coding assistant? Give it live, accurate Pipecat context instead of stale training data with the **Pipecat Context Hub** — a local index of Pipecat docs, examples, and API source your agent queries over MCP:

```bash
# Build the local index (first run takes a couple of minutes)
uvx pipecat-ai-context-hub@latest refresh

# Add it to your agent (use the line for the one you use)
claude mcp add pipecat-context-hub -- uvx pipecat-ai-context-hub serve   # Claude Code
codex mcp add pipecat-context-hub -- uvx pipecat-ai-context-hub serve    # Codex
```

MCP servers load at session start, so add it before opening your coding session. See the [Pipecat Context Hub docs](https://docs.pipecat.ai/api-reference/context-hub) for the full setup.

## Learn More

- [Pipecat Documentation](https://docs.pipecat.ai/)
- [Pipecat GitHub](https://github.com/pipecat-ai/pipecat)
- [Pipecat Examples](https://github.com/pipecat-ai/pipecat-examples)
- [Discord Community](https://discord.gg/pipecat)