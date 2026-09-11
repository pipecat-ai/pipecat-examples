# Gradium Voice Designer

Design a brand-new voice with [Gradium voice design](https://docs.gradium.ai/guides/voices/voice-design),
audition three takes, keep the one you like, and get a [Pipecat](https://github.com/pipecat-ai/pipecat)
voice agent that speaks with it plus a web client to talk to it.

> [!TIP]
> This example is a committed Claude Code skill (`.claude/skills/design-voice/`).
> Open this folder in [Claude Code](https://claude.com/claude-code) and ask for a
> voice; the skill drives everything below.

Copy `env.example` to `.env` and drop your Gradium key in it
(`GRADIUM_API_KEY=…`), plus, optionally, the service key for your bot's LLM
(`OPENAI_API_KEY`, `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY`). Then ask Claude
Code for a voice.

- **Text mode**: say what the voice should be like ("a gruff Irish innkeeper",
  "a calm support agent"). The skill asks a couple of questions, shows you the
  description, and generates three takes once you approve it.
- **Image mode**: drop a PNG or JPEG of the character in this folder first. The
  skill reads it, drafts the description, name and persona from it, and shows
  them for approval before generating.
- Either way you hear three takes and keep one. The skill then generates `server/`
  (a Pipecat agent speaking in the new voice) and `client/` (a web page that shows
  the image and talks to it). Both folders are created by the skill; nothing but
  the skill itself is committed here.

```
Gradium (STT) → OpenAI, Gemini or Anthropic (LLM) → Gradium (TTS)
```

## Running what it generated

Two terminals:

```bash
cd server
uv sync
uv run bot.py
```

```bash
cd client
npm install
npm run dev
```

Open the URL Vite prints, allow the microphone, and click Connect. The client is
built from the [Pipecat UI](https://ui.pipecat.ai/) shadcn registry, so
`npx shadcn@latest add @pipecat/<name>` adds more components to it.
