import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import type { PipecatBaseChildProps } from "@pipecat-ai/voice-ui-kit";
import {
  ErrorCard,
  FullScreenContainer,
  PipecatAppBase,
  SpinLoader,
  ThemeProvider,
} from "@pipecat-ai/voice-ui-kit";
import "@pipecat-ai/voice-ui-kit/styles";

import { App } from "./App";
import { readMoqSession } from "./session";

const session = readMoqSession();

function Root() {
  if (!session) {
    return (
      <ErrorCard>
        No relay configured. Set <code>MOQ_RELAY_URL</code> in the host's{" "}
        <code>.env</code> and restart the dev server, or name one in the URL:
        <code> ?relay=http://localhost:4443</code>.
      </ErrorCard>
    );
  }

  return (
    // No connectParams or startBotParams: there is no /start to call, so the
    // base connects the transport straight from these options.
    <PipecatAppBase transportType="moq" transportOptions={session}>
      {({ client, handleConnect, handleDisconnect, error }: PipecatBaseChildProps) =>
        !client ? (
          <SpinLoader />
        ) : error ? (
          <ErrorCard>{error}</ErrorCard>
        ) : (
          <App
            client={client}
            handleConnect={handleConnect}
            handleDisconnect={handleDisconnect}
          />
        )
      }
    </PipecatAppBase>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="terminal" disableStorage>
      <FullScreenContainer>
        <Root />
      </FullScreenContainer>
    </ThemeProvider>
  </StrictMode>,
);
