import { defineConfig } from 'vite';

export default defineConfig({
    server: {
        proxy: {
            // Proxy /start (Pipecat runner) to the backend server.
            '/start': {
                target: 'http://0.0.0.0:7860', // Replace with your backend URL
                changeOrigin: true,
            },
        },
    },
});
