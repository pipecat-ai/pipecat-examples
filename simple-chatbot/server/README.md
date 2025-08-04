# Simple Chatbot Server

A Pipecat server-side bot that connects to a Pipecat client, enabling a user to talk to the bot through their browser or mobile device.

## Available Bots

The server supports two bot implementations:

1. **OpenAI Bot**

   - Uses gpt-4o for conversation
   - Requires OPENAI_API_KEY

2. **Gemini Bot**
   - Uses Google's Gemini model
   - Requires GOOGLE_API_KEY

Select your preferred bot by running the corresponding bot.py file:

- `bot-openai.py` for OpenAI
- `bot-gemini.py` for Gemini

## Setup

1. Configure environment variables

   Create a `.env` file:

   ```bash
   cp env.example .env
   ```

   Then, add your API keys:

   ```ini
   # Required API Keys
   DAILY_API_KEY=           # Your Daily API key
   OPENAI_API_KEY=          # Your OpenAI API key (required for OpenAI bot)
   GOOGLE_API_KEY=          # Your Google Gemini API key (required for Gemini bot)
   ELEVENLABS_API_KEY=      # Your ElevenLabs API key

   # Optional Configuration
   DAILY_API_URL=           # Optional: Daily API URL (defaults to https://api.daily.co/v1)
   DAILY_SAMPLE_ROOM_URL=   # Optional: Fixed room URL for development
   ```

2. Set up a virtual environment and install dependencies

   ```bash
   cd server
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

   > Using `uv`? Create your venv using: `uv sync`

3. Run the bot:

   ```bash
   python bot-openai.py --transport daily
   ```

   > Using `uv`? Run your bot using: `uv run bot-openai.py --transport daily`

## Troubleshooting

If you encounred this error:

```bash
aiohttp.client_exceptions.ClientConnectorCertificateError: Cannot connect to host api.daily.co:443 ssl:True [SSLCertVerificationError: (1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)')]
```

It's because Python cannot verify the SSL certificate from https://api.daily.co when making a POST request to create a room or token.

This issue occurs when the system doesn't have the proper CA certificates.

Install SSL Certificates (macOS): `/Applications/Python\ 3.12/Install\ Certificates.command`
