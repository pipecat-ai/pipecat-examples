import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport';
import {
  BotLLMTextData,
  Participant,
  PipecatClient,
  PipecatClientOptions,
  TranscriptData,
  TransportState,
} from '@pipecat-ai/client-js';

class WebRTCApp {
  private declare connectBtn: HTMLButtonElement;
  private declare disconnectBtn: HTMLButtonElement;
  private declare micBtn: HTMLButtonElement;
  private declare muteBtn: HTMLButtonElement;
  private declare screenBtn: HTMLButtonElement;

  private declare audioInput: HTMLSelectElement;
  private declare videoInput: HTMLSelectElement;
  private declare audioCodec: HTMLSelectElement;
  private declare videoCodec: HTMLSelectElement;

  private declare botVideoElement: HTMLVideoElement;
  private declare botAudioElement: HTMLAudioElement;

  private declare localCamElement: HTMLVideoElement;
  private declare localScreenElement: HTMLVideoElement;

  private debugLog: HTMLElement | null = null;
  private statusSpan: HTMLElement | null = null;

  private declare smallWebRTCTransport: SmallWebRTCTransport;
  private declare pcClient: PipecatClient;

  constructor() {
    this.setupDOMElements();
    this.setupDOMEventListeners();
    this.initializePipecatClient();
    void this.populateDevices();
  }

  private initializePipecatClient(): void {
    const opts: PipecatClientOptions = {
      transport: new SmallWebRTCTransport({ webrtcUrl: '/api/offer' }),
      // transport: new DailyTransport(),
      enableMic: true,
      enableCam: true,
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
        onBotTranscript: (data: BotLLMTextData) => {
          this.log(`Bot transcript: ${data.text}`);
        },
        onTrackStarted: (
          track: MediaStreamTrack,
          participant?: Participant
        ) => {
          if (participant?.local) {
            this.onLocalTrackStarted(track);
          } else {
            this.onBotTrackStarted(track);
          }
        },
        onTrackStopped: (
          track: MediaStreamTrack,
          participant?: Participant
        ) => {
          if (participant?.local) {
            this.onLocalTrackStopped(track);
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
    window.client = this.pcClient; // Expose client for debugging
    this.smallWebRTCTransport = this.pcClient.transport as SmallWebRTCTransport;
  }

  private setupDOMElements(): void {
    this.connectBtn = document.getElementById(
      'connect-btn'
    ) as HTMLButtonElement;
    this.disconnectBtn = document.getElementById(
      'disconnect-btn'
    ) as HTMLButtonElement;
    this.micBtn = document.getElementById('mute-mic') as HTMLButtonElement;
    this.muteBtn = document.getElementById('mute-btn') as HTMLButtonElement;
    this.screenBtn = document.getElementById('screen-btn') as HTMLButtonElement;

    this.audioInput = document.getElementById(
      'audio-input'
    ) as HTMLSelectElement;
    this.videoInput = document.getElementById(
      'video-input'
    ) as HTMLSelectElement;
    this.audioCodec = document.getElementById(
      'audio-codec'
    ) as HTMLSelectElement;
    this.videoCodec = document.getElementById(
      'video-codec'
    ) as HTMLSelectElement;

    this.botVideoElement = document.getElementById(
      'bot-video'
    ) as HTMLVideoElement;
    this.botAudioElement = document.getElementById(
      'bot-audio'
    ) as HTMLAudioElement;

    this.localCamElement = document.getElementById(
      'local-cam'
    ) as HTMLVideoElement;
    this.localScreenElement = document.getElementById(
      'local-screen'
    ) as HTMLVideoElement;

    this.debugLog = document.getElementById('debug-log');
    this.statusSpan = document.getElementById('connection-status');
  }

  private setupDOMEventListeners(): void {
    this.connectBtn.addEventListener('click', () => this.start());
    this.disconnectBtn.addEventListener('click', () => this.stop());
    this.audioInput.addEventListener('change', (e) => {
      // @ts-ignore
      let audioDevice = e.target?.value;
      this.pcClient.updateMic(audioDevice);
    });
    this.micBtn.addEventListener('click', async () => {
      if (this.pcClient.state === 'disconnected') {
        await this.pcClient.initDevices();
      } else {
        let isMicEnabled = this.pcClient.isMicEnabled;
        this.pcClient.enableMic(!isMicEnabled);
      }
    });
    this.videoInput.addEventListener('change', (e) => {
      // @ts-ignore
      let videoDevice = e.target?.value;
      this.pcClient.updateCam(videoDevice);
    });
    this.muteBtn.addEventListener('click', async () => {
      if (this.pcClient.state === 'disconnected') {
        await this.pcClient.initDevices();
      } else {
        let isCamEnabled = this.pcClient.isCamEnabled;
        this.pcClient.enableCam(!isCamEnabled);
      }
    });
    this.screenBtn.addEventListener('click', async () => {
      if (this.pcClient.state === 'disconnected') {
        await this.pcClient.initDevices();
      }
      let isScreenEnabled = this.pcClient.isSharingScreen;
      this.pcClient.enableScreenShare(!isScreenEnabled);
    });
  }

  private log(message: string): void {
    if (!this.debugLog) return;
    const entry = document.createElement('div');
    entry.textContent = `${new Date().toISOString()} - ${message}`;
    if (message.startsWith('User: ')) {
      entry.style.color = '#2196F3';
    } else if (message.startsWith('Bot: ')) {
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

  private onLocalTrackStarted(track: MediaStreamTrack) {
    if (track.kind === 'audio') {
      this.micBtn.innerHTML = 'Mute Mic';
      return;
    }

    const settings = track.getSettings();
    // ... Because Firefox 😡
    interface FirefoxConstraints extends MediaTrackConstraints {
      mediaSource?: string;
    }
    const constraints = track.getConstraints() as FirefoxConstraints;
    const screenShareOpts = ['window', 'monitor', 'browser'];
    if (
      screenShareOpts.includes(settings?.displaySurface ?? '') ||
      screenShareOpts.includes(constraints?.mediaSource ?? '')
    ) {
      this.localScreenElement.srcObject = new MediaStream([track]);
      (document.getElementById('screen-x') as HTMLDivElement).hidden = true;
    } else {
      this.localCamElement.srcObject = new MediaStream([track]);
      (document.getElementById('cam-x') as HTMLDivElement).hidden = true;
    }
  }

  private onBotTrackStarted(track: MediaStreamTrack) {
    if (track.kind === 'video') {
      this.botVideoElement.srcObject = new MediaStream([track]);
    } else {
      this.botAudioElement.srcObject = new MediaStream([track]);
    }
  }

  private onLocalTrackStopped(track: MediaStreamTrack) {
    if (track.kind === 'audio') {
      this.micBtn.innerHTML = 'Unmute Mic';
      return;
    }

    const settings = track.getSettings();
    // ... Because Firefox 😡
    interface FirefoxConstraints extends MediaTrackConstraints {
      mediaSource?: string;
    }
    const constraints = track.getConstraints() as FirefoxConstraints;
    const screenShareOpts = ['window', 'monitor', 'browser'];
    if (
      screenShareOpts.includes(settings?.displaySurface ?? '') ||
      screenShareOpts.includes(constraints?.mediaSource ?? '')
    ) {
      this.localScreenElement.srcObject = null;
      (document.getElementById('screen-x') as HTMLDivElement).hidden = false;
    } else {
      this.localCamElement.srcObject = null;
      (document.getElementById('cam-x') as HTMLDivElement).hidden = false;
    }
  }

  private async populateDevices(): Promise<void> {
    const populateSelect = (
      select: HTMLSelectElement,
      devices: MediaDeviceInfo[]
    ): void => {
      let counter = 1;
      devices.forEach((device) => {
        const option = document.createElement('option');
        option.value = device.deviceId;
        option.text = device.label || 'Device #' + counter;
        select.appendChild(option);
        counter += 1;
      });
    };

    try {
      const audioDevices = await this.pcClient.getAllMics();
      populateSelect(this.audioInput, audioDevices);
      const videoDevices = await this.pcClient.getAllCams();
      populateSelect(this.videoInput, videoDevices);
    } catch (e) {
      alert(e);
    }
  }

  private async start(): Promise<void> {
    this.clearAllLogs();

    this.connectBtn.disabled = true;
    this.updateStatus('Connecting');

    if (this.smallWebRTCTransport) {
      this.smallWebRTCTransport.setAudioCodec(this.audioCodec.value);
      this.smallWebRTCTransport.setVideoCodec(this.videoCodec.value);
    }
    try {
      await this.pcClient.connect();
    } catch (e) {
      console.log(`Failed to connect ${e}`);
      this.stop();
    }
  }

  private stop(): void {
    void this.pcClient.disconnect();
  }
}

// Create the WebRTCConnection instance
const webRTCConnection = new WebRTCApp();
