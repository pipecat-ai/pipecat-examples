import { LogLevel, PipecatClient, type Transport } from "@pipecat-ai/client-js";

/** Where a session is started: the bot's runner in development, the function in api/ in production. */
const START_ENDPOINT = "/api/start";

/**
 * Daily is what the hosted demo runs on. SmallWebRTC is for local development
 * against `bot.py`, which needs no Daily account.
 */
const USE_SMALL_WEBRTC = import.meta.env.VITE_TRANSPORT === "smallwebrtc";

const START_REQUEST: Record<string, string | boolean> = USE_SMALL_WEBRTC
  ? { transport: "webrtc" }
  : { transport: "daily", createDailyRoom: true };

/** Loads only the transport in use, so the page doesn't ship the other one. */
async function createTransport(): Promise<Transport> {
  if (USE_SMALL_WEBRTC) {
    const { SmallWebRTCTransport } =
      await import("@pipecat-ai/small-webrtc-transport");
    return new SmallWebRTCTransport();
  }
  const { DailyTransport } = await import("@pipecat-ai/daily-transport");
  return new DailyTransport();
}

/** The app's one client. The microphone stays off until the visitor turns it on. */
export async function createPipecatClient(): Promise<PipecatClient> {
  const client = new PipecatClient({
    transport: await createTransport(),
    enableMic: false,
    enableCam: false,
  });
  // The SDK logs every message it sends and receives unless told otherwise.
  client.setLogLevel(import.meta.env.DEV ? LogLevel.INFO : LogLevel.WARN);
  return client;
}

/** The session being started, shared by everything that asks for one meanwhile. */
let starting: Promise<void> | null = null;

/** Resolves once a bot session is up: at once if there is one, else after starting it. */
export function ensureSession(client: PipecatClient): Promise<void> {
  if (client.state === "ready") return Promise.resolve();
  starting ??= client
    .startBotAndConnect({
      endpoint: START_ENDPOINT,
      requestData: START_REQUEST,
    })
    .then(() => undefined)
    .finally(() => {
      starting = null;
    });
  return starting;
}
