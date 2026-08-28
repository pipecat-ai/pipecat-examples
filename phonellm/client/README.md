# PhoneLLM Client

Voice console for the PhoneLLM bot: a Vite + React + Tailwind 4 app built
from [Pipecat Voice UI Kit](https://voiceuikit.pipecat.ai) components
(installed as shadcn source under `src/components/pipecat/`), using shadcn
with Base UI primitives. Dark-only, squared-off design.

## Run

Start the bot (from `../server`):

```bash
uv run bot.py -t webrtc
```

Then start the client:

```bash
npm install
npm run dev
```

Open http://localhost:5173 and hit Connect. The dev server proxies
`/api/offer` to the bot on port 7860 (see `vite.config.ts`).

## Transports

The app reaches a bot two different ways, and picks one per build:

| | dev | production |
|---|---|---|
| transport | `smallwebrtc` | `daily` |
| bot | one you run locally | a Pipecat Cloud agent |
| connect | straight to `/api/offer` | POST `/api/connect`, join the room it returns |

Local dev talks to your own bot, which serves its own offer endpoint — no
start step, nothing secret. Pipecat Cloud agents are reached over Daily, and
starting a session takes the organization's public API key. That key can't
ship in a bundle, so the browser posts to `api/connect.ts` (a serverless
function) and gets back only the Daily room and token it may join.

`VITE_TRANSPORT` forces one either way; see `.env.example` for the full set
of variables.

## Build

```bash
npm run build    # typecheck + production build to dist/
npm run preview
```

A production build defaults to the Daily path, so it needs the start
endpoint deployed alongside it. On Vercel, `api/connect.ts` is picked up
automatically — set the two server-side variables in the project:

```
BOT_START_URL=https://api.pipecat.daily.co/v1/public/phonellm-example/start
BOT_START_PUBLIC_KEY=pk_...
```

They have no `VITE_` prefix, so they stay on the server and out of the
bundle. To exercise that path locally, `vercel dev` serves the function and
the app together:

```bash
VITE_TRANSPORT=daily vercel dev
```

To build a client that talks to a self-hosted bot over SmallWebRTC instead,
pin the transport and point it at the bot:

```bash
VITE_TRANSPORT=smallwebrtc VITE_OFFER_URL=https://bot.example.com/api/offer npm run build
```
