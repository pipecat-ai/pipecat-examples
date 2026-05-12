import {WebSocketTransport} from '@pipecat-ai/websocket-transport';
import {
  AggregationType,
  BotOutputData,
  Participant,
  PipecatClient,
  PipecatClientOptions,
  TranscriptData,
  TransportState,
} from '@pipecat-ai/client-js';

class WebSocketApp {
  private declare connectBtn: HTMLButtonElement;
  private declare disconnectBtn: HTMLButtonElement;
  private declare botAudioElement: HTMLAudioElement;

  private debugLog: HTMLElement | null = null;
  private statusSpan: HTMLElement | null = null;

  private declare pcClient: PipecatClient;

  private declare baseUrl: string;
  private declare startUrl: string;
  private declare apiKey: string;

  constructor() {
    this.setupEnvironmentVariables();
    this.setupDOMElements();
    this.setupDOMEventListeners();
    this.initializePipecatClient();
  }

  private setupEnvironmentVariables() {
    this.baseUrl = import.meta.env.VITE_PIPECAT_BASE_URL
    this.startUrl = `${this.baseUrl}/start`
    this.apiKey = import.meta.env.VITE_PIPECAT_PUBLIC_API;
  }

  private initializePipecatClient(): void {
    const opts: PipecatClientOptions = {
      transport: new WebSocketTransport(),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (state: TransportState) => {
          this.log(`Transport state: ${state}`);
        },
        onConnected: () => {
          this.onConnectedHandler();
        },
        onBotReady: () => {
          this.log('Bot is ready.');
        },
        onDisconnected: () => {
          this.onDisconnectedHandler();
        },
        onUserStartedSpeaking: () => {
          this.log('User started speaking.');
        },
        onUserStoppedSpeaking: () => {
          this.log('User stopped speaking.');
        },
        onBotStartedSpeaking: () => {
          this.log('Bot started speaking.');
        },
        onBotStoppedSpeaking: () => {
          this.log('Bot stopped speaking.');
        },
        onUserTranscript: (transcript: TranscriptData) => {
          if (transcript.final) {
            this.log(`User transcript: ${transcript.text}`);
          }
        },
        onBotOutput: (data: BotOutputData) => {
          if(data.aggregated_by === AggregationType.SENTENCE) {
            this.log(`Bot output: ${data.text}`);
          }
        },
        onTrackStarted: (
          track: MediaStreamTrack,
          participant?: Participant
        ) => {
          if (!participant?.local) {
            this.onBotTrackStarted(track);
          }
        },
        onServerMessage: (msg: unknown) => {
          this.log(`Server message: ${msg}`);
        },
      },
    };
    this.pcClient = new PipecatClient(opts);
    // @ts-ignore
    window.webapp = this;
    // @ts-ignore
    window.client = this.pcClient;
  }

  private setupDOMElements(): void {
    this.connectBtn = document.getElementById(
      'connect-btn'
    ) as HTMLButtonElement;
    this.disconnectBtn = document.getElementById(
      'disconnect-btn'
    ) as HTMLButtonElement;
    this.debugLog = document.getElementById('debug-log');
    this.statusSpan = document.getElementById('connection-status');
    this.botAudioElement = document.getElementById('bot-audio') as HTMLAudioElement;
  }

  private setupDOMEventListeners(): void {
    this.connectBtn.addEventListener('click', () => this.start());
    this.disconnectBtn.addEventListener('click', () => this.stop());
  }

  private log(message: string): void {
    if (!this.debugLog) return;
    const entry = document.createElement('div');
    entry.textContent = `${new Date().toISOString()} - ${message}`;
    if (message.startsWith('User transcript: ')) {
      entry.style.color = '#2196F3';
    } else if (message.startsWith('Bot transcript: ')) {
      entry.style.color = '#4CAF50';
    }
    this.debugLog.appendChild(entry);
    this.debugLog.scrollTop = this.debugLog.scrollHeight;
  }

  private clearAllLogs() {
    this.debugLog!.innerText = '';
  }

  private updateStatus(status: string): void {
    if (this.statusSpan) {
      this.statusSpan.textContent = status;
    }
    this.log(`Status: ${status}`);
  }

  private onConnectedHandler() {
    this.updateStatus('Connected');
    if (this.connectBtn) this.connectBtn.disabled = true;
    if (this.disconnectBtn) this.disconnectBtn.disabled = false;
  }

  private onDisconnectedHandler() {
    this.updateStatus('Disconnected');
    if (this.connectBtn) this.connectBtn.disabled = false;
    if (this.disconnectBtn) this.disconnectBtn.disabled = true;
  }

  private onBotTrackStarted(track: MediaStreamTrack) {
    if (track.kind === 'audio') {
      this.botAudioElement.srcObject = new MediaStream([track]);
    }
  }

  private async start(): Promise<void> {
    this.clearAllLogs();
    await this.pcClient.initDevices();
    this.connectBtn.disabled = true;
    try {
      this.updateStatus('Starting the bot');
      const headers = new Headers();
      headers.append("Authorization", `Bearer ${this.apiKey}`);

      // TODO: this should not be needed in the future
      // When we release a version of websocket transport which knows how to handle it automatically
      const startBotResponseTransformerWebsocket = ({ token, wsUrl}: {
        wsUrl: string;
        token?: string;
      }) => {
        return {
          wsUrl: token ? `${wsUrl}?token=${encodeURIComponent(token)}` : wsUrl,
        };
      };
      const startBotResult = await this.pcClient.startBot({
          endpoint: this.startUrl,
          headers: headers,
          requestData: {
            transport: "websocket"
          }
      });
      // @ts-ignore
      const wsConnectionParams = startBotResponseTransformerWebsocket(startBotResult)
      await this.pcClient.connect(wsConnectionParams)
    } catch (e) {
      console.log(`Failed to connect ${e}`);
      this.stop();
    }
  }

  private stop(): void {
    void this.pcClient.disconnect();
  }
}

const websocketApp = new WebSocketApp();
