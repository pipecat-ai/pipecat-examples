# Wiring the voice into a Pipecat bot

Three situations, in order of how often they come up. Every shell block
starts by setting `SKILL` (this skill's directory) and `SCRIPT`; keep that
line in each Bash call, since shell variables do not persist between calls.

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
```

## 1. No `server/bot.py` yet: copy the template

The skill bundles a Pipecat quickstart in `assets/server/`, already wired for
this demo:

| File | What it is |
|---|---|
| `bot.py` | Cascade pipeline: Gradium speech-to-text → LLM → Gradium text-to-speech, over WebRTC. Constants near the top: `LLM_PROVIDER`, `GRADIUM_VOICE_ID`, `GRADIUM_LANGUAGE`, `PERSONA`. Checks its keys and the voice id at startup. |
| `pyproject.toml` | `pipecat-ai[anthropic,google,gradium,openai,runner,silero,webrtc]` and the dev tools. All three LLM extras, so switching provider is one constant, no re-sync. |
| `Dockerfile`, `pcc-deploy.toml` | For Pipecat Cloud later; unused locally |

The project's one example env file is `env.example` at the root, copied from
`assets/env.example`; there is deliberately no second copy under `server/`.

It is the output of `pipecat init … --stt gradium_stt --tts gradium_tts` with
the LLM block replaced by a `build_llm()` that picks the provider from
`LLM_PROVIDER`, so it matches what the Pipecat CLI would scaffold. It is used
instead of running `pipecat init .` because that command refuses to run when
a `server/` directory already exists, even an empty one.

Copy it without overwriting anything that is already there:

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
mkdir -p server
for f in bot.py pyproject.toml Dockerfile pcc-deploy.toml; do
  [ -e "server/$f" ] && echo "kept existing server/$f" || cp "$SKILL/assets/server/$f" server/
done
[ -e env.example ] || cp "$SKILL/assets/env.example" env.example
```

(`cp -n` would exit 1 on macOS as soon as one target exists, even though it
copies the others, and Claude Code reads a non-zero exit as a failure.)

### The LLM

`bot.py` supports three providers. Each one runs on its small, low-latency
model, the right size for a real-time voice conversation; a bigger model adds
seconds of silence before every reply.

| `LLM_PROVIDER` | Model | Key in `.env` | Where the key comes from |
|---|---|---|---|
| `openai` (default) | `gpt-5.6-luna` | `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> |
| `gemini` | `gemini-3.5-flash-lite` | `GOOGLE_API_KEY` | <https://aistudio.google.com/apikey> |
| `anthropic` | `claude-haiku-4-5` | `ANTHROPIC_API_KEY` | <https://console.anthropic.com/settings/keys> |

`LLM_MODEL` in `.env` overrides the model within the chosen provider. The
skill sets `LLM_PROVIDER` with `apply --llm` (section 2) from the answer the
user gave, and `env` (section 4) checks the matching key.

If the user would rather scaffold with the Pipecat CLI (a different
transport, a different STT), the command is:

```bash
TMP=$(mktemp -d)
uvx --from "pipecat-ai[cli]" pipecat init "$TMP/scaffold" --name "$(basename "$PWD")" \
  --no-context-hub --bot-type web -t smallwebrtc -m cascade \
  --stt gradium_stt --llm openai_llm --tts gradium_tts
for f in "$TMP/scaffold/server/"*; do
  [ -e "server/$(basename "$f")" ] || cp "$f" server/
done; rm -rf "$TMP"
```

That output reads the voice from `os.getenv("GRADIUM_VOICE_ID")` and has no
`LLM_PROVIDER`; apply the edits in section 3 to it.

## 2. Write the voice id, persona and provider

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" apply --session voices/<slug> --bot server/bot.py \
  --persona "You are Fionn, the support agent for Northgate IT." --llm openai
```

`apply` finds the `GRADIUM_VOICE_ID = "…"` line, replaces the comment block
above it with the voice's name and brief, and writes the kept `voice_id`. It
also sets `GRADIUM_LANGUAGE` from the session's language, so the
speech-to-text listens in the language the voice was designed for; with
`--persona` it rewrites the `PERSONA = "…"` line the system prompt starts
with; and with `--llm` it rewrites `LLM_PROVIDER`. It checks that the result
still compiles before writing, prints the before and after, and records the
persona and provider in `session.json` so the `client` command can reuse
them. Run it again after designing another voice and it replaces the previous
one. It refuses candidate ids (`vox_emb_…`), which expire.

Always pass a persona for the template bot. Its system prompt is generic
otherwise, and the model then answers "who are you?" with its own name, which
is the first thing the user hears. A name plus the role the voice was
designed for is enough; the rest of the system prompt (spoken-aloud, brief)
stays as it is.

Without `--session`, pass `--voice-id`, `--name`, `--brief` and `--language`
yourself, for a voice the user already has. On a `409` from `keep`, the
`detail` line names the voice that already exists for that candidate; this is
how to wire it in.

If `apply` exits with "No GRADIUM_VOICE_ID constant", the bot is not built
from the template; go to section 3. If it notes "no LLM_PROVIDER constant",
the bot keeps whatever LLM it already has.

## 3. Existing `bot.py` that is not from the template

Read the file first. Then:

**It already uses `GradiumTTSService`.** Add the constants near the top, after
`load_dotenv()`, and point the services at them:

```python
# The Gradium voice this bot speaks with, designed with the design-voice skill.
# Voice "Receptionist EN": A British female voice, 20 to 30, glossy and confident…
GRADIUM_VOICE_ID = "aBcD1234EfGh5678"  # the id `keep` printed
GRADIUM_LANGUAGE = "en"
```

```python
from pipecat.transcriptions.language import Language

stt = GradiumSTTService(
    api_key=os.getenv("GRADIUM_API_KEY"),
    settings=GradiumSTTService.Settings(language=Language(GRADIUM_LANGUAGE)),
)
tts = GradiumTTSService(
    api_key=os.getenv("GRADIUM_API_KEY"),
    settings=GradiumTTSService.Settings(voice=GRADIUM_VOICE_ID),
)
```

Once the constants are there, `apply` works on this file too. If it read the
voice from `os.getenv("GRADIUM_VOICE_ID")`, drop that and remove the
`GRADIUM_VOICE_ID=` line from `.env` and from the example file: with
`load_dotenv(override=True)` an empty line sets the variable to an empty
string, which would win over any default. The speech-to-text language line
only matters if the voice is not English; Gradium STT defaults to English.

**It uses another TTS service** (Cartesia, ElevenLabs, Deepgram…). Swap the
service and leave the LLM and everything else alone:

1. Import: `from pipecat.services.gradium.tts import GradiumTTSService`, and
   remove the old TTS import.
2. Replace the old service construction with the TTS block above. Gradium
   outputs 48 kHz audio and the service tells the pipeline, so no sample-rate
   changes.
3. Add `gradium` to the `pipecat-ai[…]` extras in `pyproject.toml`, and
   `GRADIUM_API_KEY=` to `env.example`. Remove the old provider's key and
   voice lines if nothing else uses them.
4. Tell the user which provider you replaced; do not silently remove a key
   they may still use elsewhere.

**Its LLM is not one of the three.** Leave it. The skill's job is the voice;
only change the LLM when the user asks, and then copy the matching branch of
`build_llm()` from `assets/server/bot.py`.

## 4. Environment

One `.env` file holds the variables below: `server/.env` if it exists,
otherwise `.env` at the project root. `load_dotenv()` in bot.py takes the
nearest file walking up from `server/` and ignores any other, so a variable
that is only in the root file is invisible once `server/.env` exists; keep
everything in one file. The skill's script reads them in the same order.
Pipecat Cloud reads secrets from `server/.env`.

| Variable | Where it comes from |
|---|---|
| `GRADIUM_API_KEY` | Gradium console. The same key the skill used for the audition. |
| `OPENAI_API_KEY`, `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY` | The provider console (table in section 1). Only the one for `LLM_PROVIDER` is needed. |
| `LLM_MODEL` | Optional. Another model from the same provider. |

The `env` command does the bookkeeping. It picks the file the bot reads,
creates it if needed (with `chmod 600`), reads `LLM_PROVIDER` from
`server/bot.py` to know which key is required, and reports each one as set,
set only in the shell, or MISSING. It never prints a value.

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" env --from-env
```

`--from-env` copies required variables that are exported in the shell into
the file, which is what Docker and Pipecat Cloud need. For a key the user
gives you, write it with `--set` (the value never appears in the output):

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" env --set OPENAI_API_KEY=<the key>
```

`env` refuses `--set VAR=` with no value and never writes an empty line: with
`load_dotenv(override=True)`, an empty `VAR=` line overrides a value exported
in the shell with an empty string, so a key that "is set" in the shell goes
missing. It reports that case when it finds one in an existing file. Do not
copy `env.example` to `.env` for the same reason; let `env` build the file.

## 5. Run and check

```bash
cd server
uv sync        # first run only, about a minute
uv run bot.py
```

The template checks the keys and the voice id as it starts, so a missing one
ends the run immediately with a single line naming it. A healthy start prints
the dev-runner banner, `Bot ready!` with the client URL, and `Uvicorn running
on http://localhost:7860`. The bot's own lines (`Starting bot (voice …, LLM
…)`, the service connections) appear in the log when the first client
connects, because the runner only builds the pipeline on Connect.

Then the client: [client.md](client.md). The runner's prebuilt client at
<http://localhost:7860/client/> also works as a fallback.

| Symptom | Fix |
|---|---|
| `Missing required environment variable: …` at startup | `env --set VAR=…` (section 4). |
| `GRADIUM_VOICE_ID is not set in bot.py` at startup | `apply` was not run; run it (section 2). |
| `LLM_PROVIDER is … in bot.py; it must be one of` | A typo in the constant; `apply --llm <provider>` rewrites it. |
| `uv: command not found` | `curl -LsSf https://astral.sh/uv/install.sh \| sh`, reopen the shell. |
| Port 7860 in use | `uv run bot.py --port 7861`, and start the client with `PIPECAT_SERVER_URL=http://localhost:7861 npm run dev`. |
| Bot connects, greets nothing, log shows `401` or `403` from the LLM | The provider key in `.env` is wrong, or the account has no access to the model. |
| Bot connects, greets nothing, log shows `404` or `model not found` | The account cannot use the default model; set `LLM_MODEL=` in `.env` to one it can. |
| Bot connects but no audio, log shows `401` from Gradium | The `GRADIUM_API_KEY` in `.env` is wrong. |
| `Client connected` then silence, no LLM log lines | Check the browser allowed the microphone, then look for a provider error in the log. |
