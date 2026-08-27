# MoQ Direct-Mode Client

A browser client for the direct-mode host in the parent directory. Built with
[Vite](https://vite.dev/) and the
[Pipecat voice UI kit](https://github.com/pipecat-ai/voice-ui-kit).

Unlike the other client examples in this repo, there is **no `/start` endpoint
and no server side**. The host is already sitting on the relay before you open
this page, so the client dials the relay directly and the two meet on a pair of
broadcast paths. That's also why this is a plain Vite SPA rather than Next.js:
there is no API route to host.

## Setup

1. Start a MoQ relay and the host; see the [parent README](../README.md).

2. Install and run:

```bash
npm install
npm run dev
```

3. Open <http://localhost:5173/> and press Connect.

Open the same URL in a second tab to get a second, independent call — each tab
mints its own session id, so the host starts a separate bot for each.

## Configuration

There is no `/start` response to carry the relay, so it reaches the browser one
of two ways. Query parameters win; the host's `.env` fills in the rest.

**1. The host's `.env`.** `vite.config.ts` loads `MOQ_*` from the directory
above and inlines three of them, so running both sides from one checkout needs
no URL parameters at all — the client already points at whatever relay the host
dials. This happens at **build time**, so a change to `.env` needs a dev-server
restart (or a rebuild) to take effect. Only `MOQ_RELAY_URL`,
`MOQ_RESPONSE_PREFIX` and `MOQ_REQUEST_PREFIX` are passed through; the API keys
in the same file are never read.

**2. Query parameters.** What makes a link shareable, and the only option once
this client is built and served somewhere other than the host's checkout.

| Parameter | Falls back to | Meaning |
| --- | --- | --- |
| `relay` | `MOQ_RELAY_URL` | The relay to dial, e.g. `http://localhost:4443`. **Required** — with neither source set, the page reports that it isn't configured rather than guessing. |
| `ns` | *(empty)* | Namespace prepended to both prefixes when they come from the URL or the defaults. Ignored when the host's `.env` supplies prefixes, since those are already full paths (`demo/pipecat/request`) and would otherwise carry the room twice. |
| `botId` | `MOQ_RESPONSE_PREFIX`, then `response` | The prefix the host publishes replies under — its `--response-prefix`. |
| `clientId` | `MOQ_REQUEST_PREFIX`, then `request` | The prefix this client publishes its mic under — the host's `--request-prefix`. |

The client appends its own session id to both, so a call runs on
`<ns>/<clientId>/<session>` and `<ns>/<botId>/<session>`. A host started with
`--request-prefix demo/pipecat/request --response-prefix demo/pipecat/response`
is reached with `?relay=…&ns=demo/pipecat` — or, when those same prefixes are
in the host's `.env`, with no parameters at all.

## Notes

- **The session id is minted here, not handed out.** The host watches the
  request prefix and starts a bot for each id it sees, so two callers sharing
  one URL never collide.
- **WebTransport needs a secure context.** `localhost` counts as one, so plain
  HTTP works for local dev; serving this from another host needs HTTPS.
- **Self-signed relays**: `MoqTransportOptions.serverCertificateHashes` pins a
  cert, but this page doesn't read one from the URL — a dev relay on localhost
  or a CA-signed relay needs no pinning.
