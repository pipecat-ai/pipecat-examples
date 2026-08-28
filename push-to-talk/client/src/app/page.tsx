'use client';

import {
  ErrorCard,
  FullScreenContainer,
  ThemeProvider,
  PipecatAppBase,
  SpinLoader,
  type PipecatBaseChildProps,
} from '@pipecat-ai/voice-ui-kit';
import { useState } from 'react';
import { App } from './components/App';
import {
  AVAILABLE_TRANSPORTS,
  DEFAULT_TRANSPORT,
  TRANSPORT_CONFIG,
  type TransportType,
} from '../config';

export default function Home() {
  const [transportType, setTransportType] =
    useState<TransportType>(DEFAULT_TRANSPORT);

  return (
    <ThemeProvider>
      <FullScreenContainer>
        <PipecatAppBase
          transportType={transportType}
          connectParams={TRANSPORT_CONFIG[transportType]}>
          {({
            client,
            handleConnect,
            handleDisconnect,
            error,
          }: PipecatBaseChildProps) =>
            error ? (
              <ErrorCard error={error} title="An error occurred connecting to agent." />
            ) : !client ? (
              <SpinLoader />
            ) : (
              <App
                handleConnect={handleConnect}
                handleDisconnect={handleDisconnect}
                error={error}
                transportType={transportType}
                onTransportChange={setTransportType}
                availableTransports={AVAILABLE_TRANSPORTS}
              />
            )
          }
        </PipecatAppBase>
      </FullScreenContainer>
    </ThemeProvider>
  );
}
