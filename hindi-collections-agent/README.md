# Hindi Collections Agent

A loan payment reminder call in Hindi, built with Pipecat. It hears Hindi and English, speaks Hindi, handles a caller who cuts in, and walks a three-step call script.

- **Speech to text:** Deepgram Flux (`flux-general-multi`, Hindi + English). Flux also decides when the caller starts and stops talking.
- **LLM:** OpenAI.
- **Text to speech:** Deepgram Flux TTS, Hindi voice `flux-anjali-hi`.
- **Call script:** Pipecat Flows, written as data in `flow.yaml`.

## What it shows

| Problem | Where to look |
|---|---|
| Turn detection and barge-in | `bot.py` has no VAD and no turn-taking code. `DeepgramFluxSTTService` does it. |
| Keep your own LLM and TTS | Each service is one block in `bot.py`. Swap the `tts = ...` block for `SarvamTTSService` and nothing else changes. |
| Phone and web from one bot | `transport_params` in `bot.py`: browser, Daily dial-in, Exotel. Same pipeline for all. |
| Multi-step calls you can audit | `flow.yaml`: verify, remind, close. The loan amount is not in the prompt until the caller is verified. |
| Proof it works | `evals/`: a spoken test call, recorded. |

## The call

| Step | The bot | Tool | Next |
|---|---|---|---|
| `verify` | Greets and asks for the last four digits of the loan number | `verify_customer` | `remind` if it matches. Asks again if not, and ends the call after three misses. |
| `remind` | States the overdue amount and due date, asks when the caller can pay | `record_promise_to_pay` | `close` |
| `close` | Reads the date back, says goodbye, hangs up | | |

Any step can leave early to `wrap_up`, which ends the call without reading back a promise: the wrong person answered, the caller already paid, or they will not give a date.

The test loan in `handlers.py` ends in **4321**.

## Setup

```bash
uv sync
cp env.example .env   # then add your keys
```

## Run it

**In the browser**

```bash
uv run bot.py
```

Open http://localhost:7860/client and click Connect.

**Phone dial-in with Daily**

```bash
uv run bot.py -t daily
ngrok http 7860
```

Point your Daily phone number's `room_creation_api` at `https://<your-ngrok-url>/daily-dialin-webhook`, then call the number. Full steps: https://docs.pipecat.ai/pipecat/telephony/daily-pstn

**Phone dial-in with Exotel**

```bash
uv run bot.py -t exotel --proxy <your-ngrok-host>
```

Set the Voicebot applet URL to `wss://<your-ngrok-host>/ws`. Full steps: https://docs.pipecat.ai/pipecat/telephony/exotel-websockets

**Ozonetel**

Pipecat has no Ozonetel WebSocket serializer at this time. We recommend a SIP trunk: point your Ozonetel SIP trunk at a Daily SIP trunk and calls reach this bot over the `daily` transport, with no bot changes. https://docs.daily.co/docs/guides/features/dial-in-dial-out/sip-trunk

## The eval

`evals/scenarios/collections_call.yaml` holds three spoken test calls. Every model in the test is in the cloud:

| Part of the test | Model |
|---|---|
| The caller's voice | Deepgram Flux TTS (`flux-arjun-hi`, `flux-cole-en`) |
| Transcribing what the bot said | Deepgram Nova-3, Hindi |
| Judging the bot's replies | OpenAI `gpt-4.1`, or a plain text check |

The harness speaks the caller's lines out loud, so the bot's real speech to text and turn detection run. `eval_services.py` builds the services the test uses.

| Scenario | What it checks |
|---|---|
| `verify_remind_close` | A full call in Hindi. All three steps in order, both tool calls, and a barge-in: the caller cuts in two seconds into the reminder, and the bot must stop talking within three seconds and answer. |
| `english_caller` | The caller gives the loan digits in English. The bot understands, moves to `remind`, and keeps speaking Hindi. |
| `already_paid` | The caller says they already paid. The call leaves through `wrap_up` and no promise is recorded. |

Run them all:


```bash
uv run pipecat eval suite evals/manifest.yaml
```

A run takes about a minute and needs the same two API keys as the bot. Logs and recordings land in `evals/runs/<timestamp>/`.

Some checks use a plain text check in place of the LLM judge, because the judge misread correct Hindi replies in testing.

A finished run is in `evals/sample-run/`. Play the `.wav` files to hear the calls. The `.eval.log` files show each event with its time: search for `bot_interrupted` to see the barge-in, and `flow_node` to see each step.

## Deploy to Pipecat Cloud

`pcc-deploy.toml` targets the Mumbai region (`ap-south`).

```bash
pipecat cloud secrets set hindi-collections-agent --file .env --region ap-south
pipecat cloud deploy
```

For Exotel, the Voicebot applet URL becomes:

```
wss://ap-south.api.pipecat.daily.co/ws/exotel?serviceHost=hindi-collections-agent.<your-org-id>
```

Agents run, and their logs are stored, in the region you pick. Account and session records are stored in the US. If every record must stay in India, Pipecat Enterprise runs the same bot in your own Kubernetes cluster: https://docs.pipecat.ai/pipecat-cloud/enterprise/overview

## Good to know

- **The bot always speaks Hindi.** It understands Hindi, English, and a mix. To change the voice, pick another `flux-<name>-hi` voice from https://developers.deepgram.com/docs/flux-tts/voices, or swap the block for `SarvamTTSService`.
- **Other Indian languages.** Flux multilingual covers Hindi and English. Flux multilingual does not list other Indian languages. For those, use another Pipecat STT service with Pipecat's own turn detection.
- **The loan data is fake.** `handlers.py` is where your loan system and collections system plug in.
