# JavaScript Implementation

Basic implementation using the [Pipecat JavaScript SDK](https://docs.pipecat.ai/client/js/introduction)
with the [Daily transport](https://docs.pipecat.ai/api-reference/client/js/transports).

## Setup

> Requires Node >=22.14.0 (`@daily-co/daily-js` declares `engines.node >= 22.14.0`). A `.nvmrc` pinned to `22.14.0` is included; run `nvm use` if you use nvm.

1. Run the bot server. See the [top-level README](../../README.md).

2. Navigate to the `client/javascript` directory:

```bash
cd client/javascript
```

3. Install dependencies:

```bash
npm install
```

4. Run the client app:

```
npm run dev
```

5. Visit http://localhost:5173 in your browser, then click **Connect**.

## How the bot-ready handshake works

The Pipecat JavaScript client signals `client-ready` automatically once the
transport reaches the `ready` state. The bot's `on_client_ready` handler then
calls `set_bot_ready()` and pushes the first `TTSSpeakFrame`, so the greeting
is never clipped. The previous `sendAppMessage("playable")` workaround is no
longer needed.

Bot audio is rendered by attaching the remote audio track to a hidden `<audio>`
element inside the `onTrackStarted` callback. See `src/app.js`.
