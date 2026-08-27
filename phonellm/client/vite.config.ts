import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
      // Optional transports src/lib/transports.ts can load but this app
      // doesn't install — stubbed so Vite can resolve them. To use one,
      // install its package and remove its alias.
      "@pipecat-ai/daily-transport": path.resolve(
        import.meta.dirname,
        "./src/lib/optional-transport-stub.ts"
      ),
      "@pipecat-ai/websocket-transport": path.resolve(
        import.meta.dirname,
        "./src/lib/optional-transport-stub.ts"
      ),
      "@pipecat-ai/moq-transport": path.resolve(
        import.meta.dirname,
        "./src/lib/optional-transport-stub.ts"
      ),
    },
  },
  server: {
    proxy: {
      // Pipecat dev runner (uv run bot.py -t webrtc) serves the WebRTC
      // offer endpoint on port 7860.
      "/api": "http://localhost:7860",
    },
  },
})
