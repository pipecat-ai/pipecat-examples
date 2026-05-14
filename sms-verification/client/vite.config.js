import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:7860',
      '/events': {
        target: 'http://localhost:7860',
        ws: false,
        changeOrigin: true,
      },
    },
  },
});
