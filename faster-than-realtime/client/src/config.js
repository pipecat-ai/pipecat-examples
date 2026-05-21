/* jshint esversion: 11, browser: true */

const botStartUrl =
  import.meta.env.VITE_BOT_START_URL || 'http://localhost:7860/start';
const botStartPublicApiKey = import.meta.env.VITE_BOT_START_PUBLIC_API_KEY;

if (!import.meta.env.VITE_BOT_START_URL) {
  console.warn(
    'VITE_BOT_START_URL not configured, using default: http://localhost:7860/start'
  );
}

const connectParams = {
  endpoint: botStartUrl,
  requestData: {
    createDailyRoom: false,
    dailyRoomProperties: { start_video_off: true },
    transport: 'daily',
  },
};

if (botStartPublicApiKey) {
  connectParams.headers = new Headers({
    Authorization: `Bearer ${botStartPublicApiKey}`,
  });
}

export { connectParams };
