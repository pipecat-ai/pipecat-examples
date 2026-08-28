import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The host's .env, one directory up. Reading it here is what lets the client
// default to the same relay the host dials, instead of repeating it in the URL.
const HOST_ENV_DIR = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig(({ mode }) => {
  // Only MOQ_* is loaded, and only these three are handed to the browser.
  // Inlining happens at build time, so anything named here ends up in the
  // bundle — keep it to values that are safe to publish. The API keys in the
  // same file are never touched.
  //
  // There is no namespace to pass: the host's prefixes are already full
  // paths, so a room name lives inside them (`demo/pipecat/request`).
  const env = loadEnv(mode, HOST_ENV_DIR, "MOQ_");

  return {
    plugins: [react()],
    define: {
      __MOQ_ENV_DEFAULTS__: JSON.stringify({
        relayUrl: env.MOQ_RELAY_URL ?? null,
        botId: env.MOQ_RESPONSE_PREFIX ?? null,
        clientId: env.MOQ_REQUEST_PREFIX ?? null,
      }),
    },
    server: {
      // WebTransport needs a secure context. localhost counts as one, so plain
      // HTTP is fine here; a non-localhost host would need HTTPS.
      port: 5173,
    },
  };
});
