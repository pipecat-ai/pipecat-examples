import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js';
import {
  AVAILABLE_TRANSPORTS,
  DEFAULT_TRANSPORT,
  TRANSPORT_CONFIG,
  createTransport,
} from './config';

class VoiceChatClient {
  constructor() {
    this.client = null;
    this.transportType = DEFAULT_TRANSPORT;
    this.isConnected = false;

    this.setupDOM();
    this.setupEventListeners();
    this.addEvent('initialized', 'Client initialized');
  }

  setupDOM() {
    this.transportSelect = document.getElementById('transport-select');
    this.connectBtn = document.getElementById('connect-btn');
    this.micBtn = document.getElementById('mic-btn');
    this.micStatus = document.getElementById('mic-status');
    this.conversationLog = document.getElementById('conversation-log');
    this.eventsLog = document.getElementById('events-log');
    this.uploadBtn = document.getElementById('upload-btn');
    this.uploadModal = document.getElementById('upload-modal');
    this.closeBtn = document.querySelector('.close-btn');
    this.uploadConfirmBtn = document.getElementById('upload-confirm-btn');
    this.fileInput = document.getElementById('file-input');
    this.urlInput = document.getElementById('url-input');
    this.filePrompt = document.getElementById('file-prompt');
    this.uploadTabs = document.querySelectorAll('.tab-link');
    this.tabContents = document.querySelectorAll('.tab-content');
    this.lastConversationBubble = null;
    this.botSpans = {};

    // Populate transport selector with available transports
    this.transportSelect.innerHTML = '';
    AVAILABLE_TRANSPORTS.forEach((transport) => {
      const option = document.createElement('option');
      option.value = transport;
      option.textContent =
        transport.charAt(0).toUpperCase() + transport.slice(1);
      if (transport === 'smallwebrtc') {
        option.textContent = 'SmallWebRTC';
      } else if (transport === 'daily') {
        option.textContent = 'Daily';
      } else if (transport === 'websocket') {
        option.textContent = 'WebSocket';
      }
      this.transportSelect.appendChild(option);
    });

    // Hide transport selector if only one transport
    if (AVAILABLE_TRANSPORTS.length === 1) {
      this.transportSelect.parentElement.style.display = 'none';
    }

    // Add placeholder message
    this.addConversationMessage(
      'Connect to start talking with your bot',
      'placeholder',
    );
  }

  setupEventListeners() {
    this.transportSelect.addEventListener('change', (e) => {
      this.transportType = e.target.value;
      this.addEvent('transport-changed', this.transportType);
    });

    this.connectBtn.addEventListener('click', () => {
      if (this.isConnected) {
        this.disconnect();
      } else {
        this.connect();
      }
    });

    this.micBtn.addEventListener('click', () => {
      if (this.client) {
        const newState = !this.client.isMicEnabled;
        this.client.enableMic(newState);
        this.updateMicButton(newState);
      }
    });

    this.uploadBtn.addEventListener('click', () => {
      this.uploadModal.style.display = 'block';
    });

    this.closeBtn.addEventListener('click', () => {
      this.uploadModal.style.display = 'none';
    });

    window.addEventListener('click', (event) => {
      if (event.target === this.uploadModal) {
        this.uploadModal.style.display = 'none';
      }
    });

    this.uploadConfirmBtn.addEventListener('click', () => {
      this.handleContentUpload();
    });

    this.uploadTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const target = tab.getAttribute('data-tab');
        this.uploadTabs.forEach((t) => t.classList.remove('active'));
        tab.classList.add('active');
        this.tabContents.forEach((c) => c.classList.remove('active'));
        document.getElementById(target).classList.add('active');
      });
    });
  }

  handleContentUpload() {
    const activeTab = document.querySelector('.tab-link.active').dataset.tab;
    const prompt = this.filePrompt.value;
    if (activeTab === 'file-tab') {
      this.handleFileUpload(prompt);
    } else {
      this.handleUrlUpload(prompt);
    }
  }

  handleUrlUpload(prompt) {
    const url = this.urlInput.value;
    if (!url) {
      alert('Please enter a URL.');
      return;
    }

    const rtvi_file = {
      format: url.split('.').pop(),
      source: { type: 'url', url },
    };

    if (this.client && this.isConnected) {
      this.client
        .sendFile(rtvi_file, prompt)
        .catch((error) => console.error('URL upload error:', error))
        .then(() => {
          this.addConversationMessage(
            `Referencing URL: ${url}` +
              (prompt ? ` with prompt: ${prompt}` : ''),
            'user',
          );
        });
    }

    this.urlInput.value = '';
    this.filePrompt.value = '';
    this.uploadModal.style.display = 'none';
  }

  handleFileUpload(prompt) {
    const file = this.fileInput.files[0];
    if (!file) {
      alert('Please select a file to upload.');
      return;
    }

    if (this.client && this.isConnected) {
      this.client
        .sendFile(file, prompt)
        .catch((error) => console.error('File upload error:', error))
        .then(() => {
          this.addConversationMessage(
            `Uploaded file: ${file.name}` +
              (prompt ? ` with prompt: ${prompt}` : ''),
            'user',
          );
        });
    }

    this.fileInput.value = '';
    this.filePrompt.value = '';
    this.uploadModal.style.display = 'none';
  }

  async connect() {
    try {
      this.addEvent('connecting', `Using ${this.transportType} transport`);

      // Create transport using config
      const transport = await createTransport(this.transportType);

      // Create client
      this.client = new PipecatClient({
        transport,
        enableMic: true,
        enableCam: false,
        callbacks: {
          onConnected: () => {
            this.onConnected();
          },
          onDisconnected: () => {
            this.onDisconnected();
          },
          onTransportStateChanged: (state) => {
            this.addEvent('transport-state', state);
          },
          onBotReady: () => {
            this.addEvent('bot-ready', 'Bot is ready to talk');
          },
          onUserTranscript: (data) => {
            if (data.final) {
              this.addConversationMessage(data.text, 'user');
            }
          },
          onBotOutput: (data) => {
            if (data.will_be_spoken && data.spoken_status !== 'new') {
              this.highlightSpokenText(data);
              return;
            }
            this.addConversationMessage(data.text, 'bot', data.segment_id);
          },
          onError: (error) => {
            this.addEvent('error', error.message);
          },
        },
      });
      window.client = this.client; // Expose client for debugging

      // Setup audio
      this.setupAudio();

      // Start bot and connect using config
      const connectParams = TRANSPORT_CONFIG[this.transportType];
      if (this.transportType === 'websocket') {
        // WebSocket connects in two steps: start the bot to obtain the
        // WebSocket URL (and optional token), then connect to it.
        const { wsUrl, token } = await this.client.startBot(connectParams);
        await this.client.connect({
          wsUrl: token ? `${wsUrl}?token=${encodeURIComponent(token)}` : wsUrl,
        });
      } else {
        await this.client.startBotAndConnect(connectParams);
      }
    } catch (error) {
      this.addEvent('error', error.message);
      console.error('Connection error:', error);
    }
  }

  async disconnect() {
    if (this.client) {
      await this.client.disconnect();
    }
  }

  setupAudio() {
    this.client.on(RTVIEvent.TrackStarted, (track, participant) => {
      if (!participant?.local && track.kind === 'audio') {
        this.addEvent('track-started', 'Bot audio track');
        const audio = document.createElement('audio');
        audio.autoplay = true;
        audio.srcObject = new MediaStream([track]);
        document.body.appendChild(audio);
      }
    });
  }

  onConnected() {
    this.isConnected = true;
    this.connectBtn.textContent = 'Disconnect';
    this.connectBtn.classList.add('disconnect');
    this.micBtn.disabled = false;
    this.transportSelect.disabled = true;
    this.updateMicButton(this.client.isMicEnabled);
    this.addEvent('connected', 'Successfully connected to bot');

    // Clear placeholder
    if (this.conversationLog.querySelector('.placeholder')) {
      this.conversationLog.innerHTML = '';
    }
  }

  onDisconnected() {
    this.isConnected = false;
    this.connectBtn.textContent = 'Connect';
    this.connectBtn.classList.remove('disconnect');
    this.micBtn.disabled = true;
    this.transportSelect.disabled = false;
    this.updateMicButton(false);
    this.addEvent('disconnected', 'Disconnected from bot');
  }

  updateMicButton(enabled) {
    this.micStatus.textContent = enabled ? 'Mic is On' : 'Mic is Off';
    this.micBtn.style.backgroundColor = enabled ? '#10b981' : '#1f2937';
  }

  highlightSpokenText(data) {
    const curSpan = this.botSpans[data.segment_id];
    if (!curSpan) return;
    const accumulatedText = data.spoken_progress.accumulated_text.replace(
      /\n/g,
      ' <br> ',
    );
    const remainingText = data.spoken_progress.remaining_text.replace(
      /\n/g,
      ' <br> ',
    );
    curSpan.innerHTML = `<strong>${accumulatedText}</strong>${remainingText}`;
    this.conversationLog.scrollTop = this.conversationLog.scrollHeight;
  }

  addConversationMessage(text, role, segmentId) {
    if (role === 'placeholder') {
      const messageDiv = document.createElement('div');
      messageDiv.className = 'conversation-message placeholder';
      messageDiv.textContent = text;
      this.conversationLog.appendChild(messageDiv);
      this.conversationLog.scrollTop = this.conversationLog.scrollHeight;
      return;
    }

    // Append bot segments to the current bubble; start a new bubble on role change
    if (this.lastConversationBubble?.role === role && role === 'bot') {
      const textSpan = document.createElement('span');
      textSpan.innerHTML = text.replace(/\n/g, ' <br> ');
      if (segmentId) this.botSpans[segmentId] = textSpan;
      this.lastConversationBubble.appendChild(document.createTextNode(' '));
      this.lastConversationBubble.appendChild(textSpan);
      this.conversationLog.scrollTop = this.conversationLog.scrollHeight;
      return;
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `conversation-message ${role}`;
    messageDiv.role = role;
    this.lastConversationBubble = messageDiv;

    const roleLabel = document.createElement('div');
    roleLabel.className = 'role';
    roleLabel.textContent = role === 'user' ? 'You' : 'Bot';
    messageDiv.appendChild(roleLabel);

    if (role === 'bot') {
      const textSpan = document.createElement('span');
      textSpan.innerHTML = text.replace(/\n/g, ' <br> ');
      if (segmentId) this.botSpans[segmentId] = textSpan;
      messageDiv.appendChild(textSpan);
    } else {
      const textDiv = document.createElement('div');
      textDiv.textContent = text;
      messageDiv.appendChild(textDiv);
    }

    this.conversationLog.appendChild(messageDiv);
    this.conversationLog.scrollTop = this.conversationLog.scrollHeight;
  }

  addEvent(eventName, data) {
    const eventDiv = document.createElement('div');
    eventDiv.className = 'event-entry';

    const timestamp = new Date().toLocaleTimeString();
    const timestampSpan = document.createElement('span');
    timestampSpan.className = 'timestamp';
    timestampSpan.textContent = timestamp;

    const nameSpan = document.createElement('span');
    nameSpan.className = 'event-name';
    nameSpan.textContent = eventName;

    const dataSpan = document.createElement('span');
    dataSpan.className = 'event-data';
    dataSpan.textContent =
      typeof data === 'string' ? data : JSON.stringify(data);

    eventDiv.appendChild(timestampSpan);
    eventDiv.appendChild(nameSpan);
    eventDiv.appendChild(dataSpan);

    this.eventsLog.appendChild(eventDiv);
    this.eventsLog.scrollTop = this.eventsLog.scrollHeight;
  }
}

// Initialize when DOM is loaded
window.addEventListener('DOMContentLoaded', () => {
  new VoiceChatClient();
});
