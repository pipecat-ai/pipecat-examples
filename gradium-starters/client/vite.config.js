import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  base: "./",
  plugins: [react()],
  publicDir: "public",
  server: {
    allowedHosts: true,
    proxy: {
      "/start": {
        target: "http://0.0.0.0:7860",
        changeOrigin: true,
      },
      "/api": {
        target: "http://0.0.0.0:7860",
        changeOrigin: true,
      },
      "/sessions": {
        target: "http://0.0.0.0:7860",
        changeOrigin: true,
      },
    },
  },
});
