import {
  Button,
  ConnectButton,
  ControlBar,
  ErrorCard,
  PipecatLogo,
  TranscriptOverlay,
  UserAudioControl,
  usePipecatConnectionState,
} from '@pipecat-ai/voice-ui-kit';
import { PlasmaVisualizer } from '@pipecat-ai/voice-ui-kit/webgl';
import { LogOutIcon, XIcon, MicIcon } from 'lucide-react';
import { usePipecatClient } from '@pipecat-ai/client-react';
import { useCallback, useState } from 'react';

export interface AppProps {
  handleConnect?: () => void | Promise<void>;
  handleDisconnect?: () => void | Promise<void>;
  error?: string | null;
}

export type PushToTalkState = 'idle' | 'talking';

const PushToTalkButton = () => {
  const client = usePipecatClient();
  const [pushToTalkState, setPushToTalkState] =
    useState<PushToTalkState>('idle');

  const handlePushToTalk = useCallback(() => {
    if (!client || client.state !== 'ready') {
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
  }, [client, pushToTalkState]);

  const isReady = client && client.state === 'ready';

  return (
    <Button
      size="xl"
      variant={pushToTalkState === 'talking' ? 'destructive' : 'primary'}
      disabled={!isReady}
      onMouseDown={handlePushToTalk}
      onMouseUp={handlePushToTalk}
      onTouchStart={handlePushToTalk}
      onTouchEnd={handlePushToTalk}
      className={`transition-all duration-200 select-none ${
        pushToTalkState === 'talking' ? 'scale-105' : ''
      } flex items-center gap-2`}>
      <MicIcon size={20} />
      {pushToTalkState === 'talking' ? 'Release to Send' : 'Hold to Talk'}
    </Button>
  );
};

export const App = ({ handleConnect, handleDisconnect, error }: AppProps) => {
  const { isConnected } = usePipecatConnectionState();

  if (error) {
    return (
      <ErrorCard error={error} title="An error occured connecting to agent." />
    );
  }

  return (
    <div className="w-full h-screen">
      <div className="flex flex-col h-full">
        <div className="relative bg-background overflow-hidden flex-1 shadow-long/[0.02]">
          <main className="flex flex-col gap-0 h-full relative justify-end items-center">
            <PlasmaVisualizer />
            <div className="absolute w-full h-full flex items-center justify-center">
              <ConnectButton
                size="xl"
                onConnect={handleConnect}
                onDisconnect={handleDisconnect}
              />
            </div>
            <div className="absolute w-full h-full flex items-center justify-center pointer-events-none">
              <TranscriptOverlay participant="remote" className="max-w-md" />
            </div>
            {isConnected && (
              <>
                <div className="absolute bottom-32 left-1/2 transform -translate-x-1/2 z-20">
                  <PushToTalkButton />
                </div>
                <ControlBar>
                  <UserAudioControl />
                  <Button
                    size="xl"
                    isIcon={true}
                    variant="outline"
                    onClick={handleDisconnect}>
                    <LogOutIcon />
                  </Button>
                </ControlBar>
              </>
            )}
          </main>
        </div>
        <footer className="p-5 md:p-7 text-center flex flex-row gap-4 items-center justify-center">
          <PipecatLogo className="h-[24px] w-auto text-gray-500" />
          <div className="flex flex-row gap-2 items-center justify-center opacity-60">
            <p className="text-sm text-muted-foreground font-medium">
              Pipecat AI
            </p>
            <XIcon size={16} className="text-gray-400" />
            <p className="text-sm text-muted-foreground font-medium">
              Voice UI Kit
            </p>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default App;
