import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js';
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport';

// Swap these for your own assets in client/ if you want.
const SUCCESS_GIF = 'https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExa3F3ZXhkNTN6M3lmN25ibWR3amF1cGI0b2Z0ZGE5NHV0YmpndGVteSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/0E5zvkDsBo2kyfx9DT/giphy.gif';
const FAILURE_GIF = 'https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExNjByYjhkYWFpYW00eHpkNGVvZGo0Y3pyN3M5YzVlMHlucjdmbDRrbyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/26ybwvTX4DTkwst6U/giphy.gif';

const tabs = document.querySelectorAll('.tab');
const phonePane = document.getElementById('phone-pane');
const browserPane = document.getElementById('browser-pane');
const form = document.getElementById('call-form');
const phoneInput = document.getElementById('phone-input');
const callBtn = document.getElementById('call-btn');
const resultEl = document.getElementById('result');
const resultGif = document.getElementById('result-gif');
const resultText = document.getElementById('result-text');
const logEl = document.getElementById('log');

let pcClient = null;

function log(msg) {
  console.log(msg);
  logEl.textContent += `${new Date().toLocaleTimeString()}  ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function showResult(success) {
  resultEl.classList.remove('hidden');
  resultGif.src = success ? SUCCESS_GIF : FAILURE_GIF;
  resultText.textContent = success ? 'Verified!' : 'Verification failed.';
}

function setMode(mode) {
  tabs.forEach((t) => t.classList.toggle('active', t.dataset.mode === mode));
  phonePane.classList.toggle('hidden', mode !== 'phone');
  browserPane.classList.toggle('hidden', mode !== 'browser');
  resultEl.classList.add('hidden');
}

tabs.forEach((t) => t.addEventListener('click', () => setMode(t.dataset.mode)));

// --- SSE: always listen, both modes ---------------------------------------

const sse = new EventSource('/events');
sse.onmessage = (ev) => {
  try {
    const data = JSON.parse(ev.data);
    if (data.type === 'verification_result') {
      log(`SSE result: ${data.success ? 'success' : 'failure'}`);
      showResult(data.success);
    }
  } catch (e) {
    log(`SSE parse error: ${e}`);
  }
};
sse.onerror = () => log('SSE error (will retry)');

// --- Browser (WebRTC) mode ------------------------------------------------

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (pcClient) {
    await disconnect();
    return;
  }
  const phone = toE164(phoneInput.value);
  phoneInput.value = phone;
  await connect(phone);
});

function toE164(raw) {
  const trimmed = (raw || '').trim();
  if (trimmed.startsWith('+')) {
    return '+' + trimmed.slice(1).replace(/\D/g, '');
  }
  const digits = trimmed.replace(/\D/g, '');
  if (digits.length === 11 && digits.startsWith('1')) return '+' + digits;
  return '+1' + digits;
}

async function connect(phone) {
  resultEl.classList.add('hidden');
  callBtn.disabled = true;
  callBtn.textContent = 'Connecting…';
  log(`Connecting WebRTC for ${phone}`);

  const transport = new SmallWebRTCTransport();

  pcClient = new PipecatClient({
    transport,
    enableMic: true,
    enableCam: false,
    callbacks: {
      onConnected: () => {
        log('Connected to bot');
        callBtn.disabled = false;
        callBtn.textContent = 'Hang up';
        callBtn.classList.add('in-call');
      },
      onDisconnected: () => {
        log('Disconnected');
        cleanup();
      },
      onBotReady: () => log('Bot ready'),
      onBotTranscript: (d) => log(`Bot: ${d.text}`),
      onUserTranscript: (d) => {
        if (d.final) log(`You: ${d.text}`);
      },
      onServerMessage: (msg) => {
        log(`Server message: ${JSON.stringify(msg)}`);
        if (msg?.type === 'verification_result') {
          showResult(!!msg.success);
        }
      },
      onError: (err) => log(`Error: ${err.message || err}`),
    },
  });

  pcClient.on(RTVIEvent.TrackStarted, (track, participant) => {
    if (!participant?.local && track.kind === 'audio') {
      const audio = document.createElement('audio');
      audio.autoplay = true;
      audio.srcObject = new MediaStream([track]);
      document.body.appendChild(audio);
    }
  });

  try {
    // Route through the runner's /start endpoint so the phone number lands on
    // runner_args.body. Posting directly to /api/offer loses it because the
    // runner's FastAPI dataclass parser only reads request_data (snake_case)
    // while the SDK sends requestData (camelCase); the /sessions/{id}/api/offer
    // proxy that /start hands us handles both.
    await pcClient.startBotAndConnect({
      endpoint: '/start',
      requestData: {
        transport: 'webrtc',
        body: { phone_number: phone },
      },
    });
  } catch (err) {
    log(`Connect failed: ${err.message || err}`);
    cleanup();
  }
}

async function disconnect() {
  if (pcClient) {
    try {
      await pcClient.disconnect();
    } catch {}
  }
  cleanup();
}

function cleanup() {
  pcClient = null;
  callBtn.disabled = false;
  callBtn.textContent = 'Call';
  callBtn.classList.remove('in-call');
  document.querySelectorAll('body > audio').forEach((a) => a.remove());
}
