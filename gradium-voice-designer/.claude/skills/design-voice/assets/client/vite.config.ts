import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// The bot (server/bot.py) listens on http://localhost:7860 by default. Requests to
// /api/* (the WebRTC offer) are proxied there, so the page and the bot share an origin.
// If the bot runs on another port, point the proxy at it:
//
//     PIPECAT_SERVER_URL=http://localhost:7861 npm run dev
const server = process.env.PIPECAT_SERVER_URL || "http://localhost:7860"

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
      "/api": {
        target: server,
        changeOrigin: true,
      },
    },
  },
})
