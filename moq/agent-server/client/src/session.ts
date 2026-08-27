import type { MoqTransportOptions } from "@pipecat-ai/moq-transport";

/**
 * Defaults read from the host's `.env` at build time (see `vite.config.ts`).
 * Each is null when the corresponding `MOQ_*` variable isn't set.
 */
declare const __MOQ_ENV_DEFAULTS__: {
  relayUrl: string | null;
  botId: string | null;
  clientId: string | null;
};

/** Prefix the bot publishes its replies under, matching the host's default. */
const DEFAULT_BOT_ID = "response";

/** Prefix this client publishes its mic under, matching the host's default. */
const DEFAULT_CLIENT_ID = "request";

/**
 * A random UUID v4. `crypto.randomUUID` exists only in secure contexts, and
 * this runs at module load, so on a non-localhost http:// origin it would
 * throw before React mounts and the page would be blank instead of showing
 * the transport's own error. `getRandomValues` works everywhere.
 */
function mintSessionId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * Read a MoQ direct-mode session from the page URL, falling back to the
 * host's `.env`.
 *
 * The host is already on the relay before anyone opens this page, so there is
 * no `/start` to ask where to meet it. Everything the browser can't derive on
 * its own has to reach it another way:
 *
 *   1. Query parameters — `?relay=…&ns=…&botId=…&clientId=…`. This is what
 *      makes a link shareable, and the only option once the client is built
 *      and served somewhere.
 *   2. The host's `MOQ_*` variables, inlined at build time. Running both
 *      sides from one checkout, this means `npm run dev` already points at
 *      whatever relay `.env` names.
 *
 * Returns null when neither supplies a relay, which is what the page treats
 * as "not configured" rather than guessing.
 */
export function readMoqSession(): MoqTransportOptions | null {
  const params = new URLSearchParams(window.location.search);
  const env = __MOQ_ENV_DEFAULTS__;

  const relayUrl = params.get("relay") ?? env.relayUrl;
  if (!relayUrl) return null;

  // The bot publishes its own broadcast as the response and reads the peer's
  // as the request, so we take the opposite pair. Worth naming explicitly:
  // the transport still defaults to the older bot0/client0.
  const botId = params.get("botId") ?? env.botId ?? DEFAULT_BOT_ID;
  const clientId = params.get("clientId") ?? env.clientId ?? DEFAULT_CLIENT_ID;

  // `ns` is a room for prefixes that came from the URL or the defaults. The
  // host's env prefixes are already full paths (`demo/pipecat/request`), so
  // prepending a namespace to them would double the room; they win over `ns`.
  // Empty rather than the transport's built-in default, so an unscoped URL
  // puts the call at the relay root instead of silently joining the shared
  // `pipecat` namespace. `Path.from` drops empty components, so the paths
  // below come out as `request/<session>` with no leading slash.
  const envPrefixed = env.botId != null || env.clientId != null;
  const ns = params.get("ns");
  if (ns && envPrefixed) {
    console.warn(
      `Ignoring ?ns=${ns}: the host's .env supplies prefixes that already carry their room.`,
    );
  }
  const namespace = envPrefixed ? "" : (ns ?? "");

  // Everyone opening this URL shares a namespace, so the session id is what
  // keeps one caller's broadcasts off another's. The host watches the request
  // prefix and starts a bot per id it sees, which is why we mint it here
  // rather than being told one.
  const session = mintSessionId();

  return {
    relayUrl,
    namespace,
    botId: `${botId}/${session}`,
    clientId: `${clientId}/${session}`,
  };
}
