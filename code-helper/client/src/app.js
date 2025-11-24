import {
  AggregationType,
  PipecatClient,
  RTVIEvent,
} from '@pipecat-ai/client-js';
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
    // Listen and log transport state changes
    this.transportSelect.addEventListener('change', (e) => {
      this.transportType = e.target.value;
      this.addEvent('transport-changed', this.transportType);
    });

    // Setup connect button for connecting/disconnecting
    this.connectBtn.addEventListener('click', () => {
      if (this.isConnected) {
        this.disconnect();
      } else {
        this.connect();
      }
    });

    // Setup mic button for muting/unmuting
    this.micBtn.addEventListener('click', () => {
      if (this.client) {
        const newState = !this.client.isMicEnabled;
        this.client.enableMic(newState);
        this.updateMicButton(newState);
      }
    });

    // Handle sending text input to LLM
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
            // Check the aggregation type. If WORD, embolden the word already rendered
            // in the bot transcript. Otherwise, add to the latest bot message or start
            // a new one.
            if (data.aggregated_by === AggregationType.WORD) {
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
    // Listen for bot audio tracks and play them
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
    // Update UI on connection
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
    // Update UI on disconnection
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
    // Update the microphone button UI based on whether the mic is enabled
    this.micStatus.textContent = enabled ? 'Mic is On' : 'Mic is Off';
    this.micBtn.style.backgroundColor = enabled ? '#10b981' : '#1f2937';
  }

  emboldenBotWord(word) {
    // This method does it's best to find the word provided in the rendered bot
    // transcript and embolden it. It keeps track of which bubble and index
    // it's at to avoid searching from the start each time. It simply looks for
    // the next occurrence of the word in the current bubble and emboldens all the
    // text up to that word. This means it may fail if the word does not
    // match exactly what was rendered (e.g., punctuation, casing, etc), but
    // it's a best effort.
    if (this.curBotSpan < 0) return;
    const curSpan = this.botSpans[this.curBotSpan];
    if (!curSpan) return;
    // Get the inner HTML without <strong> tags
    const spanInnards = curSpan.innerHTML.replace(/<\/?strong>/g, '');
    // Split into already spoken (and emboldened) and yet to be spoken (and emboldened)
    const alreadyEmboldened = spanInnards.slice(0, this.lastBotWordIndex || 0);
    const yetToEmbolden = spanInnards.slice(this.lastBotWordIndex || 0);

    // For the yet to embolden part, find the next occurrence of the word
    const wordIndex = yetToEmbolden.indexOf(word);
    if (wordIndex === -1) {
      // If the word is not found, we may have finished this span
      // move to the next span if available
      if (this.botSpans.length > this.curBotSpan + 1) {
        // Once we complete a span, mark it as spoken. This removes the need
        // for inserting <strong> tags and simplifies the innerHTML.
        curSpan.innerHTML = spanInnards;
        curSpan.classList.add('spoken');

        // Move to next bubble
        this.curBotSpan = this.curBotSpan + 1;
        this.lastBotWordIndex = 0;
        // Try again with the next span
        this.emboldenBotWord(word);
        return;
      }
      return;
    }
    // Replace the first occurrence of the word with word</strong>
    // Use word boundaries to match the whole word
    const replaced = yetToEmbolden.replace(word, `${word}</strong>`);

    // Update the inner HTML so that <strong> wraps all text up until
    // and including the current word
    curSpan.innerHTML = '<strong>' + alreadyEmboldened + replaced;
    // Scroll to bottom
    this.conversationLog.scrollTop = this.conversationLog.scrollHeight;

    // Update lastBotWordIndex
    this.lastBotWordIndex =
      (this.lastBotWordIndex || 0) + wordIndex + word.length;
  }

  // Create a new element to add to the bot bubble based on aggregation type
  createBotBubbleElement(text, type) {
    let newElement;
    switch (type) {
      case 'code':
        {
          // Create a code block with syntax highlighting
          newElement = document.createElement('pre');
          const codeDiv = document.createElement('code');
          codeDiv.textContent = text;
          hljs.highlightElement(codeDiv);
          newElement.appendChild(codeDiv);
        }
        break;
      case 'link':
        {
          // Create a link element
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
          // All other text is rendered in a simple span and new lines are converted to <br>
          newElement = document.createElement('span');
          text = text.trim();
          // We add spaces around the <br> to ensure we don't break our emboldening logic
          newElement.innerHTML = text.replace(/\n/g, ' <br> ');
          this.botSpans.push(newElement);
          if (this.curBotSpan === -1) {
            this.curBotSpan = 0;
          }
        }
        break;
    }
    // Attach the aggregation type for later reference
    newElement.type = type;
    return newElement;
  }

  // Add text to the last bubble, handling different types appropriately
  addToLastBubble(text, role, type) {
    const appendText = (element, text) => {
      text = text.trim();
      element.innerHTML += ' ' + text.replace(/\n/g, ' <br> ');
    };
    const typeIsText = (t) => {
      return !['code', 'link'].includes(t);
    };

    if (role === 'user') {
      // If the role is user, always simply append the text and return.
      // There is no special rendering for user messages.
      appendText(this.lastConversationBubble, text);
      return;
    }

    // For bot messages, if the last element is text and the new type is also text,
    // we can simply append to it.
    const lastChild = this.lastConversationBubble.lastChild;
    if (lastChild && typeIsText(lastChild.type) && typeIsText(type)) {
      appendText(lastChild, text);
      return;
    }
    // If we're here, then the text is part of the bot transcript and either not
    // text or a different type than the last element. Create a new element to add
    // to the bot transcript bubble.
    this.lastConversationBubble.appendChild(
      this.createBotBubbleElement(text, type)
    );
  }

  // Entry point for adding text to the conversation log
  addConversationMessage(text, role, type = AggregationType.SENTENCE) {
    // If the role changes, create a new bubble. Otherwise, add to the last bubble.
    if (this.lastConversationBubble?.role === role) {
      this.addToLastBubble(text, role, type);
    } else {
      this.createConversationBubble(text, role, type);
    }
  }

  // Create a new conversation bubble along with its initial text
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

  // The client UI also has an event log for debugging and observability.
  // The method below adds entries to that log.
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
