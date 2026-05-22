/* jshint esversion: 11, browser: true */

import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  const botStartUrl = env.VITE_BOT_START_URL || 'http://localhost:7860/start';
  const botStartPublicApiKey = env.VITE_BOT_START_PUBLIC_API_KEY || '';

  if (!env.VITE_BOT_START_URL) {
    console.warn(
      '[vite] VITE_BOT_START_URL not set, using default: http://localhost:7860/start'
    );
  }

  const target = new URL(botStartUrl);

  return {
    server: {
      allowedHosts: true, // Allows external connections like ngrok
      proxy: {
        '/start': {
          target: target.origin,
          changeOrigin: true,
          rewrite: () => target.pathname,
          ...(botStartPublicApiKey && {
            headers: { Authorization: `Bearer ${botStartPublicApiKey}` },
          }),
        },
      },
    },
  };
});
