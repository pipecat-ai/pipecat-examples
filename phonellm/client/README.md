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

Open http://localhost:5173 and hit Connect. The dev server proxies `/api`
to the bot's WebRTC offer endpoint on port 7860 (see `vite.config.ts`).

## Build

```bash
npm run build    # typecheck + production build to dist/
npm run preview
```

In production, either serve the app behind a proxy that maps `/api` to the
bot, or set the offer endpoint directly at build time:

```bash
VITE_OFFER_URL=https://bot.example.com/api/offer npm run build
```

## Voice UI Kit components

Components come from the `@pipecat` registry configured in
`components.json`. To add or update one:

```bash
npx shadcn@latest add @pipecat/<name>            # install
npx shadcn@latest add @pipecat/<name> --overwrite # update in place
npx shadcn@latest list @pipecat                   # see what's available
```

Registry-installed files (`src/components/ui/`, `src/components/pipecat/`,
`src/hooks/use-pipecat-*.ts`) are kept as shipped; a scoped override in
`eslint.config.js` relaxes a few strict lint rules for those paths only.

## Notes

- Only the SmallWebRTC transport is installed. The kit's transport loader
  references the other transports optionally; `vite.config.ts` aliases
  them to `src/lib/optional-transport-stub.ts`. To use another transport,
  install its package and remove its alias.
- Dark mode is fixed: `class="dark"` on `<html>` plus a single dark token
  set in `src/index.css`. There is no theme switching.
