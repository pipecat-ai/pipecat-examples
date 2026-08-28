/**
 * Transport configuration.
 *
 * The bot runner supports several transports at once, and the client picks one
 * per session with the `transport` field in the `/start` request body. Run the
 * server without `-t` so both of these stay available.
 */

import type { APIRequest } from '@pipecat-ai/client-js';

export type TransportType = 'smallwebrtc' | 'daily';

export const AVAILABLE_TRANSPORTS: TransportType[] = ['smallwebrtc', 'daily'];

export const DEFAULT_TRANSPORT: TransportType = 'smallwebrtc';

export const TRANSPORT_LABELS: Record<TransportType, string> = {
  smallwebrtc: 'SmallWebRTC',
  daily: 'Daily',
};

// Both go through the Next.js route handlers in `src/app/api`, which forward to
// the bot server and keep any Pipecat Cloud key out of the browser bundle.
export const TRANSPORT_CONFIG: Record<TransportType, APIRequest> = {
  smallwebrtc: {
    endpoint: '/api/start',
    requestData: {
      createDailyRoom: false,
      enableDefaultIceServers: true,
      transport: 'webrtc',
    },
  },
  daily: {
    endpoint: '/api/start',
    requestData: {
      createDailyRoom: true,
      dailyRoomProperties: { start_video_off: true },
      transport: 'daily',
    },
  },
};
