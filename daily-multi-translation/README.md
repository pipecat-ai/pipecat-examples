# Daily Multi Translation

This example shows how to use Daily to stream several live translations over a single transport. Daily provides custom tracks, and the bot sends each translation to its own track. Each listener picks the track they want to hear.

The demo translates between Swahili and English, one direction per session:

| `source`       | The bot hears | The bot speaks (one track each) |
| -------------- | ------------- | ------------------------------- |
| `sw` (default) | Swahili       | `english`, `french`, `german`   |
| `en`           | English       | `swahili`                       |

Speech-to-text is Deepgram Nova-3 in both directions. English, French and German speech is Deepgram Aura-2. Deepgram has no Swahili voice, so the Swahili track uses Google Gemini TTS.

<img src="image.png" width="420px">

## Get started

Create your virtual environment and install dependencies:

```bash
uv sync
```

Set up environment variables:

```bash
cp env.example .env # and add your credentials
```

## Run the bot

Start your bot using the DailyTransport:

```bash
uv run bot.py -t daily
```

Then, visit `http://localhost:7860/` in your browser and connect. This puts you in a Daily room with the bot, where you will speak in Swahili (make sure you are not muted).

To translate the other way, set `SOURCE_LANGUAGE=en` in `.env` and restart the bot. When you start a session through `/start` (for example on Pipecat Cloud), you can pick the direction per session in the request body instead:

```json
{ "createDailyRoom": true, "body": { "source": "en" } }
```

## Open client

Next, you need to open the client that will listen to the translations.

```bash
open index.html
```

Once the client is opened, copy the URL of the Daily room created above and join it. You should be able to select which translation you want to hear. The `original` button plays the speaker's own audio.

## Run the evals

The example ships with two audio evals, one per direction. Each one sends real audio into the bot, lets the bot speak, transcribes what the bot said with Deepgram, and asks a judge (OpenAI `gpt-4.1`) if the translation is right.

```bash
PYTHONPATH=evals uv run pipecat eval suite evals/manifest.yaml
```

The suite starts a fresh bot for each scenario, so nothing needs to be running first. Logs and recordings land in `evals/test-runs/<timestamp>/`. Listen to the recordings: a pass tells you the words came out, not how the voice sounds.

- `evals/scenarios/sw_to_en.yaml` plays two Swahili recordings from `evals/assets/`. The harness's built-in voice has no Swahili, so the turns use recordings.
- `evals/scenarios/en_to_sw.yaml` speaks English with the harness's local voice and checks the bot's Swahili speech.

The Swahili recordings were made with Google Gemini TTS. They are cleaner than a real speaker, so a pass shows the path works. It does not measure accuracy on real speech. Swap in your own recordings to test that.

## Things to know

- **One direction per session.** Deepgram's Swahili model hears one language, so the bot cannot follow a speaker who switches between Swahili and English. A two-way meeting needs one bot per direction, each listening only to the speakers of its language.
- **Swahili accuracy.** Swahili is new in Nova-3. Deepgram reports about a 30% word error rate for streaming Swahili, and much worse on numbers, dates and IDs. Expect mistakes on real speech.
- **No `Finalize` for Swahili.** `bot.py` uses a small `DeepgramSTTService` subclass for Swahili that does not send Deepgram's `Finalize` message when the speaker stops. The Swahili model answers a late `Finalize` with a made-up word for the trailing silence, which the bot would then translate and speak.
- **No interruptions.** The translation branches turn interruptions off. An interpreter keeps going while the speaker talks, so a new sentence must not cut off the translation of the last one.

## Build and test the Docker image

```
docker build -t daily-multi-translation .
docker run --env-file .env -p 7860:7860 daily-multi-translation
```
