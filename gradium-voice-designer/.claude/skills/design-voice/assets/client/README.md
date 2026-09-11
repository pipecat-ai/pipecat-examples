# Gradium voice client

A small browser client for the Pipecat bot in `../server`, built from the
[Pipecat UI](https://ui.pipecat.ai/) shadcn registry: a transcript window above a
control bar with the microphone toggle, a text input and the Connect / Disconnect
button. If the voice was designed from a reference image, the image sits above the
transcript in place of the audio visualizer and glows while the bot speaks.

## Run

Node 20.19 or newer (or 22.12+; that is what Vite 8 requires).

```bash
npm install     # first run only
npm run dev     # prints the URL, usually http://localhost:5173
```

Start the bot first (`cd ../server && uv run bot.py`). The dev server proxies
`/api/*` to it on `http://localhost:7860`; if the bot listens elsewhere:

```bash
PIPECAT_SERVER_URL=http://localhost:7861 npm run dev
```

`npm run build` writes a static bundle to `dist/`; serve it behind the same `/api`
proxy, or from the bot's origin.

## voice.json

`public/voice.json` tells the page who the bot is. The design-voice skill writes it
(and copies the image into `public/`) after a voice is kept:

```json
{
  "name": "Gruff Irishman",
  "image": "/gruff-irishman.png",
  "brief": "A gruff Irish male voice, 45 to 60, ...",
  "persona": "You are Declan, a gruff but good-hearted Irish innkeeper ..."
}
```

Every field is optional; with no `image` the visualizer is shown instead. The file
is fetched on page load, so editing it needs a reload, not a restart.

## How it was made, and adding more

This is `npx shadcn@latest init -t vite -b base -p nova` (Vite, Tailwind 4, the
`base-nova` style on Base UI primitives) with the `@pipecat` registry added to
`components.json` and these items installed as source under `src/components/pipecat`,
`src/hooks` and `src/lib`:

```bash
npx shadcn@latest add @pipecat/connect-button @pipecat/user-audio-control \
  @pipecat/text-input @pipecat/conversation @pipecat/audio-visualizer-bar \
  @pipecat/bot-audio @pipecat/use-pipecat-app
```

The registry is already configured, so more components are one command away, for
example `npx shadcn@latest add @pipecat/client-status`. The list is at
<https://ui.pipecat.ai/docs>. The app's own code is `src/App.tsx`, `src/voice.ts`
and the layout at the end of `src/index.css`; the registry source
(`src/components/pipecat/`, `src/components/ui/`, `src/hooks/use-pipecat-app.ts`,
`src/lib/transports.ts`, `src/lib/visualizer.ts`) is left as upstream wrote it and
is skipped by `npm run lint` and `npm run format`.
