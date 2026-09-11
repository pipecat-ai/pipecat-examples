# The web client

The skill bundles a browser client in `assets/client/` and copies it into the
project's `client/` with the `client` subcommand. It is a Vite + React +
TypeScript app whose voice components come from the
[Pipecat UI](https://ui.pipecat.ai/) shadcn registry, installed as source, so
the user owns and can edit every component. It talks to the bot in `server/`
over WebRTC through the Pipecat client SDK.

## What the user sees

Top to bottom, filling the window:

1. **Header**: the voice's name (fallback "Gradium voice") and, under it, the
   brief the voice was designed from.
2. **Stage**: the reference image when the voice was designed from one, shown
   in place of the bot's audio visualizer, with a glow while the bot speaks.
   Without an image, the bot's audio visualizer (`AudioVisualizerBar`).
3. **Transcript**: the live conversation (`Conversation`), user turns from the
   speech-to-text and bot turns as they are spoken, scrolling.
4. **Control bar**: the microphone toggle with a device picker
   (`UserAudioControl`), a text input that sends typed messages to the bot
   (`TextInput`), and the Connect / Disconnect button (`ConnectButton`).
   A connection error, if any, appears above the bar.

Light or dark follows the system theme.

## Scaffold and run

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" client --session voices/<slug>
```

`client` copies the template into `client/` without overwriting anything
(when `client/package.json` already exists it copies nothing and says so),
copies the session's reference image to `client/public/<slug>.<ext>`, and
writes `client/public/voice.json`:

```json
{
  "name": "Gruff Irishman",
  "image": "/gruff-irishman.png",
  "brief": "A gruff Irish male voice, 45 to 60, ...",
  "persona": "You are Declan, a gruff but good-hearted Irish innkeeper ..."
}
```

Every field may be null; with no `image` the visualizer shows. The page
fetches the file on load, so a new voice needs a reload, not a restart. When
a later run switches to a voice without an image, the previous image file is
removed from `public/` (the session directory keeps the original). Without
`--session`, pass `--name`, `--image`, `--brief`, `--persona` by hand; with a
session, `--image <file>` overrides the session's image.

Then:

```bash
cd client
npm install     # first run only, about a minute; Node 20.11 or newer
npm run dev     # prints the URL, normally http://localhost:5173
```

Start the bot first. Vite proxies `/api/*` to `http://localhost:7860`, so the
page and the WebRTC offer share an origin; if the bot listens elsewhere:

```bash
PIPECAT_SERVER_URL=http://localhost:7861 npm run dev
```

`npm run build` writes a static bundle to `dist/` (gitignored).

## Files

| Path | What it is |
|---|---|
| `src/App.tsx` | The app: `usePipecatApp` builds the client with `SmallWebRTCTransport` and `connectParams: { webrtcRequestParams: { endpoint: "/api/offer" } }`, `PipecatClientProvider` wraps the page, `BotAudioOutput` plays the bot (required; without it the bot is silent), then the layout above. |
| `src/voice.ts` | Loads and validates `public/voice.json`. |
| `src/index.css` | Tailwind 4, the shadcn theme (with the registry's `active`/`inactive` and `agent`/`client` tokens), and the app layout at the end. |
| `src/components/pipecat/*.tsx` | Registry source: `connect-button`, `user-audio-control`, `device-select`, `text-input`, `conversation`, `conversation-message`, `audio-visualizer-bar`, `bot-audio`. |
| `src/hooks/use-pipecat-app.ts`, `src/lib/transports.ts`, `src/lib/visualizer.ts` | Registry hook and helpers. |
| `src/components/ui/*.tsx` | shadcn primitives the registry items depend on (button, dropdown-menu, input-group, slider…). |
| `components.json` | shadcn config, `"style": "base-nova"`, with the `@pipecat` registry: `"registries": { "@pipecat": "https://ui.pipecat.ai/r/{name}.json" }`. |
| `vite.config.ts` | React and Tailwind plugins, the `@/` alias, the `/api` proxy. |
| `public/voice.json` | Written by `client`; see above. |

The template was produced with `npx shadcn@latest init -t vite -b base -p nova`
followed by:

```bash
npx shadcn@latest add @pipecat/connect-button @pipecat/user-audio-control \
  @pipecat/text-input @pipecat/conversation @pipecat/audio-visualizer-bar \
  @pipecat/bot-audio @pipecat/use-pipecat-app
```

so more components are one command away, for example
`cd client && npx shadcn@latest add @pipecat/client-status`. The list is at
<https://ui.pipecat.ai/docs/components>. `npm run lint` covers the app's own
files; the registry directories are excluded.

## How text input reaches the bot

`TextInput` calls the client's `sendText`, an RTVI `send-text` message. The
template bot's `PipelineWorker` adds an `RTVIProcessor`, which interrupts any
bot speech, appends the text to the LLM context as a user turn and runs the
LLM, so the reply is spoken and appears in the transcript like a spoken turn.
No server change is needed; a bot that is not built from the template needs
an `RTVIProcessor` in its pipeline for typing to work.

## When something goes wrong

| Symptom | Fix |
|---|---|
| `npm: command not found`, or `npm install` complains about the Node version | Install Node 20.11 or newer from <https://nodejs.org>. |
| The page loads but Connect sits at "Connecting…", then an error above the bar | The bot is not running, or is on another port. Start `uv run bot.py`, or set `PIPECAT_SERVER_URL`. The Vite log shows the proxy error. |
| Port 5173 in use | Vite picks the next free port and prints it; open that one. |
| No microphone prompt | The page asks for the microphone on load. Reload; in the browser's site settings, allow the microphone for `localhost`. |
| Bot audio never plays | `BotAudioOutput` is mounted in `App.tsx`; do not remove it. Check the browser's autoplay setting and the bot log for a Gradium `401`. |
| The image does not show | `client/public/voice.json` has `"image": null`. Run `client --session voices/<slug>` again (the session needs `--image` at generate time) or `client --image <file>`. |
| Old image still shows after switching voices | Hard-reload; `voice.json` is fetched with `cache: "no-store"` but the image itself may be cached. |
