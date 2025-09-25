/**
 * Copyright (c) 2024–2025, Daily
 *
 * SPDX-License-Identifier: BSD 2-Clause License
 */

/**
 * Pipecat Client Implementation
 *
 * This client connects to an RTVI-compatible bot server using WebSocket.
 *
 * Requirements:
 * - A running RTVI bot server (defaults to http://localhost:7860)
 */

import {
  PipecatClient,
  PipecatClientOptions,
  RTVIEvent,
} from '@pipecat-ai/client-js';
import { WebSocketTransport } from '@pipecat-ai/websocket-transport';

class WebsocketClientApp {
  private pcClient: PipecatClient | null = null;
  private connectBtn: HTMLButtonElement | null = null;
  private disconnectBtn: HTMLButtonElement | null = null;
  private statusSpan: HTMLElement | null = null;
  private debugLog: HTMLElement | null = null;
  private botAudio: HTMLAudioElement;
  
  // Text input elements
  private textInput: HTMLInputElement | null = null;
  private sendTextBtn: HTMLButtonElement | null = null;
  
  // Audio control elements
  private deviceSelector: HTMLSelectElement | null = null;
  private micToggleBtn: HTMLButtonElement | null = null;

  constructor() {
    console.log('WebsocketClientApp');
    this.botAudio = document.createElement('audio');
    this.botAudio.autoplay = true;
    //this.botAudio.playsInline = true;
    document.body.appendChild(this.botAudio);

    this.setupDOMElements();
    this.setupEventListeners();
  }

  /**
   * Set up references to DOM elements and create necessary media elements
   */
  private setupDOMElements(): void {
    this.connectBtn = document.getElementById(
      'connect-btn'
    ) as HTMLButtonElement;
    this.disconnectBtn = document.getElementById(
      'disconnect-btn'
    ) as HTMLButtonElement;
    this.statusSpan = document.getElementById('connection-status');
    this.debugLog = document.getElementById('debug-log');
    
    // Text input elements
    this.textInput = document.getElementById('text-input') as HTMLInputElement;
    this.sendTextBtn = document.getElementById('send-text-btn') as HTMLButtonElement;
    
    // Audio control elements
    this.deviceSelector = document.getElementById('device-selector') as HTMLSelectElement;
    this.micToggleBtn = document.getElementById('mic-toggle-btn') as HTMLButtonElement;
  }

  /**
   * Set up event listeners for connect/disconnect buttons, text input, and audio controls
   */
  private setupEventListeners(): void {
    this.connectBtn?.addEventListener('click', () => this.connect());
    this.disconnectBtn?.addEventListener('click', () => this.disconnect());

    // Text input functionality
    const sendTextToBot = (): void => {
      if (!this.textInput || !this.sendTextBtn || !this.pcClient) return;
      
      this.sendTextBtn.disabled = true; // Disable button to prevent multiple clicks
      const text = this.textInput.value.trim();
      
      if (text) {
        this.log(`Sending text: ${text}`);
        // Send text message to bot
        void this.pcClient.appendToContext({
          role: 'user',
          content: text,
          run_immediately: true,
        });
      }
      
      this.textInput.value = ''; // Clear the input
      this.sendTextBtn.disabled = false; // Re-enable button after sending
    };

    // Text input event listeners
    this.sendTextBtn?.addEventListener('click', sendTextToBot);

    // Handle Enter key in the text input
    this.textInput?.addEventListener('keypress', (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        sendTextToBot();
      }
    });

     // Populate device selector
    this.pcClient?.getAllMics().then((mics) => {
      console.log('Available mics:', mics);
      mics.forEach((device) => {
        const option = document.createElement('option');
        option.value = device.deviceId;
        option.textContent = device.label || `Microphone ${device.deviceId}`;
        this.deviceSelector?.appendChild(option);
      });
    });
     this.deviceSelector?.addEventListener('change', (event: Event) => {
      const target = event.target as HTMLSelectElement;
      const selectedDeviceId = target.value;
      console.log('Selected device ID:', selectedDeviceId);
      if (this.pcClient) {
        this.pcClient.updateMic(selectedDeviceId);
      }
    });
    this.micToggleBtn?.addEventListener('click', async () => {
      if (this.pcClient?.state === 'disconnected') {
        await this.pcClient.initDevices();
      } else {
        this.pcClient?.enableMic(!this.pcClient.isMicEnabled);
      }
    });
  }

  /**
   * Set up audio control event listeners - called after pcClient is created
   */
  private setupAudioControls(): void {
    if (!this.pcClient) return;

    // Setup mic toggle button listener
    this.micToggleBtn?.addEventListener('click', async () => {
      if (!this.pcClient) return;
      
      if (this.pcClient.state === 'disconnected') {
        try {
          await this.pcClient.initDevices();
          this.updateMicToggleButton(true);
        } catch (error) {
          console.log('Error initializing devices:', error);
        }
      } else {
        this.pcClient.enableMic(!this.pcClient.isMicEnabled);
      }
    });

    // Setup device selector listener
    this.deviceSelector?.addEventListener('change', (event: Event) => {
      const target = event.target as HTMLSelectElement;
      const selectedDeviceId = target.value;
      console.log('Selected device ID:', selectedDeviceId);
      if (this.pcClient) {
        this.pcClient.updateMic(selectedDeviceId);
      }
    });
  }

  /**
   * Populate the device selector with available microphones
   */
  private async populateDeviceSelector(): Promise<void> {
    if (!this.pcClient || !this.deviceSelector) return;

    try {
      const mics = await this.pcClient.getAllMics();
      console.log('Available mics:', mics);
      
      // Clear existing options
      this.deviceSelector.innerHTML = '';
      
      mics.forEach((device: any) => {
        const option = document.createElement('option');
        option.value = device.deviceId;
        option.textContent = device.label || `Microphone ${device.deviceId}`;
        this.deviceSelector!.appendChild(option);
      });
    } catch (error) {
      console.log('Error getting microphones:', error);
    }
  }

  /**
   * Update the mic toggle button text based on current state
   */
  private updateMicToggleButton(micEnabled: boolean): void {
    console.log('Mic enabled:', micEnabled);
    if (this.micToggleBtn) {
      this.micToggleBtn.textContent = micEnabled ? 'Mute Mic' : 'Unmute Mic';
    }
  }

  /**
   * Add a timestamped message to the debug log
   */
  private log(message: string): void {
    if (!this.debugLog) return;
    const entry = document.createElement('div');
    entry.textContent = `${new Date().toISOString()} - ${message}`;
    
    // Add styling based on message type
    if (message.startsWith('User: ')) {
      entry.style.color = '#2196F3';
    } else if (message.startsWith('Bot: ')) {
      entry.style.color = '#4CAF50';
    } else if (message.startsWith('Sending text: ')) {
      entry.style.color = '#FF9800'; // orange for text messages
    }
    
    this.debugLog.appendChild(entry);
    this.debugLog.scrollTop = this.debugLog.scrollHeight;
    console.log(message);
  }

  /**
   * Update the connection status display
   */
  private updateStatus(status: string): void {
    if (this.statusSpan) {
      this.statusSpan.textContent = status;
    }
    this.log(`Status: ${status}`);
  }

  /**
   * Check for available media tracks and set them up if present
   * This is called when the bot is ready or when the transport state changes to ready
   */
  setupMediaTracks() {
    if (!this.pcClient) return;
    const tracks = this.pcClient.tracks();
    if (tracks.bot?.audio) {
      this.setupAudioTrack(tracks.bot.audio);
    }
  }

  /**
   * Set up listeners for track events (start/stop)
   * This handles new tracks being added during the session
   */
  setupTrackListeners() {
    if (!this.pcClient) return;

    // Listen for new tracks starting
    this.pcClient.on(RTVIEvent.TrackStarted, (track, participant) => {
      // Only handle non-local (bot) tracks
      if (!participant?.local && track.kind === 'audio') {
        this.setupAudioTrack(track);
      } else if (participant?.local && track.kind === 'audio') {
        console.log(`Local audio track started`);
        // If local audio track starts, update mic toggle button
        this.updateMicToggleButton(true);
      }
    });

    // Listen for tracks stopping
    this.pcClient.on(RTVIEvent.TrackStopped, (track, participant) => {
      this.log(
        `Track stopped: ${track.kind} from ${participant?.name || 'unknown'}`
      );
      if (participant?.local && track.kind === 'audio') {
        // If local audio track stops, update mic toggle button
        this.updateMicToggleButton(false);
      }
    });
  }

  /**
   * Set up an audio track for playback
   * Handles both initial setup and track updates
   */
  private setupAudioTrack(track: MediaStreamTrack): void {
    this.log('Setting up audio track');
    if (
      this.botAudio.srcObject &&
      'getAudioTracks' in this.botAudio.srcObject
    ) {
      const oldTrack = this.botAudio.srcObject.getAudioTracks()[0];
      if (oldTrack?.id === track.id) return;
    }
    this.botAudio.srcObject = new MediaStream([track]);
  }

  /**
   * Initialize and connect to the bot
   * This sets up the Pipecat client, initializes devices, and establishes the connection
   */
  public async connect(): Promise<void> {
    try {
      const startTime = Date.now();

      //const transport = new DailyTransport();
      const PipecatConfig: PipecatClientOptions = {
        transport: new WebSocketTransport(),
        enableMic: true,
        enableCam: false,
        callbacks: {
          onConnected: () => {
            this.updateStatus('Connected');
            if (this.connectBtn) this.connectBtn.disabled = true;
            if (this.disconnectBtn) this.disconnectBtn.disabled = false;
          },
          onDisconnected: () => {
            this.updateStatus('Disconnected');
            if (this.connectBtn) this.connectBtn.disabled = false;
            if (this.disconnectBtn) this.disconnectBtn.disabled = true;
            if (this.sendTextBtn) this.sendTextBtn.disabled = true; // Disable text input when disconnected
            this.updateMicToggleButton(false); // Reset mic button when disconnected
            this.log('Client disconnected');
          },
          onBotReady: (data) => {
            this.log(`Bot ready: ${JSON.stringify(data)}`);
            this.setupMediaTracks();
            if (this.sendTextBtn) this.sendTextBtn.disabled = false; // Enable text input when bot is ready
          },
          onUserTranscript: (data) => {
            if (data.final) {
              this.log(`User: ${data.text}`);
            }
          },
          onBotTranscript: (data) => this.log(`Bot: ${data.text}`),
          onMessageError: (error) => console.error('Message error:', error),
          onError: (error) => console.error('Error:', error),
          // Handle mic updates
          onMicUpdated: (data: any) => {
            console.log('Mic updated:', data);
            if (this.deviceSelector && data.deviceId) {
              this.deviceSelector.value = data.deviceId;
            }
          },
        },
      };
      this.pcClient = new PipecatClient(PipecatConfig);
      // @ts-ignore
      window.pcClient = this.pcClient; // Expose for debugging
      this.setupTrackListeners();

      this.log('Initializing devices...');
      await this.pcClient.initDevices();

      this.log('Connecting to bot...');
      await this.pcClient.startBotAndConnect({
        // The baseURL and endpoint of your bot server that the client will connect to
        endpoint: 'http://localhost:7860/connect',
      });

      const timeTaken = Date.now() - startTime;
      this.log(`Connection complete, timeTaken: ${timeTaken}`);
    } catch (error) {
      this.log(`Error connecting: ${(error as Error).message}`);
      this.updateStatus('Error');
      // Clean up if there's an error
      if (this.pcClient) {
        try {
          await this.pcClient.disconnect();
        } catch (disconnectError) {
          this.log(`Error during disconnect: ${disconnectError}`);
        }
      }
    }
  }

  /**
   * Disconnect from the bot and clean up media resources
   */
  public async disconnect(): Promise<void> {
    if (this.pcClient) {
      try {
        await this.pcClient.disconnect();
        this.pcClient = null;
        if (
          this.botAudio.srcObject &&
          'getAudioTracks' in this.botAudio.srcObject
        ) {
          this.botAudio.srcObject
            .getAudioTracks()
            .forEach((track) => track.stop());
          this.botAudio.srcObject = null;
        }
      } catch (error) {
        this.log(`Error disconnecting: ${(error as Error).message}`);
      }
    }
  }
}

declare global {
  interface Window {
    WebsocketClientApp: typeof WebsocketClientApp;
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.WebsocketClientApp = WebsocketClientApp;
  new WebsocketClientApp();
});