import babel from "@rolldown/plugin-babel";
import tailwindcss from "@tailwindcss/vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";

const START_PATH = "/api/start";

/**
 * Serves /api/start from the dev server with the same function production
 * runs (api/start.ts), so a local page can start the bot deployed on Pipecat
 * Cloud. The key is read by the dev server and never reaches the page.
 */
function pipecatCloudStart(agentName: string, publicKey: string): Plugin {
  return {
    name: "pipecat-cloud-start",
    configureServer(server) {
      process.env.PIPECAT_CLOUD_AGENT_NAME = agentName;
      process.env.PIPECAT_CLOUD_PUBLIC_KEY = publicKey;
      server.middlewares.use(START_PATH, (request, response, next) => {
        if (request.method !== "POST") {
          next();
          return;
        }
        server
          .ssrLoadModule("/api/start.ts")
          .then((module) => (module as typeof import("./api/start.ts")).POST())
          .then(async (started) => {
            response.statusCode = started.status;
            response.setHeader("Content-Type", "application/json");
            response.end(await started.text());
          })
          .catch(next);
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, import.meta.dirname, "");
  // With a Pipecat Cloud key the dev server starts sessions there, over Daily.
  // Without one, /api is the local bot's own runner (bot.py).
  const cloudStart =
    env.PIPECAT_CLOUD_AGENT_NAME && env.PIPECAT_CLOUD_PUBLIC_KEY
      ? [
          pipecatCloudStart(
            env.PIPECAT_CLOUD_AGENT_NAME,
            env.PIPECAT_CLOUD_PUBLIC_KEY,
          ),
        ]
      : [];
  return {
    plugins: [
      ...cloudStart,
      react(),
      babel({ presets: [reactCompilerPreset()] }),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        "@": new URL("./src", import.meta.url).pathname,
      },
    },
    build: {
      rolldownOptions: {
        output: {
          // React and the Pipecat SDK change far less often than the app, so
          // each is a chunk of its own that browsers can keep cached.
          codeSplitting: {
            groups: [
              {
                name: "react",
                test: /node_modules\/(react|react-dom|scheduler)\//,
              },
              { name: "pipecat", test: /node_modules\/@pipecat-ai\/client-/ },
            ],
          },
        },
      },
    },
    server: {
      // The local bot's runner (bot.py), for everything the plugin above
      // doesn't answer. In production /api is the function in api/.
      proxy: {
        "/api": {
          target: env.BOT_URL ?? "http://localhost:7860",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
