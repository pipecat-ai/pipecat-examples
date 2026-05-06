/**
 * Copyright (c) 2024–2025, Daily
 *
 * SPDX-License-Identifier: BSD 2-Clause License
 */

import { PipecatClient } from "@pipecat-ai/client-js";
import { DailyTransport } from "@pipecat-ai/daily-transport";

/**
 * ChatbotClient handles the connection and media management for a real-time
 * voice interaction with an AI bot using the Pipecat client SDK.
 *
 * The bot-ready handshake is handled by RTVI: the SDK signals client-ready
 * automatically once the transport reaches the `ready` state, the bot replies
 * with `bot-ready`, and only then does the bot push its first TTS frame. No
 * manual sendAppMessage / "playable" plumbing is needed.
 */
class ChatbotClient {
  constructor() {
    this.pcClient = null;
    this.botAudio = null;
    this.setupDOMElements();
    this.setupEventListeners();
  }

  setupDOMElements() {
    this.connectBtn = document.getElementById('connect-btn');
    this.disconnectBtn = document.getElementById('disconnect-btn');
    this.statusSpan = document.getElementById('connection-status');
    this.debugLog = document.getElementById('debug-log');
  }

  setupEventListeners() {
    this.connectBtn.addEventListener('click', () => this.connect());
    this.disconnectBtn.addEventListener('click', () => this.disconnect());
  }

  log(message) {
    const entry = document.createElement('div');
    entry.textContent = `${new Date().toISOString()} - ${message}`;

    if (message.startsWith('User: ')) {
      entry.style.color = '#2196F3';
    } else if (message.startsWith('Bot: ')) {
      entry.style.color = '#4CAF50';
    }

    this.debugLog.appendChild(entry);
    this.debugLog.scrollTop = this.debugLog.scrollHeight;
    console.log(message);
  }

  updateStatus(status) {
    this.statusSpan.textContent = status;
    this.log(`Status: ${status}`);
  }

  /**
   * Attach the bot's audio track to a hidden <audio> element so it plays back.
   * The Pipecat client SDK fires onTrackStarted for every remote track.
   */
  handleBotAudio(track, participant) {
    if (participant?.local || track.kind !== 'audio') return;

    this.log('Bot audio track started.');

    if (!this.botAudio) {
      this.botAudio = document.createElement('audio');
      this.botAudio.autoplay = true;
      this.botAudio.playsInline = true;
      document.body.appendChild(this.botAudio);
    }

    this.botAudio.srcObject = new MediaStream([track]);
  }

  removeBotAudio() {
    if (this.botAudio) {
      const stream = this.botAudio.srcObject;
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
      }
      this.botAudio.srcObject = null;
      this.botAudio.remove();
      this.botAudio = null;
    }
  }

  async connect() {
    if (this.pcClient) return;

    try {
      this.pcClient = new PipecatClient({
        transport: new DailyTransport(),
        enableMic: true,
        enableCam: false,
        callbacks: {
          onTransportStateChanged: (state) => {
            this.updateStatus(state);
            const isConnected = state === 'ready';
            this.connectBtn.disabled = state !== 'idle' && state !== 'disconnected';
            this.disconnectBtn.disabled = !isConnected;
          },
          onBotReady: () => {
            this.log('Bot ready: greeting will play next.');
          },
          onTrackStarted: (track, participant) => this.handleBotAudio(track, participant),
          onDisconnected: () => {
            this.log('Disconnected from bot.');
            this.removeBotAudio();
            this.pcClient = null;
            window.pcClient = null;
            this.connectBtn.disabled = false;
            this.disconnectBtn.disabled = true;
          },
          onError: (message) => {
            const detail =
              message?.data?.message ??
              (typeof message?.data === 'string' ? message.data : null) ??
              message?.message ??
              JSON.stringify(message);
            this.log(`Error: ${detail}`);
          },
        },
      });

      // Expose for debugging.
      window.pcClient = this.pcClient;

      this.log('Creating the bot...');
      await this.pcClient.startBotAndConnect({
        endpoint: '/start',
        requestData: { createDailyRoom: true },
      });
      this.log('Connection complete.');
    } catch (error) {
      this.log(`Error connecting: ${error.message}`);
      this.log(`Error stack: ${error.stack}`);
      this.updateStatus('Error');

      if (this.pcClient) {
        try {
          await this.pcClient.disconnect();
        } catch (disconnectError) {
          this.log(`Error during disconnect: ${disconnectError.message}`);
        }
      }

      this.pcClient = null;
      window.pcClient = null;
      this.removeBotAudio();
      this.connectBtn.disabled = false;
      this.disconnectBtn.disabled = true;
    }
  }

  async disconnect() {
    if (this.pcClient) {
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
}

window.addEventListener('DOMContentLoaded', () => {
  new ChatbotClient();
});
