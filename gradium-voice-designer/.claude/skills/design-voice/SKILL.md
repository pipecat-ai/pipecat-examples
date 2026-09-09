---
name: design-voice
description: Design a custom Gradium voice for a Pipecat bot by auditioning three takes, then build the demo around it. Drafts the voice description from a reference image in the project root when there is one, otherwise from a few questions, and shows it for approval; then generates three takes, keeps the one the user picks as a permanent voice_id, wires it into server/bot.py with their choice of OpenAI, Gemini or Anthropic, and scaffolds a web client that shows the image. Use it whenever the user wants to create, design, audition or pick a Gradium voice, wants a new or custom voice for a bot or agent without naming another TTS provider, mentions Gradium voices or voice design, drops an image in and wants a voice for it, or says they want the bot to sound a certain way, even if they never say "design" or "audition". Not for switching between another provider's preset voices.
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion
---

# design-voice

Take the user from "I want a voice that sounds like…" (or a picture of the
character) to a Pipecat bot that speaks with it, and a web client to talk to
it. Gradium voice design samples a brand-new voice from a written
description, so the flow is: describe, approve, hear three takes, keep one,
wire it in, build the client.

The API calls live in `scripts/audition.py` in this skill's directory. It is
standard library only (Python 3.9 or newer), so run it with plain `python3`.
Your job is the conversation around it: turn what the user wants (or what
the image shows) into a good description, get it approved, play the takes,
ask which one they like, and put the result into `server/bot.py` and
`client/`.

Every shell block below starts with the same line, which sets `SKILL` to this
skill's directory and `SCRIPT` to the script. Keep that line in each Bash call
you make; shell variables do not carry over between calls. Run everything
from the project root, the directory that holds (or will hold) `server/` and
`client/`, and never `cd` in a Bash call: the working directory does carry
over, so it would break every later command.

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
```

## Before you start

**Git.** First, so that no key is ever written to a tracked file: make sure
`.env`, `node_modules` and the audition audio are ignored. The bundled
`assets/gitignore` is used when the project has none; otherwise the patterns
are appended if missing:

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
if [ -f .gitignore ]; then
  [ -z "$(tail -c1 .gitignore)" ] || echo >> .gitignore
  for p in '.env' '.venv/' '__pycache__/' 'node_modules/' 'dist/' '.DS_Store' 'voices/**/*.wav'; do
    grep -qxF "$p" .gitignore || echo "$p" >> .gitignore
  done
else
  cp "$SKILL/assets/gitignore" .gitignore
fi
```

(The `tail -c1` line: a file whose last line has no newline would otherwise
get `.env` glued onto it, and the key would stay committable.)

**API key.** The script reads `GRADIUM_API_KEY` from the environment, then
from `server/.env`, then from `.env` at the project root. Check once:

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" env
```

It prints the file the bot reads and `GRADIUM_API_KEY: set` or `MISSING`
(and the LLM key line, which you can ignore until Step 4). If the key is
missing, ask the user for one from the Gradium console and write it with
`env --set GRADIUM_API_KEY=<key>`; the value never appears in the output.
The key never goes into `bot.py`, into chat output, or into a commit. Do not
echo it back to confirm it; say that it is set.

**Audio.** The `play` command finds a player on its own (`afplay` on macOS,
then `paplay`, `aplay`, `ffplay`, `mpv`). Nothing to set up.

**Node**, for the client in Step 5: `node --version` should print v20.19 or
newer (v22.12 or newer on the 22 line). If it is missing, carry on with
everything else and say at the end that the client needs Node
(<https://nodejs.org>) before `npm install`.

## Step 1: Find out what voice they want

### 1a. Look for a reference image

The user can drop a picture of the character into the project root instead
of describing the voice. Look for one first (newest first; prints nothing
when there is none; `find` rather than a glob, because zsh aborts
`ls *.png *.jpg` as soon as one pattern has no match, and `-r` because GNU
`xargs` would otherwise run `ls` with no arguments and list the whole folder):

```bash
find . -maxdepth 1 -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) -print0 | xargs -0r ls -t 2>/dev/null
```

- **None**: go to 1b.
- **One**: open it with the Read tool, which shows you the picture, and read
  the "From a reference image" section of
  [references/writing-descriptions.md](references/writing-descriptions.md).
  Take the voice's attributes from what you see, a working name (the file
  name is often the character's name: `declan.png`) and a persona line for
  the bot ("You are Declan, the innkeeper at the Crossroads Inn."); the brief
  itself is written in 1d. Tell the user in one line that you are working
  from that image.
- **Several**: ask which one, with AskUserQuestion, newest first.

If the user also described the voice in words, the words win where they
disagree with the picture; the picture fills the gaps.

### 1b. Ask (no image)

If the request already describes the voice ("a gruff pirate for our game",
"calm Irish woman for a support line"), do not ask again; go straight to the
brief. Otherwise ask, with AskUserQuestion when it is available and in plain
text when it is not. One call, three short questions plus the LLM question
below:

1. **What is the voice for?** Offer archetypes as options and let them type
   their own: a friendly receptionist (bright, quick, upbeat), a calm support
   agent (warm, unhurried, reassuring), a narrator (measured, resonant), a
   character (a pirate, a robot, a wizard).
2. **Gender?** Female, male, androgynous, no preference.
3. **Accent?** American, British, Irish, or their own.

Pitch, pace, energy and timbre follow from the use, so do not ask for them.
Fill any gap with a sensible default for that use and say what you assumed.

### 1c. Which LLM

In the same AskUserQuestion call (or on its own in the image path), ask
**which LLM the bot should think with**. Each runs on its small, low-latency
model, the right size for a real-time voice conversation:

- **OpenAI, GPT-5.6 Luna** (Recommended) — `openai`
- **Google, Gemini 3.5 Flash-Lite** — `gemini`
- **Anthropic, Claude Haiku 4.5** — `anthropic`

If `server/bot.py` already exists with an `LLM_PROVIDER` line, put "Keep
<provider>, the current one" first instead of the recommendation. The answer
goes into `apply --llm` in Step 4, and decides which key `env` asks for.

### 1d. Write the brief and get it approved

Read [references/writing-descriptions.md](references/writing-descriptions.md)
the first time; it has the attribute table and four descriptions that work
well. A good brief is one or two sentences, up to 500 characters, naming
gender, age range, accent, pitch, pace, energy, timbre, manner, and ending
with the intended use, because the use steers delivery and register, not only
the colour of the voice. Describe the voice, not what it will say, and not
the picture.

**Pick three more things** while you are at it:

- **Language**: `en` unless the voice will speak French, Spanish, Portuguese
  or German (`fr`, `es`, `pt`, `de`). Language shapes the accent, so a
  Parisian voice that will speak English stays `en`. The choice also sets
  what the bot's speech-to-text listens for, later, in Step 4.
- **Audition line**: up to 100 characters, in that language, the kind of
  sentence this bot will actually say. A receptionist gets a greeting, a
  narrator gets an opening line. Every take speaks the same line so the user
  compares voices, not scripts.
- **Working name**: short, like "Receptionist EN" or "Pirate narrator". It
  becomes the voice's name in the user's Gradium account.

**Then show it and ask before generating.** Print the brief, the working
name, the language and the audition line. In the image path, add one line
per attribute you took from the picture and one for anything you guessed
(the accent, usually). Then ask with AskUserQuestion: "Generate three takes
from this brief?" with the options **Yes, generate** and **No, I want to
change it**; the user can also type their edits directly. On a change,
rewrite the brief, show it again, and ask again. Do not call `generate`
until they say yes. Takes are cheap, but a brief that describes the wrong
character wastes a round.

## Step 2: Generate three takes and play them

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" generate --name "<working name>" --language en \
  --prompt "<brief>" --line "<audition line>"
```

With a reference image, add `--image <file>`: the script keeps a copy with
the session and the client shows it in Step 5.

About ten seconds. It writes `voices/<slug>/take-1.wav`, `take-2.wav`,
`take-3.wav` and a `session.json` holding the candidate ids, and prints the
session directory. If anything fails mid-way it deletes the candidates it
made and says so; run it again. Then play the takes:

Before playing anything, tell the user in one line that the three takes are
about to play through the speakers (about fifteen seconds in all), that all
three are variations on one character because they come from the same
description, and that the files are in `voices/<slug>/` if they would rather
open them. Then play one take per Bash call, so each call's output lines up
with what they just heard; Bash output only arrives when a command returns,
so one call for all three would announce them after the audio had finished:

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" play --session voices/<slug> --take 1
```

and again with `--take 2` and `--take 3`. If no player was found, the script
prints the file paths instead; pass them on so the user can open them.

Then ask which one they like, with AskUserQuestion when available: Take 1,
Take 2, Take 3, or none of these. Replay one on request with the same
`--take N` command.

**If they like none of them**, find out which kind of miss it is:

- Right character, none of the takes landed: run `discard` on the session so
  the candidates do not pile up in the account, then `generate` again with
  the same brief. Every request samples new voices.
- Wrong character: revise the brief with what they told you, show it, get it
  approved, discard, and generate again.

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" discard --session voices/<slug>
```

After two rounds on the same brief, suggest changing the description: more
rounds of the same words give more of the same character. `generate` never
overwrites; a second run with the same name lands in `voices/<slug>-2`.

## Step 3: Keep the chosen take

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" keep --session voices/<slug> --take 2
```

This promotes the take to a permanent voice in the user's account (free, and
it counts against their custom-voice quota like any other voice), prints the
`voice_id`, records it in `session.json`, then deletes the two rejected
candidates. That `voice_id` is the one thing worth shipping. Candidate ids
(the `vox_emb_` ones) expire after 30 days and are minted fresh on every
request, so they never belong in `bot.py`.

Running `keep` twice on the same session is safe; it reports the existing
`voice_id` and does nothing. If the cleanup part fails, the voice is still
kept; run `discard` on the session later.

## Step 4: Put the voice in the bot

[references/pipecat-bot.md](references/pipecat-bot.md) has the commands and
edits in full. The short version:

**No `server/bot.py` yet.** Copy the bundled quickstart, which is the Pipecat
scaffold for Gradium speech-to-text and text-to-speech with an LLM block
that supports OpenAI, Gemini and Anthropic. It never overwrites existing
files:

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
mkdir -p server
for f in bot.py pyproject.toml Dockerfile pcc-deploy.toml; do
  [ -e "server/$f" ] && echo "kept existing server/$f" || cp "$SKILL/assets/server/$f" server/
done
[ -e env.example ] || cp "$SKILL/assets/env.example" env.example
```

(A per-file loop rather than `cp -n`, which exits 1 on macOS when any target
already exists, even though it copies the rest.)

**Then, in every case**, write the voice id, give the bot a matching
persona, and set the LLM the user chose:

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" apply --session voices/<slug> --bot server/bot.py \
  --persona "You are Freya, the receptionist at Northgate Dental." --llm openai
```

`apply` rewrites the `GRADIUM_VOICE_ID` constant near the top of `bot.py`
and the comment above it, so the file itself records which voice this is and
the brief that produced it; sets `GRADIUM_LANGUAGE` from the session so the
speech-to-text listens in the same language; sets the `PERSONA` line the
system prompt starts with; and sets `LLM_PROVIDER`. The persona matters: the
LLM answers "who are you?" from it, and without one the model introduces
itself by its own name, which spoils the demo. One sentence with a name and
the role the voice was designed for is enough (with an image, the character
in it). Show the user the before/after it prints.

If `apply` reports that there is no `GRADIUM_VOICE_ID` constant, the bot was
not built from the template; the reference explains how to add the constant,
or swap another provider's TTS service for `GradiumTTSService`, by hand. If
it notes that there is no `LLM_PROVIDER` constant, the bot keeps the LLM it
already has.

**Environment.** The bot needs `GRADIUM_API_KEY` and the chosen provider's
key (`OPENAI_API_KEY`, `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY`) in the one
`.env` it reads. The `env` command reads `LLM_PROVIDER` from `bot.py`, picks
the file (`server/.env` if it exists, else the root `.env`, creating
`server/.env` when neither exists), copies what is exported in the shell,
and reports the rest:

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" env --from-env
```

For anything `MISSING`, ask the user for the key (the reference lists where
each one comes from) and write it with `env --set VAR=<key>`. Never print a
value back; say that it is set. Do not copy `.env.example` to `.env`: an
empty `VAR=` line in it would override a key exported in the shell with an
empty string.

## Step 5: Build the client

```bash
SKILL="${CLAUDE_SKILL_DIR:-.claude/skills/design-voice}"; SCRIPT="$SKILL/scripts/audition.py"
python3 "$SCRIPT" client --session voices/<slug>
```

This copies the bundled client into `client/` (a Vite React app built from
the Pipecat UI shadcn components; nothing is overwritten if a `client/` with
a `package.json` is already there), copies the reference image into
`client/public/` when the session has one, and writes
`client/public/voice.json` with the voice's name, image, brief and persona.
The client reads that file at load: it shows the voice's name in the header,
the image in place of the bot's audio visualizer when there is one, a
transcript window, and a control bar with the microphone control, a text
input for typing to the bot, and the Connect / Disconnect button.
[references/client.md](references/client.md) describes the layout, the
files, and how to add more Pipecat UI components.

Then install its dependencies (about a minute the first time; give the call
a five-minute timeout). `--prefix` rather than `cd`, which would leave every
later command running in `client/`:

```bash
npm install --prefix client
```

Run it again after designing another voice: it rewrites `voice.json` and
the image, and the running dev server picks the change up on reload.

## Step 6: Tell them how to run it

Give exactly this, filled in. Two terminals:

```bash
cd server
uv sync        # first run only, about a minute
uv run bot.py
```

```bash
cd client
npm install    # first run only
npm run dev
```

The bot checks its keys and the voice id at startup and exits with a one-line
message if one is missing. A healthy start prints `Bot ready!` and `Uvicorn
running on http://localhost:7860`. Vite prints its own URL, normally
<http://localhost:5173>: open it, allow the microphone when the page asks on
load, then click Connect and talk or type. The bot greets them in the new
voice.
(The runner's prebuilt client at <http://localhost:7860/client/> still works
as a fallback.) Say which keys, if any, still have to be filled in.

Close with a short recap the user can come back to: the voice name, the
`voice_id`, where the takes and `session.json` are (and the image copy, if
any), that the voice is permanent in their account, which LLM the bot uses,
and that running this skill again designs another voice and swaps it into
both the bot and the client. If `apply`'s `was:` line showed a previous
voice id rather than the placeholder, say so too: that voice is still in
their account and counts against the quota, its session is in its own
`voices/<slug>/`, and you can delete it if they want (it is permanent, so
ask first).

## When something goes wrong

| Symptom | What it means / what to do |
|---|---|
| `HTTP 401` from the script | The Gradium key is invalid or expired. Ask for a fresh one from the Gradium console. |
| `HTTP 400` or `HTTP 422` | The script checks language, take count and the two length limits before sending, so this is something else. Read the `detail` line printed under the error and report it. |
| `timed out … candidates were deleted` | The takes never became ready. The script already cleaned up; run `generate` again, and simplify the brief if it repeats. |
| `HTTP 409` on keep | A voice already exists for that candidate. The `detail` line names it; pass that id to `apply --voice-id`. |
| No audio player found | The script prints the paths; tell the user to open the WAV files. |
| `apply` says no `GRADIUM_VOICE_ID` constant | Not the template; edit by hand as the reference shows. |
| `Missing required environment variable` at startup | `env --set VAR=<key>` for that line. |
| `env` says an empty `VAR=` line overrides the shell | The file has `VAR=` with nothing after it; `env --from-env` fills it from the shell, or `--set` writes a value. |
| `uv: command not found` | `curl -LsSf https://astral.sh/uv/install.sh \| sh`, then reopen the shell. |
| `npm: command not found`, or `npm run dev` says "Vite requires Node.js version 20.19+ or 22.12+" | Install Node 22 (or 20.19+) from <https://nodejs.org>, then `npm install --prefix client`. |
| Port 7860 already in use | `uv run bot.py --port 7861`, and `PIPECAT_SERVER_URL=http://localhost:7861 npm run dev` for the client. |
| The client shows "Failed to start session" or a proxy error | The bot is not running, or runs on another port; start it, or set `PIPECAT_SERVER_URL` as above. |
| Bot connects but stays silent, log shows `401`/`403` from the LLM | The provider key in `.env` is wrong, or the account has no access to the model; `LLM_MODEL=` in `.env` picks another. |
| Bot greets, then never answers | The browser did not get microphone permission. Allow the microphone for `localhost` in the browser's site settings and reload. Typing in the text input works meanwhile. |
| The image does not show in the client | `client/public/voice.json` has `"image": null`. Point the client at a picture with `client --session voices/<slug> --image <file>`, which also records it in the session. Never run `client --image` without `--session`: with no session it writes a `voice.json` with no name, brief or persona. |

## What this skill does not do

- Deploy anything. The client is a local Vite dev server; the scaffold
  includes a `Dockerfile` and `pcc-deploy.toml` for Pipecat Cloud when the
  user wants that.
- Add more Pipecat UI components. The client is a shadcn project, so the
  user can: `cd client && npx shadcn@latest add @pipecat/<name>` (the
  reference lists them).
- Delete voices from the account. If the user asks, the call is
  `DELETE https://api.gradium.ai/api/voices/<voice_id>` with the `x-api-key`
  header; confirm with them first, since it is permanent.
