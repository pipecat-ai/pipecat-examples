import type {
  APIRequest,
  TransportConnectionParams,
} from "@pipecat-ai/client-js"

import type { TransportType } from "@/lib/transports"

/**
 * The offer endpoint of a locally running bot. The Vite dev server proxies
 * it to `uv run bot.py -t webrtc` on port 7860 (see vite.config.ts).
 */
const OFFER_URL = import.meta.env.VITE_OFFER_URL ?? "/api/offer"

/**
 * The start endpoint that launches a Pipecat Cloud session. Served by
 * `api/connect.ts`, which holds the PCC API key.
 */
const CONNECT_URL = import.meta.env.VITE_CONNECT_URL ?? "/api/connect"

/** The transports this app knows how to reach a bot with. */
const SUPPORTED = ["smallwebrtc", "daily"] as const

type SupportedTransport = (typeof SUPPORTED)[number]

export interface SessionConfig {
  transportType: TransportType
  /**
   * Either connection params the transport connects with directly, or an
   * `APIRequest` (an object with an `endpoint`), which makes the client
   * start a bot at that endpoint and connect with what it returns.
   */
  connectParams: TransportConnectionParams | APIRequest
}

/**
 * Picks the transport for this build: `smallwebrtc` in dev, `daily` in a
 * production build, unless VITE_TRANSPORT names one explicitly.
 */
function resolveTransport(): SupportedTransport {
  const requested = import.meta.env.VITE_TRANSPORT?.trim().toLowerCase()
  if (requested) {
    const match = SUPPORTED.find((name) => name === requested)
    if (match) return match
    console.warn(
      `Ignoring VITE_TRANSPORT="${requested}" — expected one of ` +
        `${SUPPORTED.join(", ")}. Falling back to the default for this build.`
    )
  }
  return import.meta.env.PROD ? "daily" : "smallwebrtc"
}

/**
 * How this build reaches a bot, and how it starts one.
 *
 * The two environments differ in more than the transport, so they take
 * different connect paths:
 *
 * - **Local (`smallwebrtc`)** — the bot runs on your machine and serves its
 *   own offer endpoint, so the browser negotiates straight with it. There is
 *   no start endpoint and no key to protect.
 * - **Production (`daily`)** — the bot is a Pipecat Cloud agent, which hands
 *   out Daily rooms and needs a `pk_...` key to start a session. The key can
 *   never reach the browser, so the client posts to CONNECT_URL instead; that
 *   function starts the agent and returns the room URL and token to join.
 */
export function sessionConfig(): SessionConfig {
  const transportType = resolveTransport()

  if (transportType === "daily") {
    // An `endpoint` here routes through startBotAndConnect(): the client
    // POSTs to it and passes the response to connect(), so the function must
    // answer with Daily call options ({ url, token }).
    return { transportType, connectParams: { endpoint: CONNECT_URL } }
  }

  return { transportType, connectParams: { webrtcUrl: OFFER_URL } }
}
