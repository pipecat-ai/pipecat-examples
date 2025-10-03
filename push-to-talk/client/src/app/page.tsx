'use client';

import {
  FullScreenContainer,
  ThemeProvider,
  PipecatAppBase,
  SpinLoader,
  type PipecatBaseChildProps,
} from '@pipecat-ai/voice-ui-kit';
import { App } from './components/App';

export default function Home() {
  return (
    <ThemeProvider>
      <FullScreenContainer>
        <PipecatAppBase
          transportType="daily"
          connectParams={{
            endpoint: '/api/connect',
          }}>
          {({
            client,
            handleConnect,
            handleDisconnect,
            error,
          }: PipecatBaseChildProps) =>
            !client ? (
              <SpinLoader />
            ) : (
              <App
                handleConnect={handleConnect}
                handleDisconnect={handleDisconnect}
                error={error}
              />
            )
          }
        </PipecatAppBase>
      </FullScreenContainer>
    </ThemeProvider>
  );
}
