"use client";

import React, { useState } from "react";
import { usePipecatClient } from "@pipecat-ai/client-react";

import Setup from "./Setup";
import Story from "./Story";

type State =
  | "idle"
  | "connecting"
  | "connected"
  | "started"
  | "finished"
  | "error";

export default function App() {
  const client = usePipecatClient();

  const [state, setState] = useState<State>("idle");

  async function start() {
    if (!client) return;

    setState("connecting");

    try {
      // Mute the mic until the bot hands the user their turn; the bot says
      // hello first and we don't want its intro echoing back into the story.
      client.enableMic(false);

      // Start a bot and join the WebRTC session. The Next.js API routes
      // forward these requests to the bot server (local or Pipecat Cloud).
      await client.startBotAndConnect({
        endpoint: "/api/start",
        requestData: {
          transport: "webrtc",
          createDailyRoom: false,
          enableDefaultIceServers: true,
        },
      });

      setState("started");
    } catch (error) {
      console.error("Failed to start the story", error);
      setState("error");
    }
  }

  async function leave() {
    await client?.disconnect();
    setState("finished");
  }

  if (state === "error") {
    return (
      <div className="flex items-center mx-auto">
        <p className="text-red-500 font-semibold bg-white px-4 py-2 shadow-xl rounded-lg">
          This demo is currently at capacity. Please try again later.
        </p>
      </div>
    );
  }

  if (state === "started") {
    return <Story handleLeave={() => leave()} />;
  }

  return <Setup handleStart={() => start()} />;
}
