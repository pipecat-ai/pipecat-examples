import { PipecatClientProvider } from "@pipecat-ai/client-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@/index.css";
import { App } from "@/app";
import { ErrorBoundary } from "@/components/error-boundary";
import { BotAudioOutput } from "@/components/pipecat/bot-audio";
import { createPipecatClient } from "@/lib/pipecat-client";

const client = await createPipecatClient();
const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <PipecatClientProvider client={client}>
        <App />
        <BotAudioOutput />
      </PipecatClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
