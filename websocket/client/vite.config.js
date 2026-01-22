/* jshint esversion: 6 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';

export default defineConfig({
    plugins: [react()],
    server: {
        allowedHosts: true, // Allows external connections like ngrok
    },
});
