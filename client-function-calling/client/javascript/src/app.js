/**
 * Copyright (c) 2026, Daily
 *
 * SPDX-License-Identifier: BSD 2-Clause License
 */

import { PipecatClient } from "@pipecat-ai/client-js";
import { DailyTransport } from "@pipecat-ai/daily-transport";

/**
 * Tools the bot's LLM can call, run here in the browser.
 *
 * Each handler receives the call's arguments and returns the result the LLM
 * reads. The SDK sends that result back to the bot as
 * `llm-function-call-result`. The names must match the tools declared in
 * server/bot.py.
 */
const CLIENT_TOOLS = {
  get_local_time: async () => {
    const now = new Date();
    return {
      local_time: now.toLocaleString(undefined, {
        dateStyle: "full",
        timeStyle: "short",
      }),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
  },

  set_background_color: async ({ color }) => {
    if (typeof color !== "string" || !CSS.supports("color", color)) {
      return { success: false, error: `"${color}" is not a valid CSS color.` };
    }
    document.body.style.backgroundColor = color;
    return { success: true, color };
  },
};

class ChatbotClient {
  constructor() {
    this.pcClient = null;
    this.botAudio = null;
    this.connectBtn = document.getElementById("connect-btn");
    this.disconnectBtn = document.getElementById("disconnect-btn");
    this.statusSpan = document.getElementById("connection-status");
    this.debugLog = document.getElementById("debug-log");
    this.connectBtn.addEventListener("click", () => this.connect());
    this.disconnectBtn.addEventListener("click", () => this.disconnect());
  }

  log(message, className) {
    const entry = document.createElement("div");
    entry.textContent = `${new Date().toLocaleTimeString()} - ${message}`;
    if (className) entry.className = className;
    this.debugLog.appendChild(entry);
    this.debugLog.scrollTop = this.debugLog.scrollHeight;
    console.log(message);
  }

  updateStatus(state) {
    this.statusSpan.textContent = state;
    this.connectBtn.disabled = state !== "disconnected" && state !== "error";
    this.disconnectBtn.disabled = state === "disconnected" || state === "error";
  }

  registerTools() {
    for (const [name, run] of Object.entries(CLIENT_TOOLS)) {
      this.pcClient.registerFunctionCallHandler(name, async ({ arguments: args }) => {
        this.log(`Tool call: ${name}(${JSON.stringify(args)})`, "log-tool");
        const result = await run(args);
        this.log(`Tool result: ${name} -> ${JSON.stringify(result)}`, "log-tool");
        return result;
      });
    }
  }

  /** Play the bot's audio track through a hidden <audio> element. */
  handleBotAudio(track, participant) {
    if (participant?.local || track.kind !== "audio") return;
    if (!this.botAudio) {
      this.botAudio = document.createElement("audio");
      this.botAudio.autoplay = true;
      this.botAudio.playsInline = true;
      document.body.appendChild(this.botAudio);
    }
    this.botAudio.srcObject = new MediaStream([track]);
  }

  removeBotAudio() {
    if (!this.botAudio) return;
    this.botAudio.srcObject = null;
    this.botAudio.remove();
    this.botAudio = null;
  }

  async connect() {
    if (this.pcClient) return;

    this.pcClient = new PipecatClient({
      transport: new DailyTransport(),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (state) => this.updateStatus(state),
        onBotReady: () => this.log("Bot ready."),
        onUserTranscript: (data) => {
          if (data.final) this.log(`User: ${data.text}`, "log-user");
        },
        onBotOutput: (data) => {
          if (data.aggregated_by === "sentence") this.log(`Bot: ${data.text}`, "log-bot");
        },
        onTrackStarted: (track, participant) => this.handleBotAudio(track, participant),
        onDisconnected: () => {
          this.log("Disconnected.");
          this.removeBotAudio();
          this.pcClient = null;
          this.updateStatus("disconnected");
        },
        onError: (message) => this.log(`Error: ${JSON.stringify(message?.data ?? message)}`),
      },
    });
    window.pcClient = this.pcClient; // for debugging in the console

    this.registerTools();

    try {
      await this.pcClient.startBotAndConnect({
        endpoint: "/start",
        requestData: { createDailyRoom: true },
      });
    } catch (error) {
      this.log(`Error connecting: ${error.message}`);
      await this.disconnect();
      this.updateStatus("error");
    }
  }

  async disconnect() {
    if (!this.pcClient) return;
    try {
      await this.pcClient.disconnect();
    } catch (error) {
      this.log(`Error disconnecting: ${error.message}`);
    } finally {
      this.pcClient = null;
      this.removeBotAudio();
    }
  }
}

window.addEventListener("DOMContentLoaded", () => new ChatbotClient());
