"use client";

import { usePipecatClient } from "@pipecat-ai/client-react";
import { XIcon } from "lucide-react";
import { useEffect } from "react";

import { ConnectButton } from "@/components/pipecat/connect-button";
import { UserAudioControl } from "@/components/pipecat/user-audio-control";
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import type { TransportType } from "../../config";
import { BotVideoPanel } from "./BotVideoPanel";
import { ConversationPanel } from "./ConversationPanel";
import { EventsPanel } from "./EventsPanel";
import { TransportSelect } from "./TransportSelect";

const DISCONNECT_FILL =
  "bg-inactive text-inactive-foreground hover:bg-inactive/90 hover:text-inactive-foreground dark:bg-inactive";

interface AppProps {
  onConnect: () => void;
  onDisconnect: () => void;
  /** Session error from usePipecatApp, shown as a dismissible banner. */
  error: string | null;
  onDismissError: () => void;
  transportType: TransportType;
  onTransportChange: (type: TransportType) => void;
  availableTransports: TransportType[];
}

export const App = ({
  onConnect,
  onDisconnect,
  error,
  onDismissError,
  transportType,
  onTransportChange,
  availableTransports,
}: AppProps) => {
  const client = usePipecatClient();
  useEffect(() => {
    if (!client) return;
    // PipecatClientProvider attaches its transport-state listener in its own
    // effect, which runs after this child effect. Yield one microtask so the
    // synchronous "initializing" transition is observed and the connect
    // button disables itself while the permission prompt is up. Device
    // errors surface through the mic control's own error states.
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) client.initDevices().catch(() => {});
    });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const showTransportSelector = availableTransports.length > 1;

  return (
    <div className="flex h-full w-full flex-col gap-4 p-4">
      <div className="flex items-center justify-between gap-4">
        {showTransportSelector ? (
          <TransportSelect
            transportType={transportType}
            onTransportChange={onTransportChange}
            availableTransports={availableTransports}
          />
        ) : (
          <div /> /* Spacer */
        )}
        <div className="flex items-center gap-4">
          <UserAudioControl size="lg" />
          <ConnectButton
            size="lg"
            onConnect={onConnect}
            onDisconnect={onDisconnect}
            // Solid fill for the disconnect states, still driven by the
            // --inactive-* tokens so retheming reaches the button.
            stateProps={{
              connected: { className: DISCONNECT_FILL },
              ready: { className: DISCONNECT_FILL },
            }}
          />
        </div>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Session error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
          <AlertAction>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Dismiss"
              onClick={onDismissError}
            >
              <XIcon />
            </Button>
          </AlertAction>
        </Alert>
      )}
      <div className="flex min-h-0 flex-1 gap-4">
        <BotVideoPanel className="flex-1" />
        <ConversationPanel className="flex-1" />
      </div>
      <EventsPanel className="h-60" />
    </div>
  );
};
