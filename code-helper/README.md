# code-helper

This example demonstrates using `LLMTextProcessor` to categorize the LLM's
output text so that the client can easily render different types of output
accordingly, while the TTS speaks these same types in separate but also
custom ways, spelling out credit card numbers, while skipping trying to
read out code snippets or not saying the 'https' part of a url.

This example also includes a text entry box in the client to show how the
bot handles text input and can respond either with audio or not and the
categorization and "bot output" continues seemlessly.

The client in this example will render the user and bot transcripts using
simply the `user-transcript` and `bot-output` messages. The bot output will
render each sentence and then highlight each word as it is said. All code
provided by the bot will be highlighted as such and links will be formatted.

Concepts this example is meant to demonstrate:
- Custom handling of LLM text output for different purposes:
  - For the purpose of having the TTS skip certain outputs or speak certain
    outputs differently
  - For the purpose of supporting a client UI for easier rendering of
    different types of text or for altering for filtering out text before
    sending it to the client.
- Client <-> Bot Communication with RTVI
- Tool calling for sensitive information and custom handling of that
  information for TTS and RTVI purposes.
- Client->Server Text input

## Configuration

- **Bot Type**: Web
- **Transport(s)**: SmallWebRTC
- **Pipeline**: Cascade
  - **STT**: Deepgram
  - **LLM**: OpenAI
  - **TTS**: ElevenLabs

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
   cp .env.example .env
   # Edit .env and add your API keys
   ```

4. **Run the bot**:

   - SmallWebRTC: `uv run bot.py`

### Client

1. **Navigate to client directory**:

   ```bash
   cd client
   ```

2. **Install dependencies**:

   ```bash
   npm install
   ```

3. **Run development server**:

   ```bash
   npm run dev
   ```

4. **Open browser**:

   http://localhost:5173

## Project Structure

```
code-helper/
├── server/              # Python bot server
│   ├── bot.py           # Main bot implementation
│   ├── pyproject.toml   # Python dependencies
│   ├── .env.example     # Environment variables template
│   ├── .env             # Your API keys (git-ignored)
│   └── ...
├── client/              # Vanilla application
│   ├── src/             # Client source code
│   ├── package.json     # Node dependencies
│   └── ...
├── .gitignore           # Git ignore patterns
└── README.md            # This file
```
## Observability

This project includes observability tools to help you debug and monitor your bot:

## Learn More

- [Pipecat Documentation](https://docs.pipecat.ai/)
- [Pipecat GitHub](https://github.com/pipecat-ai/pipecat)
- [Pipecat Examples](https://github.com/pipecat-ai/pipecat-examples)
- [Discord Community](https://discord.gg/pipecat)