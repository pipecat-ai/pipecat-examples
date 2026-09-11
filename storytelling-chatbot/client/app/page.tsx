"use client";

import React, { useEffect, useState } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import {
  PipecatClientAudio,
  PipecatClientProvider,
} from "@pipecat-ai/client-react";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { IconLoader2 } from "@tabler/icons-react";

import App from "../components/App";

export default function Home() {
  // The transport needs browser WebRTC APIs, so the client is created after
  // mount rather than during server rendering. One client per page load: the
  // mic is acquired up front so the device picker can list it, and App turns
  // it off again until the bot asks for input.
  const [client, setClient] = useState<PipecatClient | null>(null);

  useEffect(() => {
    const pcClient = new PipecatClient({
      transport: new SmallWebRTCTransport(),
      enableMic: true,
      enableCam: false,
    });
    setClient(pcClient);

    return () => {
      void pcClient.disconnect();
    };
  }, []);

  if (!client) {
    return (
      <div className="flex items-center mx-auto">
        <IconLoader2 size={42} stroke={2} className="animate-spin text-white" />
      </div>
    );
  }

  return (
    <PipecatClientProvider client={client}>
      <App />
      <PipecatClientAudio />
    </PipecatClientProvider>
  );
}
