import {
  ConnectionEndpoint,
  PipecatClient,
  TransportConnectionParams,
  TransportState,
} from '@pipecat-ai/client-js';
import {
  PipecatClientAudio,
  PipecatClientProvider,
} from '@pipecat-ai/client-react';
import { DailyTransport } from '@pipecat-ai/daily-transport';
import {
  Button,
  Card,
  CardContent,
  ConnectButton,
  LoaderIcon,
  PipecatLogo,
  TranscriptOverlay,
  XIcon,
} from '@pipecat-ai/voice-ui-kit';
import { PlasmaVisualizer } from '@pipecat-ai/voice-ui-kit/webgl';
import { useCallback, useEffect, useRef, useState } from 'react';

export interface AppProps {
  connectParams: TransportConnectionParams | ConnectionEndpoint;
  transportType: 'daily';
}

export type AppState = 'idle' | 'connecting' | 'connected' | 'disconnected';
export type PushToTalkState = 'idle' | 'talking';

export const App = ({ connectParams, transportType }: AppProps) => {
  const [client, setClient] = useState<PipecatClient | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<AppState>('idle');
  const [pushToTalkState, setPushToTalkState] =
    useState<PushToTalkState>('idle');
  const isMounted = useRef(false);

  useEffect(() => {
    if (isMounted.current) return;

    isMounted.current = true;
    async function initClient() {
      // Only run on client side
      if (typeof window === 'undefined') return;

      const transport = new DailyTransport();

      const pcClient = new PipecatClient({
        enableCam: false,
        enableMic: true,
        transport: transport,
        callbacks: {
          onTransportStateChanged: (state: TransportState) => {
            switch (state) {
              case 'connecting':
              case 'authenticating':
              case 'connected':
                setState('connecting');
                break;
              case 'ready':
                setState('connected');
                break;
              case 'disconnected':
              case 'disconnecting':
              default:
                setState('idle');
                break;
            }
          },
          onError: () => {
            setError(
              'An error occured connecting to agent. It may be that the agent is at capacity. Please try again later.'
            );
          },
        },
      });
      await pcClient.initDevices();
      setClient(pcClient);
    }

    initClient();
  }, [connectParams, transportType]);

  const handleStartSession = async () => {
    if (
      !client ||
      !['initialized', 'disconnected', 'error'].includes(client.state)
    ) {
      return;
    }
    setError(null);

    try {
      await client.connect(connectParams);
    } catch (err) {
      console.error('Connection error:', err);
      setError(
        `Failed to start session: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  };

  const handlePushToTalk = useCallback(() => {
    if (!client || state !== 'connected') {
      return;
    }

    if (pushToTalkState === 'idle') {
      // Start talking
      setPushToTalkState('talking');
      client.sendClientMessage('push_to_talk', { state: 'start' });
    } else {
      // Stop talking
      setPushToTalkState('idle');
      client.sendClientMessage('push_to_talk', { state: 'stop' });
    }
  }, [client, state, pushToTalkState]);

  if (!client) {
    return (
      <div className="w-full h-screen flex items-center justify-center">
        <LoaderIcon className="animate-spin opacity-50" size={32} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full h-screen flex items-center justify-center">
        <Card className="shadow-long">
          <CardContent>
            <div className="bg-destructive text-background font-semibold text-center p-3 rounded-lg flex flex-col gap-2">
              An error occured connecting to agent.
              <p className="text-sm font-medium text-balanced text-background/80">
                It may be that the agent is at capacity. Please try again later.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <PipecatClientProvider client={client!}>
      <div className="w-full h-screen">
        <div className="flex flex-col h-full">
          <div className="relative bg-background overflow-hidden flex-1 shadow-long/[0.02]">
            <main className="flex flex-col gap-0 h-full relative justify-end items-center">
              <PlasmaVisualizer />
              {['idle', 'connecting'].includes(state) && (
                <div className="absolute w-full h-full flex items-center justify-center">
                  <ConnectButton size="xl" onConnect={handleStartSession} />
                </div>
              )}
              {state === 'connected' && (
                <>
                  <div className="absolute w-full h-full flex items-center justify-center">
                    <TranscriptOverlay
                      participant="remote"
                      className="vkui:max-w-md"
                    />
                  </div>
                  <div className="absolute bottom-32 left-1/2 transform -translate-x-1/2">
                    <button
                      onClick={handlePushToTalk}
                      className={`px-8 py-4 rounded-full font-semibold transition-all duration-200 select-none ${
                        pushToTalkState === 'talking'
                          ? 'bg-red-500 text-white shadow-lg scale-105'
                          : 'bg-blue-500 hover:bg-blue-600 text-white shadow-md'
                      }`}>
                      {pushToTalkState === 'talking'
                        ? 'Click to Stop'
                        : 'Click to Talk'}
                    </button>
                  </div>
                </>
              )}
              {state === 'connected' && (
                <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 z-50">
                  <Card className="animate-in fade-in slide-in-from-bottom-10 duration-500">
                    <CardContent className="flex flex-row gap-4 p-4">
                      <Button
                        onClick={() => client?.disconnect()}
                        variant="destructive"
                        size="sm">
                        Disconnect
                      </Button>
                    </CardContent>
                  </Card>
                </div>
              )}
            </main>
          </div>
          <footer className="p-5 md:p-7 text-center flex flex-row gap-4 items-center justify-center">
            <PipecatLogo className="h-[24px] w-auto text-black" />
            <div className="flex flex-row gap-2 items-center justify-center opacity-60">
              <p className="text-sm text-muted-foreground font-medium">
                Pipecat AI
              </p>
              <XIcon size={16} className="text-black/30" />
              <p className="text-sm text-muted-foreground font-medium">
                Voice UI Kit
              </p>
            </div>
          </footer>
        </div>
      </div>
      <PipecatClientAudio />
    </PipecatClientProvider>
  );
};

export default App;
