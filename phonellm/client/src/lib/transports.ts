import type { Transport } from "@pipecat-ai/client-js";

/**
 * The transports this app ships. Both packages are declared dependencies —
 * the kit's loader also covers websocket and moq, but carrying them here
 * meant stubbing packages we never install just to let the bundler resolve
 * branches that never run.
 */
export type TransportType = "daily" | "smallwebrtc";

/**
 * Constructor options for the selected transport.
 *
 * Typed loosely on purpose: transport packages are optional installs, so
 * their option types can't be referenced here without breaking consumers
 * that don't have them installed. For precise typing, annotate at the call
 * site with the transport package's own options type.
 */
export type TransportOptions = Record<string, unknown>;

type TransportConstructor = new (options?: TransportOptions) => Transport;

const INSTALL_HINTS: Record<TransportType, string> = {
  daily: "npm install @pipecat-ai/daily-transport",
  smallwebrtc: "npm install @pipecat-ai/small-webrtc-transport",
};

/**
 * Dynamically imports the transport class for a transport type.
 *
 * The import stays dynamic so each transport lands in its own chunk and only
 * the one this build connects with is fetched at runtime.
 */
export async function loadTransport(
  transportType: TransportType,
): Promise<TransportConstructor> {
  if (!(transportType in INSTALL_HINTS)) {
    throw new Error(`Unsupported transport type: ${String(transportType)}`);
  }
  try {
    switch (transportType) {
      case "daily": {
        const { DailyTransport } = await import("@pipecat-ai/daily-transport");
        return DailyTransport as TransportConstructor;
      }
      case "smallwebrtc": {
        const { SmallWebRTCTransport } = await import(
          "@pipecat-ai/small-webrtc-transport"
        );
        return SmallWebRTCTransport as TransportConstructor;
      }
    }
    // Unreachable: transportType was validated against INSTALL_HINTS above.
    throw new Error(`Unsupported transport type: ${String(transportType)}`);
  } catch (loadError) {
    const message =
      loadError instanceof Error ? loadError.message : String(loadError);
    throw new Error(
      `Failed to load transport "${transportType}". Make sure the package ` +
        `is installed: ${INSTALL_HINTS[transportType]}. Original error: ${message}`,
      { cause: loadError },
    );
  }
}

/**
 * Creates a transport instance for a transport type, loading the transport
 * package on demand. See {@link loadTransport} for the install semantics.
 */
export async function createTransport(
  transportType: TransportType,
  options?: TransportOptions,
): Promise<Transport> {
  const TransportClass = await loadTransport(transportType);
  return new TransportClass(options);
}
