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
    },
  },
  server: {
    proxy: {
      // Pipecat dev runner (uv run bot.py -t webrtc) serves the WebRTC
      // offer endpoint on port 7860. Scoped to that one path so it doesn't
      // swallow /api/connect, which `vercel dev` serves from api/.
      "/api/offer": "http://localhost:7860",
    },
  },
})
