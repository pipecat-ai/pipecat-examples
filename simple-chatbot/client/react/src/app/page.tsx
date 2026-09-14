"use client";

import { useState } from "react";

import type { Transport } from "@pipecat-ai/client-js";
import {
  PipecatClientAudio,
  PipecatClientProvider,
} from "@pipecat-ai/client-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";
import { usePipecatApp } from "@/hooks/use-pipecat-app";

import { App } from "./components/App";
import {
  AVAILABLE_TRANSPORTS,
  DEFAULT_TRANSPORT,
  TRANSPORT_CONFIG,
} from "../config";
import type { TransportType } from "../config";

/** Imports only the transport package the selected transport needs. */
async function createTransport(type: TransportType): Promise<Transport> {
  switch (type) {
    case "daily": {
      const { DailyTransport } = await import("@pipecat-ai/daily-transport");
      return new DailyTransport();
    }
    case "smallwebrtc": {
      const { SmallWebRTCTransport } = await import(
        "@pipecat-ai/small-webrtc-transport"
      );
      return new SmallWebRTCTransport();
    }
  }
}

export default function Home() {
  const [transportType, setTransportType] =
    useState<TransportType>(DEFAULT_TRANSPORT);

  // Changing transportType rebuilds the client with a fresh transport.
  const { client, connect, disconnect, error, clearError } = usePipecatApp({
    transportType,
    transportFactory: () => createTransport(transportType),
    startBotParams: TRANSPORT_CONFIG[transportType],
    initDevicesOnMount: true,
  });

  if (!client) {
    return (
      <main className="flex h-dvh items-center justify-center p-4">
        {error ? (
          <Alert variant="destructive" className="max-w-md">
            <AlertTitle>Failed to set up the client</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : (
          <Spinner className="size-8" />
        )}
      </main>
    );
  }

  return (
    <PipecatClientProvider client={client}>
      <main className="h-dvh overflow-hidden">
        <App
          onConnect={connect}
          onDisconnect={disconnect}
          error={error}
          onDismissError={clearError}
          transportType={transportType}
          onTransportChange={setTransportType}
          availableTransports={AVAILABLE_TRANSPORTS}
        />
      </main>
      <PipecatClientAudio />
    </PipecatClientProvider>
  );
}
