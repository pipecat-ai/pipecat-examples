import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js';
import {
  AVAILABLE_TRANSPORTS,
  DEFAULT_TRANSPORT,
  TRANSPORT_CONFIG,
  createTransport,
} from './config';

import hljs from 'highlight.js/lib/core';
import 'highlight.js/styles/dark.css';
import javascript from 'highlight.js/lib/languages/javascript';
import python from 'highlight.js/lib/languages/python';
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('python', python);

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
    this.lastConversationBubble = null;
    this.botSpans = [];
    this.curBotSpan = -1;
    this.sendBtn = document.getElementById('send-btn');

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
      'placeholder'
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

    const userInput = document.getElementById('user-input');
    const sendTextToLLM = () => {
      if (this.client && this.isConnected) {
        const text = userInput.value.trim();
        const audioResponse = document.getElementById('audio-response').checked;
        if (text.length > 0) {
          this.client.sendText(text, { audio_response: audioResponse });
          this.addConversationMessage(text, 'user');
        }
        userInput.value = '';
      }
    };

    this.sendBtn.addEventListener('click', sendTextToLLM);

    // Also handle Enter key in the input
    userInput.addEventListener('keyup', (e) => {
      if (e.key === 'Enter') {
        sendTextToLLM();
      }
    });
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
            if (data.aggregated_by === 'word') {
              this.emboldenBotWord(data.text);
              return;
            } else {
              this.addConversationMessage(data.text, 'bot', data.aggregated_by);
            }
          },
          onError: (error) => {
            this.addEvent('error', error.message);
          },
        },
      });
      window.client = this; // For debugging

      // Setup audio
      this.setupAudio();

      // Connect using config
      const connectParams = TRANSPORT_CONFIG[this.transportType];
      await this.client.connect(connectParams);
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
    this.sendBtn.disabled = false;
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
    this.sendBtn.disabled = true;
    this.transportSelect.disabled = false;
    this.updateMicButton(false);
    this.addEvent('disconnected', 'Disconnected from bot');
  }

  updateMicButton(enabled) {
    this.micStatus.textContent = enabled ? 'Mic is On' : 'Mic is Off';
    this.micBtn.style.backgroundColor = enabled ? '#10b981' : '#1f2937';
  }

  emboldenBotWord(word) {
    if (this.curBotSpan < 0) return;
    const curSpan = this.botSpans[this.curBotSpan];
    if (!curSpan) return;
    const spanInnards = curSpan.innerHTML.replace(/<\/?strong>/g, '');
    const alreadyEmboldened = spanInnards.slice(0, this.lastBotWordIndex);
    const yetToEmbolden = spanInnards.slice(this.lastBotWordIndex || 0);

    const wordIndex = yetToEmbolden.indexOf(word);
    if (wordIndex === -1) {
      if (this.botSpans.length > this.curBotSpan + 1) {
        curSpan.innerHTML = spanInnards;
        curSpan.classList.add('spoken');

        // Move to next bubble
        this.curBotSpan = this.curBotSpan + 1;
        this.lastBotWordIndex = 0;
        this.emboldenBotWord(word);
        return;
      }
      return;
    }
    // Replace the first occurrence of the word with <strong>word</strong>
    // Use word boundaries to match the whole word
    const replaced = yetToEmbolden.replace(word, `${word}</strong>`);

    curSpan.innerHTML = '<strong>' + alreadyEmboldened + replaced;
    this.conversationLog.scrollTop = this.conversationLog.scrollHeight;

    // Update lastBotWordIndex
    this.lastBotWordIndex =
      (this.lastBotWordIndex || 0) + wordIndex + word.length;
  }

  createBotBubbleElement(text, type) {
    let newElement;
    switch (type) {
      case 'code':
        {
          newElement = document.createElement('pre');
          const codeDiv = document.createElement('code');
          codeDiv.textContent = text;
          hljs.highlightElement(codeDiv);
          newElement.appendChild(codeDiv);
        }
        break;
      case 'link':
        {
          newElement = document.createElement('div');
          const link = document.createElement('a');
          link.href = text;
          link.textContent = text;
          link.target = '_blank';
          newElement.appendChild(link);
        }
        break;
      default:
        {
          newElement = document.createElement('span');
          text = text.trim();
          newElement.innerHTML = text.replace(/\n/g, ' <br> ');
          this.botSpans.push(newElement);
          if (this.curBotSpan === -1) {
            this.curBotSpan = 0;
          }
        }
        break;
    }
    newElement.type = type;
    return newElement;
  }

  addToLastBubble(text, role, type) {
    const appendText = (element, text) => {
      text = text.trim();
      element.innerHTML += ' ' + text.replace(/\n/g, ' <br> ');
    };
    const typeIsText = (t) => {
      return !['code', 'link'].includes(t);
    };

    if (role === 'user') {
      appendText(this.lastConversationBubble, text);
      return;
    }

    const lastChild = this.lastConversationBubble.lastChild;
    if (lastChild && typeIsText(lastChild.type) && typeIsText(type)) {
      appendText(lastChild, text);
      return;
    }
    this.lastConversationBubble.appendChild(
      this.createBotBubbleElement(text, type)
    );
  }

  addConversationMessage(text, role, type = 'sentence') {
    // Only start a new bubble if the role changes
    if (this.lastConversationBubble?.role === role) {
      this.addToLastBubble(text, role, type);
    } else {
      this.createConversationBubble(text, role, type);
    }
  }

  createConversationBubble(text, role, type) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `conversation-message ${role} ${type}`;
    this.lastConversationBubble = messageDiv;
    this.lastConversationBubble.role = role;

    if (role === 'placeholder') {
      messageDiv.textContent = text;
    } else {
      this.addToLastBubble(text, role, type);
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
