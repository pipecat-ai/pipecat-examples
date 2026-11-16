# Expressivity

A listen-only demo of how Pipecat reads the way something was said. Play a premade clip or open the
microphone, and see each turn read two ways, both on the CPU beside the bot:

- [Pipecat Voice Reader](https://docs.pipecat.ai/api-reference/server/expressive/pipecat-voice) hears
  the voice: its tone, energy, laughter, pace and how sarcastic the delivery sounds.
- [Pipecat Tone Reader](https://docs.pipecat.ai/api-reference/server/expressive/pipecat-tone) reads the words:
  their emotion and how sarcastic they are.

Deepgram transcribes the speech. There is no LLM or TTS: in a voice agent, the same reading goes to the
LLM with the user's message. See
[Expressive Conversation](https://docs.pipecat.ai/pipecat/features/expressive-conversation).

> Pipecat Voice Reader is an experimental model, in English only. See its
> [model card](https://huggingface.co/pipecat-ai/voice-reader) for its evaluation and limitations.

- `server/`: the Pipecat bot (Pipecat 1.16 or later).
- `client/`: the page (Vite, React 19, Tailwind 4, shadcn, Zustand).

## How it works

```
transport input -> ClipPlayer -> VAD -> user turns -> Deepgram STT -> PerceptionReader -> PerceptionConclusion -> transport output
```

`server/bot.py` is a standard Pipecat pipeline. The reading is one line of it:

```python
reader = PerceptionReader(sources=[PipecatToneSource(), PipecatVoiceSource()])
```

Each time the user stops speaking, the
[`PerceptionReader`](https://docs.pipecat.ai/api-reference/server/expressive/overview#perceptionreader)
has Voice Reader hear that stretch of audio and Tone Reader read its transcription, and sets their
signals on the transcription as one reading:

| Signal          | From         | Reading                                                     |
| --------------- | ------------ | ----------------------------------------------------------- |
| `emotion`       | Tone Reader  | The two likeliest emotions in the words, with confidences   |
| `sarcasm`       | Tone Reader  | The chance the words are sarcastic, from 0 to 1             |
| `tone`          | Voice Reader | The two likeliest tones of voice, with confidences          |
| `arousal`       | Voice Reader | How activated the voice sounds, from 0 to 1                 |
| `laughter`      | Voice Reader | The chance the turn has laughter in it, from 0 to 1         |
| `speech_rate`   | Voice Reader | The speaking rate in syllables per second                   |
| `sarcasm_voice` | Voice Reader | The chance the delivery alone sounds sarcastic, from 0 to 1 |

## Weighing the two readings

Neither model is right alone. The words are the stronger reader of sarcasm, but they read a joke told
through laughter as sarcastic. The voice is the better reader of feeling, since plain words can be said
in any mood, but its sarcasm is a weak cue. `server/conclusion.py` weighs the two into one conclusion,
and adds it to the same reading as two more signals:

| Signal            | Reading                                                                   |
| ----------------- | ------------------------------------------------------------------------- |
| `feeling`         | Positive, neutral, sad or frustrated, with a confidence for the likeliest |
| `sarcasm_overall` | The chance the turn is sarcastic, from 0 to 1                             |

- **Feeling** is 60% the voice's `tone` and 40% the words' `emotion`, with neutral words counted at
  half: they show no strong feeling, which isn't the user feeling none.
- **Sarcasm** is 65% the words' and 35% the voice's. The more the voice laughs, the less the words'
  sarcasm counts. When the words are bright and the voice is flat or frustrated, the voice's sarcasm is
  taken at its word, as that is the sarcasm the words can't show.

On the premade clips, the words alone call both laughing clips sarcastic (0.84). Weighed with the voice
they read 0.06 and 0.18, and the two sarcastic clips still read 0.85 and 0.73.

`conclude()` is a plain function over a reading, and `PerceptionConclusion` is the small processor that
applies it to each transcription. It declares its signals as any perception producer does, so RTVI
sends them to the page with the rest of the reading, and an LLM after it would be told how to read
them. The weights are a starting point, set by hand and checked against these twelve clips only:
measure them on your own calls before relying on them.

## What the page shows

The page gets everything it shows from Pipecat's own RTVI events:

- `user-started-speaking` and `user-stopped-speaking`: the turn, which starts and stops with the VAD.
- `user-input`: the turn's words, with the reading as its `perception`. The reader goes right after the
  STT service, which is what has RTVI send the two together.
- `metrics`: how long each model's read took, as its classifier's processing time.

Besides the conclusion, the demo's one processor of its own is the `ClipPlayer` (`server/clips.py`). It plays a clip into the
pipeline just after the transport's input, in real time, as the user's audio, so a clip takes the same
road as the microphone. The same audio is sent out through the transport, so you hear it. The
microphone isn't heard while a clip plays. The clips in `server/clips/` are synthetic speech, listed in
`manifest.json`: six moods in two voices.

Each model has a card: its likeliest label as the headline, its two likeliest as panels, and a gauge
for each of its other signals. A badge says `sarcastic` when the model's sarcasm is a half or more, and
`sincere` under that. Under the two cards is the conclusion: the turn's overall feeling and sarcasm.
Voice Reader doesn't read speech shorter than 0.8 seconds; its card then says so, and the conclusion is
made from the words alone.

### Effects

The page makes heavy use of GPU effects, for fun: a path-traced glass pill, wisps of light flowing from
it into the cards, and glass cards. None of it is needed to read a turn. **Effects** in the header turns
them all off, leaving a plain circle and plain cards, for a device that struggles with them. The choice
is remembered, and they start off in a browser without WebGL 2.

To open the page with them off, add `?effects=off` to its address:
`http://localhost:5173/?effects=off`.

## Run it locally

You'll need two terminals.

### The bot

```bash
cd server
uv sync
cp env.example .env
```

Add your Deepgram key to `.env` as `DEEPGRAM_API_KEY`, then:

```bash
uv run bot.py
```

The first session downloads the two models from Hugging Face.

### The page

```bash
cd client
npm install
cp env.example .env.local
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). **Play** runs through the clips in order, and stops
if pressed again. **Mic** opens the microphone. Either one starts a session first if there isn't one.

Locally the two talk over SmallWebRTC, which needs no Daily account: `VITE_TRANSPORT=smallwebrtc` in
`.env.local`, and Vite proxies `/api` to the bot's runner on port 7860 (`BOT_URL`).

## Deploy to Pipecat Cloud

`server/pcc-deploy.toml` and `server/Dockerfile` deploy the bot, with both models downloaded into the
image and Krisp's voice isolation on the microphone. Follow the
[quickstart instructions](https://docs.pipecat.ai/pipecat/get-started/quickstart), with
`DEEPGRAM_API_KEY` in the secret set.

`client/api/start.ts` starts sessions on Pipecat Cloud for a hosted page, so the public API key stays
on the server. It reads `PIPECAT_CLOUD_AGENT_NAME` and `PIPECAT_CLOUD_PUBLIC_KEY`. Put the same two in
`.env.local`, with `VITE_TRANSPORT` left out, to run the local page against the deployed bot.
