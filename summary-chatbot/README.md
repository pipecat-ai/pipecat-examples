# Background Summary Bot

This bot joins a Daily call in the background and provides real-time summaries of the conversation without sending any audio back to the participants. It operates silently and generates concise summaries of key discussion points as the conversation progresses.

## Features

- Silent background operation (no audio output)
- Real-time speech-to-text transcription
- Automatic generation of conversation summaries
- Live logging of conversation and summaries
- Non-intrusive monitoring

## Get started

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp env.example .env # and add your credentials
```

## Run the server

```bash
python server.py
```

Then, visit `http://localhost:7860/` in your browser to start the bot and get a Daily room URL.

## How it works

1. The bot joins the Daily call silently (no audio output)
2. It uses Deepgram STT to transcribe conversation in real-time
3. Each transcription segment is processed through OpenAI to generate a brief summary
4. Both original transcripts and summaries are logged with timestamps
5. The bot operates completely in the background without interrupting the conversation

## Use Cases

- Meeting note-taking
- Conversation monitoring
- Real-time discussion summaries
- Call analytics and insights
- Automated meeting documentation

## Configuration

Set the following environment variables in your `.env` file:

- `DAILY_API_KEY` - Your Daily.co API key
- `OPENAI_API_KEY` - Your OpenAI API key  
- `DEEPGRAM_API_KEY` - Your Deepgram API key for speech-to-text
