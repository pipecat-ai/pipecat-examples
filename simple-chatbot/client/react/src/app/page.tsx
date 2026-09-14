"use client";

import { useState } from "react";

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

export default function Home() {
  const [transportType, setTransportType] =
    useState<TransportType>(DEFAULT_TRANSPORT);

  // Changing transportType rebuilds the client with a fresh transport; the
  // loaders are registered in config.ts. Devices are initialized by App once
  // it is mounted inside the provider, so the provider observes the state.
  const { client, connect, disconnect, error, clearError } = usePipecatApp({
    transportType,
    startBotParams: TRANSPORT_CONFIG[transportType],
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
