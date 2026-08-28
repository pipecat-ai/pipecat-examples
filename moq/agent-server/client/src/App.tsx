import { useEffect } from "react";

import type { PipecatBaseChildProps } from "@pipecat-ai/voice-ui-kit";
import {
  ConnectButton,
  ConversationPanel,
  EventsPanel,
  UserAudioControl,
} from "@pipecat-ai/voice-ui-kit";

export const App = ({
  client,
  handleConnect,
  handleDisconnect,
}: PipecatBaseChildProps) => {
  useEffect(() => {
    client?.initDevices();
  }, [client]);

  return (
    <div className="flex flex-col w-full h-full">
      <div className="flex items-center justify-end gap-4 p-4">
        <UserAudioControl size="lg" />
        <ConnectButton
          size="lg"
          onConnect={handleConnect}
          onDisconnect={handleDisconnect}
        />
      </div>
      <div className="flex-1 overflow-hidden px-4">
        <ConversationPanel />
      </div>
      <div className="h-96 overflow-hidden px-4 pb-4">
        <EventsPanel />
      </div>
    </div>
  );
};
