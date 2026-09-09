#!/usr/bin/env python3
"""Audition Gradium designed voices from the command line.

Standard library only, so ``python3 audition.py`` works without uv or pip
(Python 3.9 or newer).

Subcommands (run ``--help`` on any of them):

  generate  Describe a voice, get N takes, render each on one audition line.
            Writes take-1.wav .. take-N.wav and session.json into a session dir.
  play      Play the takes through the system audio player, one at a time.
  keep      Promote one take to a permanent voice_id. Deletes the rejected takes.
  discard   Delete every candidate in a session (the user wants none of them).
  apply     Write the kept voice_id (and optionally a persona line and the LLM
            provider) into bot.py.
  client    Scaffold the web client from the skill's template and write its
            voice.json (name, reference image, brief, persona).
  env       Create or update the .env the bot reads and report which keys are set.

The API key is read from GRADIUM_API_KEY, or from server/.env, or from .env in
the working directory (the same order the bot uses). It is never printed.

    python3 audition.py generate --name "Receptionist"
        --prompt "A British female voice, 20 to 30, glossy and confident ..."
        --line "Hi there, thanks so much for calling! How can I help you today?"
    python3 audition.py play --session voices/receptionist
    python3 audition.py keep --session voices/receptionist --take 2
    python3 audition.py apply --session voices/receptionist --bot server/bot.py --llm openai
    python3 audition.py client --session voices/receptionist
    python3 audition.py env --provider openai --from-env
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "https://api.gradium.ai/api"

# Pipecat's GradiumTTSService talks to the streaming websocket and does not send a
# model name, so the bot always gets the server default. Auditioning with "default"
# means the take the user hears is what the bot will ship. --model exists for
# experiments only; the bundled bot cannot honour another value.
DEFAULT_MODEL = "default"

LANGUAGES = ("en", "fr", "es", "pt", "de")
MAX_PROMPT_CHARS = 500
MAX_LINE_CHARS = 100
MAX_TAKES = 5
POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S = 120.0
HTTP_TIMEOUT_S = 120.0

DEFAULT_LINE = "Hi there, thanks so much for calling. How can I help you today?"

# Reference images the skill can design a voice from (generate --image).
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# LLM providers the bundled bot.py knows, and the .env variable each one reads.
LLM_PROVIDERS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

# This script lives in <skill>/scripts/; the templates live in <skill>/assets/.
SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent


class ApiError(RuntimeError):
    """A failed request. ``status`` is the HTTP status, or None for network errors."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class PollTimeout(ApiError):
    """The candidates did not become ready within POLL_TIMEOUT_S."""

    def __init__(self, ids: list[str]):
        super().__init__(f"timed out after {POLL_TIMEOUT_S:.0f}s waiting for {', '.join(ids)}")
        self.ids = ids


# --------------------------------------------------------------------------- key

def read_dotenv_value(path: pathlib.Path, wanted: str) -> str | None:
    """Read one variable from a .env file the way python-dotenv would.

    Handles ``export KEY=...``, spaces around ``=``, single or double quotes,
    a trailing ``# comment`` on unquoted values, CRLF line endings and a BOM.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    found = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        key, sep, value = line.partition("=")
        if not sep or key.strip() != wanted:
            continue
        value = value.strip()
        if value[:1] == "'":
            end = value.find("'", 1)
            value = value[1:end] if end > 0 else value[1:]
        elif value[:1] == '"':
            # Double quotes allow \" and \\ escapes, as python-dotenv reads them.
            out, i = [], 1
            while i < len(value):
                c = value[i]
                if c == "\\" and i + 1 < len(value):
                    out.append(value[i + 1])
                    i += 2
                    continue
                if c == '"':
                    break
                out.append(c)
                i += 1
            value = "".join(out)
        else:
            value = value.split(" #", 1)[0].split("\t#", 1)[0].strip()
        # Keep scanning: python-dotenv, which the bot uses, takes the last
        # assignment of a key, so a duplicate later in the file is what wins.
        found = value or None
    return found


def load_api_key(explicit: str | None) -> str:
    """GRADIUM_API_KEY from the environment, else server/.env, else .env."""
    if explicit:
        return explicit
    key = os.environ.get("GRADIUM_API_KEY", "").strip()
    if key:
        return key
    for candidate in ("server/.env", ".env", "../server/.env", "../.env"):
        value = read_dotenv_value(pathlib.Path(candidate), "GRADIUM_API_KEY")
        if value:
            return value
    raise ApiError(
        "no API key. Set GRADIUM_API_KEY in the environment, or put "
        "GRADIUM_API_KEY=... in server/.env (or .env at the project root)."
    )


# --------------------------------------------------------------------------- http

class Client:
    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self._key = api_key
        self._base = base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict | None = None,
                 stream_to: pathlib.Path | None = None) -> dict | None:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self._base + path,
            data=data,
            method=method,
            headers={
                "x-api-key": self._key,
                "content-type": "application/json",
                "accept": "*/*",
                "x-api-source": "claude-skill-design-voice",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                if stream_to is not None:
                    with open(stream_to, "wb") as f:
                        shutil.copyfileobj(resp, f)
                    return None
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            raise ApiError(explain(e.code, method, path, text), status=e.code) from None
        except urllib.error.URLError as e:
            raise ApiError(f"network failure talking to {self._base}: {e.reason}") from None
        except (OSError, http.client.HTTPException) as e:
            # Covers a stalled read (socket timeout), a reset connection and a
            # failed write of the audio file; the message names which.
            raise ApiError(f"{method} {path} failed mid-transfer: {e}") from None

    def generate(self, prompt: str, language: str, n: int) -> list[dict]:
        out = self._request("POST", "/voice-generator/generate",
                            {"prompt": prompt, "language": language, "n_samples": n})
        return out["embeddings"]

    def get_embedding(self, embedding_id: str) -> dict | None:
        out = self._request("GET", f"/voice-generator/embeddings?embedding_id={embedding_id}")
        items = (out or {}).get("embeddings") or []
        return items[0] if items else None

    def wait_ready(self, ids: list[str]) -> float:
        start = time.monotonic()
        pending = set(ids)
        while pending:
            for eid in sorted(pending):
                emb = self.get_embedding(eid)
                if emb is None:
                    raise ApiError(f"candidate {eid} vanished while waiting for it")
                if emb.get("ready"):
                    pending.discard(eid)
            if not pending:
                break
            if time.monotonic() - start > POLL_TIMEOUT_S:
                raise PollTimeout(sorted(pending))
            time.sleep(POLL_INTERVAL_S)
        return time.monotonic() - start

    def tts_to_file(self, voice_id: str, text: str, model: str, path: pathlib.Path) -> float:
        start = time.monotonic()
        part = path.with_suffix(path.suffix + ".part")
        try:
            self._request("POST", "/speech/tts", {
                "text": text,
                "voice_id": voice_id,
                "model_name": model,
                "output_format": "wav",
                "only_audio": True,
            }, stream_to=part)
            fix_wav_sizes(part)
            part.replace(path)
        finally:
            part.unlink(missing_ok=True)
        return time.monotonic() - start

    def keep(self, embedding_id: str, name: str, description: str) -> dict:
        return self._request("POST", "/voices/from-embedding", {
            "voxium_embedding_id": embedding_id,
            "name": name,
            "description": description,
        })

    def delete_embedding(self, embedding_id: str) -> bool:
        """Delete a candidate. False if it was already gone; raises on other errors."""
        try:
            self._request("DELETE", f"/voice-generator/embeddings/{embedding_id}")
            return True
        except ApiError as e:
            if e.status == 404:
                return False
            raise

    def delete_embeddings(self, ids: list[str], what: str) -> None:
        """Best-effort cleanup: report what could not be removed, never raise."""
        removed, failed = 0, []
        for eid in ids:
            try:
                if self.delete_embedding(eid):
                    removed += 1
            except ApiError as e:
                failed.append(eid)
                print(f"  could not delete {eid}: {str(e).splitlines()[0]}", file=sys.stderr)
        print(f"Deleted {removed} {what}{'s' if removed != 1 else ''}"
              + (f"; {len(failed)} could not be deleted, try `discard` later" if failed else ""))


def explain(status: int, method: str, path: str, text: str) -> str:
    detail = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "detail" in parsed:
            detail = parsed["detail"] if isinstance(parsed["detail"], str) else json.dumps(parsed["detail"])
    except ValueError:
        pass
    hints = {
        400: "the request was rejected; the script checks lengths first, so read the detail",
        401: "the API key is invalid or expired",
        404: "the id could not be resolved; the candidate may have expired (30 days)",
        409: "a voice already exists for this candidate; the detail names it, use that "
             "voice_id with `apply --voice-id`",
        422: "the request was rejected as invalid; the script checks language and take "
             "count first, so read the detail",
    }
    hint = hints.get(status)
    msg = f"{method} {path} -> HTTP {status}"
    if hint:
        msg += f" ({hint})"
    if detail:
        msg += f"\n  {detail[:500]}"
    return msg


# --------------------------------------------------------------------------- wav

def fix_wav_sizes(path: pathlib.Path) -> None:
    """Rewrite the RIFF and data lengths of a streamed WAV.

    The API streams the audio, so the header carries placeholder sizes. Players
    that trust the header (Python's wave module, some DAWs) misread the length.
    """
    with open(path, "r+b") as f:
        head = f.read(12)
        if len(head) < 12 or head[0:4] != b"RIFF" or head[8:12] != b"WAVE":
            return
        size = path.stat().st_size
        f.seek(4)
        f.write(struct.pack("<I", size - 8))
        pos = 12
        while pos + 8 <= size:
            f.seek(pos)
            header = f.read(8)
            if len(header) < 8:
                return
            cid, clen = header[0:4], struct.unpack("<I", header[4:8])[0]
            if cid == b"data":
                f.seek(pos + 4)
                f.write(struct.pack("<I", size - pos - 8))
                return
            if clen in (0xFFFFFFFF, 0):
                return
            pos += 8 + clen + (clen & 1)


def wav_seconds(path: pathlib.Path) -> float | None:
    try:
        import wave
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


# --------------------------------------------------------------------------- session

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "voice"


def load_session(session_dir: pathlib.Path) -> dict:
    path = session_dir / "session.json"
    if not path.is_file():
        raise ApiError(f"no session.json in {session_dir}. Run `generate` first.")
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ApiError(f"{path} is not valid JSON: {e}") from None
    if not isinstance(session, dict) or not isinstance(session.get("takes"), list):
        raise ApiError(f"{path} does not look like a session file")
    return session


def save_session(session_dir: pathlib.Path, session: dict) -> None:
    (session_dir / "session.json").write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_session_dir(name: str, out_dir: str | None) -> pathlib.Path:
    """voices/<slug>, or the given dir; never reuses a dir that holds a session."""
    base = pathlib.Path(out_dir) if out_dir else pathlib.Path("voices") / slugify(name)
    if not base.name:  # ".", "/", or a path ending in ".."
        base = base.resolve()
    if not base.name:
        base = base / "session"
    session_dir, n = base, 2
    while (session_dir / "session.json").exists():
        session_dir = base.with_name(f"{base.name}-{n}")
        n += 1
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


# --------------------------------------------------------------------------- commands

def cmd_generate(args: argparse.Namespace) -> int:
    prompt = args.prompt.strip()
    if not prompt:
        raise ApiError("the description is blank")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ApiError(f"the description is {len(prompt)} characters; the limit is {MAX_PROMPT_CHARS}")
    line = args.line.strip()
    if not line:
        raise ApiError("the audition line is blank")
    if len(line) > MAX_LINE_CHARS:
        raise ApiError(f"the audition line is {len(line)} characters; the limit is {MAX_LINE_CHARS}")
    if args.language not in LANGUAGES:
        raise ApiError(f"language must be one of {', '.join(LANGUAGES)}")
    if not 1 <= args.takes <= MAX_TAKES:
        raise ApiError(f"takes must be between 1 and {MAX_TAKES}")
    if args.model != DEFAULT_MODEL:
        print(f"note: auditioning with model {args.model!r}, but Pipecat's GradiumTTSService "
              f"cannot select a model, so the bot will use the server default.", file=sys.stderr)

    image_src = None
    if args.image:
        image_src = pathlib.Path(args.image)
        if not image_src.is_file():
            raise ApiError(f"{image_src} does not exist")
        if image_src.suffix.lower() not in IMAGE_EXTS:
            raise ApiError(f"{image_src} is not a supported image ({', '.join(IMAGE_EXTS)})")

    client = Client(load_api_key(args.api_key), args.url)
    session_dir = new_session_dir(args.name, args.out_dir)

    image_name = None
    if image_src is not None:
        # Keep a copy with the session so the record survives the original being moved.
        image_name = "reference" + image_src.suffix.lower()
        if image_src.resolve() != (session_dir / image_name).resolve():
            shutil.copy2(image_src, session_dir / image_name)

    print(f"Designing \"{args.name}\" ({args.language}, {args.takes} take{'s' if args.takes != 1 else ''})")
    print(f"  {prompt}")
    if image_src is not None:
        print(f"  from image {image_src} (copied to {session_dir / image_name})")
    drafts = client.generate(prompt, args.language, args.takes)
    ids = [d["embedding_id"] for d in drafts]

    # Record the ids before anything else can fail, so `discard` always works.
    session = {
        "name": args.name,
        "prompt": prompt,
        "language": args.language,
        "audition_line": line,
        "model": args.model,
        "image": image_name,
        "image_source": str(image_src) if image_src is not None else None,
        "created_at": utc_now(),
        "takes": [
            {"take": i, "embedding_id": eid, "file": None, "expires_at": d.get("expires_at")}
            for i, (eid, d) in enumerate(zip(ids, drafts), start=1)
        ],
        "kept": None,
    }
    save_session(session_dir, session)

    try:
        print("Waiting for the takes to be ready", end="", flush=True)
        elapsed = client.wait_ready(ids)
        print(f" ready in {elapsed:.1f}s")

        print(f"Rendering the audition line: \"{line}\"")
        for take in session["takes"]:
            path = session_dir / f"take-{take['take']}.wav"
            dt = client.tts_to_file(take["embedding_id"], line, args.model, path)
            secs = wav_seconds(path)
            length = f"{secs:.1f}s of audio" if secs else f"{path.stat().st_size} bytes"
            print(f"  Take {take['take']}  {path}  ({length}, rendered in {dt:.1f}s)")
            take["file"] = path.name
            save_session(session_dir, session)
    except (ApiError, KeyboardInterrupt) as e:
        print()
        # The candidates are recorded in session.json, but half a session is not
        # worth keeping: generation takes seconds, so clean up and start over.
        client.delete_embeddings(ids, "candidate")
        session["discarded_at"] = utc_now()
        save_session(session_dir, session)
        if isinstance(e, KeyboardInterrupt):
            raise
        if isinstance(e, PollTimeout):
            raise ApiError(f"{e}. The candidates were deleted. Run `generate` again; "
                           "if it repeats, simplify the description.") from None
        raise ApiError(f"{e}\nThe candidates were deleted. Run `generate` again.") from None

    print()
    print(f"Session: {session_dir}")
    print(f"Next: python3 {sys.argv[0]} play --session {session_dir}")
    return 0


def find_player() -> list[str] | None:
    """Return a command prefix that plays a WAV and exits when it finishes."""
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay"]
    for name, argv in (
        ("paplay", ["paplay"]),
        ("aplay", ["aplay", "-q"]),
        ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]),
        ("mpv", ["mpv", "--no-video", "--really-quiet"]),
        ("cvlc", ["cvlc", "--play-and-exit", "--quiet"]),
    ):
        if shutil.which(name):
            return argv
    if sys.platform.startswith("win") and shutil.which("powershell"):
        return ["powershell", "-c", "(New-Object Media.SoundPlayer '{path}').PlaySync()"]
    return None


def cmd_play(args: argparse.Namespace) -> int:
    session_dir = pathlib.Path(args.session)
    session = load_session(session_dir)
    takes = [t for t in session["takes"] if t.get("file")]
    if args.take:
        takes = [t for t in takes if t["take"] == args.take]
        if not takes:
            raise ApiError(f"no rendered take {args.take} in {session_dir}")
    if not takes:
        raise ApiError(f"no rendered takes in {session_dir}; run `generate` again")
    player = find_player()
    if player is None:
        print("No command-line audio player found. Open these files to listen:")
        for t in takes:
            print(f"  Take {t['take']}: {session_dir / t['file']}")
        return 0
    for i, t in enumerate(takes):
        path = session_dir / t["file"]
        secs = wav_seconds(path)
        print(f"Playing take {t['take']}" + (f" ({secs:.1f}s)" if secs else "") + f"  {path}", flush=True)
        if any("{path}" in a for a in player):
            argv = [a.replace("{path}", str(path)) for a in player]
        else:
            argv = player + [str(path)]
        subprocess.run(argv, check=False)
        if args.gap and i < len(takes) - 1:
            time.sleep(args.gap)
    return 0


def cmd_keep(args: argparse.Namespace) -> int:
    session_dir = pathlib.Path(args.session)
    session = load_session(session_dir)
    if session.get("kept"):
        k = session["kept"]
        print(f"Take {k['take']} was already kept as voice_id {k['voice_id']} ({k['name']}).")
        print("Nothing to do.")
        return 0
    chosen = next((t for t in session["takes"] if t["take"] == args.take), None)
    if chosen is None:
        raise ApiError(f"no take {args.take} in {session_dir}; takes are 1 to {len(session['takes'])}")

    client = Client(load_api_key(args.api_key), args.url)
    name = (args.name or session["name"]).strip()
    description = (args.description or session["prompt"])[:500]

    print(f"Keeping take {args.take} as \"{name}\"")
    kept = client.keep(chosen["embedding_id"], name, description)
    voice_id = kept["uid"]
    session["kept"] = {
        "take": args.take,
        "embedding_id": chosen["embedding_id"],
        "voice_id": voice_id,
        "name": name,
        "kept_at": utc_now(),
    }
    save_session(session_dir, session)

    # The voice is permanent from here, so say so before any cleanup can fail.
    print()
    print(f"voice_id: {voice_id}")
    print(f"This voice is now permanent in your Gradium account as \"{name}\".")
    print(f"Recorded in {session_dir / 'session.json'}")
    print()

    if not args.keep_others:
        rejected = [t["embedding_id"] for t in session["takes"] if t["take"] != args.take]
        client.delete_embeddings(rejected, "rejected take")
    return 0


def cmd_discard(args: argparse.Namespace) -> int:
    session_dir = pathlib.Path(args.session)
    session = load_session(session_dir)
    client = Client(load_api_key(args.api_key), args.url)
    kept_id = (session.get("kept") or {}).get("embedding_id")
    ids = [t["embedding_id"] for t in session["takes"] if t["embedding_id"] != kept_id]
    client.delete_embeddings(ids, "candidate")
    session["discarded_at"] = utc_now()
    save_session(session_dir, session)
    if kept_id:
        print("The kept voice is untouched; it holds its own copy.")
    return 0


def wrap_comment(text: str, width: int = 88) -> list[str]:
    """Wrap text into '# ' comment lines."""
    words, lines, cur = text.split(), [], "#"
    for w in words:
        if len(cur) + 1 + len(w) > width and cur != "#":
            lines.append(cur)
            cur = "#"
        cur += " " + w
    lines.append(cur)
    return lines


CONST_RE = re.compile(r'^(?P<indent>\s*)GRADIUM_VOICE_ID\s*=\s*["\'][^"\']*["\']\s*(#.*)?$')
PERSONA_RE = re.compile(r'^(?P<indent>\s*)PERSONA\s*=\s*(?P<q>["\'])(?P<val>.*)(?P=q)\s*(#.*)?$')
LANG_RE = re.compile(r'^(?P<indent>\s*)GRADIUM_LANGUAGE\s*=\s*["\'][^"\']*["\']\s*(#.*)?$')
LLM_RE = re.compile(r'^(?P<indent>\s*)LLM_PROVIDER\s*=\s*["\'](?P<val>[^"\']*)["\']\s*(#.*)?$')


def py_string(text: str) -> str:
    """A valid one-line Python string literal for arbitrary text."""
    return json.dumps(" ".join(text.split()), ensure_ascii=False)


def cmd_apply(args: argparse.Namespace) -> int:
    bot = pathlib.Path(args.bot)
    if not bot.is_file():
        raise ApiError(f"{bot} does not exist. Scaffold the server first (see references/pipecat-bot.md).")

    language = args.language
    session = None
    if args.session:
        session = load_session(pathlib.Path(args.session))
        kept = session.get("kept")
        if not kept:
            raise ApiError(f"nothing kept in {args.session} yet. Run `keep --take N` first.")
        voice_id = kept["voice_id"]
        name = args.name or kept.get("name") or session.get("name") or ""
        brief = args.brief or session.get("prompt") or ""
        language = language or session.get("language")
    elif args.voice_id:
        voice_id, name, brief = args.voice_id, args.name or "", args.brief or ""
    else:
        raise ApiError("pass --session <dir> (after keep) or --voice-id <id>")
    if voice_id.startswith("vox_emb_"):
        raise ApiError(f"{voice_id} is a candidate id; keep the take first and apply its voice_id")
    if language and language not in LANGUAGES:
        raise ApiError(f"language must be one of {', '.join(LANGUAGES)}")

    lines = bot.read_text(encoding="utf-8").splitlines()
    idx = next((i for i, l in enumerate(lines) if CONST_RE.match(l)), None)
    if idx is None:
        print(
            f"No GRADIUM_VOICE_ID constant in {bot}. Add one near the top:\n"
            f"    GRADIUM_VOICE_ID = \"{voice_id}\"\n"
            "and pass voice=GRADIUM_VOICE_ID to GradiumTTSService.Settings "
            "(see references/pipecat-bot.md).",
            file=sys.stderr,
        )
        return 2
    indent = CONST_RE.match(lines[idx]).group("indent")
    start = idx
    while start > 0 and lines[start - 1].strip().startswith("#"):
        start -= 1
    previous = lines[idx]

    header = "# The Gradium voice this bot speaks with, designed with the design-voice skill."
    if name and brief:
        label = f"Voice \"{name}\": {brief}"
    else:
        label = f"Voice \"{name}\"" if name else brief
    new_block = [indent + header]
    if label.strip():
        new_block += [indent + l for l in wrap_comment(" ".join(label.split()))]
    new_block.append(f'{indent}GRADIUM_VOICE_ID = "{voice_id}"')
    lines[start : idx + 1] = new_block

    notes = []
    if language:
        lidx = next((i for i, l in enumerate(lines) if LANG_RE.match(l)), None)
        if lidx is not None:
            lindent = LANG_RE.match(lines[lidx]).group("indent")
            lines[lidx] = f'{lindent}GRADIUM_LANGUAGE = "{language}"'
            notes.append(f'  language: GRADIUM_LANGUAGE = "{language}"')
        elif language != "en":
            notes.append(f"  language: no GRADIUM_LANGUAGE constant in this file; make sure the "
                         f"speech-to-text service is set to {language!r}")
    if args.persona:
        pidx = next((i for i, l in enumerate(lines) if PERSONA_RE.match(l)), None)
        if pidx is None:
            notes.append("  persona: no PERSONA constant in this file; set the system prompt by hand")
        else:
            pindent = PERSONA_RE.match(lines[pidx]).group("indent")
            lines[pidx] = f"{pindent}PERSONA = {py_string(args.persona)}"
            notes.append(f"  persona: {lines[pidx].strip()}")
    if args.llm:
        lidx = next((i for i, l in enumerate(lines) if LLM_RE.match(l)), None)
        if lidx is None:
            notes.append("  llm: no LLM_PROVIDER constant in this file (not the template); "
                         "its LLM is whatever it already uses")
        else:
            m = LLM_RE.match(lines[lidx])
            lines[lidx] = f'{m.group("indent")}LLM_PROVIDER = "{args.llm}"'
            notes.append(f'  llm: LLM_PROVIDER = "{args.llm}" (was {m.group("val")!r}; '
                         f"needs {LLM_PROVIDERS[args.llm]} in .env)")

    text = "\n".join(lines) + "\n"
    try:
        compile(text, str(bot), "exec")
    except SyntaxError as e:
        raise ApiError(f"refusing to write {bot}: the result would not compile ({e})")
    bot.write_text(text, encoding="utf-8")

    if session is not None:
        # Record what went into the bot, so `client` can reuse the persona.
        if args.persona:
            session["persona"] = " ".join(args.persona.split())
        if args.llm:
            session["llm_provider"] = args.llm
        session["applied_to"] = str(bot)
        save_session(pathlib.Path(args.session), session)

    print(f"Updated {bot}")
    print(f"  was: {previous.strip()}")
    print(f"  now: GRADIUM_VOICE_ID = \"{voice_id}\"")
    for n in notes:
        print(n)
    return 0


# --------------------------------------------------------------------------- client

def copy_tree_keep_existing(src: pathlib.Path, dest: pathlib.Path) -> tuple[int, int]:
    """Copy src into dest without overwriting anything. Returns (copied, kept)."""
    copied = kept = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", ".vite")]
        rel = pathlib.Path(root).relative_to(src)
        (dest / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            target = dest / rel / f
            if target.exists():
                kept += 1
            else:
                shutil.copy2(pathlib.Path(root) / f, target)
                copied += 1
    return copied, kept


def cmd_client(args: argparse.Namespace) -> int:
    client_dir = pathlib.Path(args.client)
    template = SKILL_DIR / "assets" / "client"
    session = load_session(pathlib.Path(args.session)) if args.session else None

    name = args.name or (session or {}).get("name")
    brief = args.brief or (session or {}).get("prompt")
    persona = args.persona or (session or {}).get("persona")

    if (client_dir / "package.json").is_file():
        print(f"Kept the existing client in {client_dir}/ (it has a package.json)")
    else:
        if not (template / "package.json").is_file():
            raise ApiError(f"the client template is missing from {template}")
        copied, kept = copy_tree_keep_existing(template, client_dir)
        print(f"Scaffolded {client_dir}/ from the skill's client template "
              f"({copied} files copied" + (f", {kept} existing kept" if kept else "") + ")")

    public = client_dir / "public"
    public.mkdir(parents=True, exist_ok=True)

    image_src = None
    if args.image:
        image_src = pathlib.Path(args.image)
    elif session and session.get("image"):
        image_src = pathlib.Path(args.session) / session["image"]
    image_url = None
    if image_src is not None:
        if not image_src.is_file():
            print(f"warning: {image_src} is missing; the client will show the visualizer instead",
                  file=sys.stderr)
        elif image_src.suffix.lower() not in IMAGE_EXTS:
            raise ApiError(f"{image_src} is not a supported image ({', '.join(IMAGE_EXTS)})")
        else:
            dest = public / (slugify(name or "voice") + image_src.suffix.lower())
            if image_src.resolve() != dest.resolve():
                shutil.copy2(image_src, dest)
                print(f"Copied the reference image to {dest}")
            image_url = "/" + dest.name

    voice = {"name": name, "image": image_url, "brief": brief, "persona": persona}
    voice_path = public / "voice.json"
    # An image the previous run copied and this voice no longer uses would linger in
    # public/; remove it (the session directory still holds the original).
    try:
        was = json.loads(voice_path.read_text(encoding="utf-8"))
        previous, previous_name = was.get("image"), was.get("name")
    except (OSError, ValueError, AttributeError):
        previous = previous_name = None
    if isinstance(previous, str) and previous != image_url and previous.startswith("/"):
        stale = public / previous.lstrip("/")
        # Only a file this script wrote: <slug of the previous name>.<ext>, in
        # public/ itself, and not the one just copied in.
        previous_slug = slugify(previous_name or "voice") if previous_name else None
        if (
            stale.is_file()
            and stale.parent == public
            and previous_slug
            and stale.stem == previous_slug
            and (image_src is None or stale.resolve() != image_src.resolve())
        ):
            stale.unlink()
            print(f"Removed {stale}, the previous voice's image")
    voice_path.write_text(json.dumps(voice, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {voice_path}")
    print(f"  name: {name or '(none)'}")
    print(f"  image: {image_url or 'none, the client shows the voice visualizer'}")
    print(f"  persona: {persona or '(none)'}")
    print()
    print("Next, in the user's second terminal:")
    print(f"  cd {client_dir} && npm install   # first run only")
    print("  npm run dev")
    print(f"(from here, install without changing directory: npm install --prefix {client_dir})")
    return 0


# --------------------------------------------------------------------------- env

ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=")
ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
BOT_LLM_RE = re.compile(r'^\s*LLM_PROVIDER\s*=\s*["\']([^"\']*)["\']', re.MULTILINE)


def env_value_literal(value: str) -> str:
    """Write a value the way python-dotenv reads it back unchanged."""
    if not value or any(c in value for c in " #\"'\\\t"):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def env_file_path(explicit: str | None) -> pathlib.Path:
    """The one .env the bot reads: server/.env if it exists, else .env at the root."""
    if explicit:
        return pathlib.Path(explicit)
    for candidate in ("server/.env", ".env"):
        if pathlib.Path(candidate).is_file():
            return pathlib.Path(candidate)
    return pathlib.Path("server/.env") if pathlib.Path("server").is_dir() else pathlib.Path(".env")


def bot_llm_provider(bot: pathlib.Path) -> str | None:
    try:
        m = BOT_LLM_RE.search(bot.read_text(encoding="utf-8"))
    except OSError:
        return None
    return m.group(1) if m else None


def cmd_env(args: argparse.Namespace) -> int:
    path = env_file_path(args.file)
    if path.exists() and not path.is_file():
        raise ApiError(f"{path} is not a file; pass the .env path, e.g. --file server/.env")
    provider = args.provider or bot_llm_provider(pathlib.Path(args.bot))
    if provider and provider not in LLM_PROVIDERS:
        raise ApiError(f"unknown LLM provider {provider!r}; use one of {', '.join(LLM_PROVIDERS)}")
    required = ["GRADIUM_API_KEY"] + ([LLM_PROVIDERS[provider]] if provider else [])

    updates: dict[str, str] = {}
    for item in args.set or []:
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or not ENV_VAR_RE.match(key):
            raise ApiError("--set expects VAR=value, with VAR in upper case")
        if not value.strip():
            raise ApiError(f"--set {key}= has no value; an empty line would override the shell")
        updates[key] = value.strip()
    if args.from_env:
        for var in required:
            shell = os.environ.get(var, "").strip()
            if var not in updates and shell and not read_dotenv_value(path, var):
                updates[var] = shell

    if path.is_file():
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    else:
        lines = [
            "# Secrets for the Pipecat bot, written by the design-voice skill. Gitignored.",
            "# Only the LLM key for the provider named by LLM_PROVIDER in bot.py is needed.",
            "# Do not leave a VAR= line empty: it overrides a value exported in the shell.",
            "",
        ]
    positions = {}
    for i, raw in enumerate(lines):
        m = ENV_LINE_RE.match(raw)
        if m:
            positions[m.group("key")] = i
    written = []
    for var, value in updates.items():
        line = f"{var}={env_value_literal(value)}"
        if var in positions:
            if lines[positions[var]] == line:
                continue
            lines[positions[var]] = line
        else:
            lines.append(line)
        written.append(var)
    if written:
        existed = path.is_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        print(("Updated " if existed else "Created ") + f"{path}: set " + ", ".join(written))

    print(f"bot reads: {path}" + ("" if path.is_file() else " (not created yet)")
          + (f"   LLM provider: {provider}" if provider else ""))
    missing = []
    for var in required + sorted(set(updates) - set(required)):
        in_file = read_dotenv_value(path, var)
        in_shell = os.environ.get(var, "").strip()
        has_empty_line = var in positions and not in_file
        if in_file:
            print(f"  {var}: set")
        elif in_shell and has_empty_line:
            print(f"  {var}: MISSING. The empty {var}= line in {path} overrides the value "
                  f"exported in the shell; run `env --from-env` to fill it in")
            missing.append(var)
        elif in_shell:
            print(f"  {var}: set in the shell only (fine for `uv run bot.py`; Docker and "
                  f"Pipecat Cloud read the file, `env --from-env` copies it there)")
        else:
            print(f"  {var}: MISSING")
            missing.append(var)
    if missing:
        print(f"Add with: python3 {sys.argv[0]} env --set {missing[0]}=<value>"
              + (" ..." if len(missing) > 1 else ""))
    return 0


# --------------------------------------------------------------------------- cli

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=BASE_URL, help=argparse.SUPPRESS)
    p.add_argument("--api-key", default=None, help="Gradium API key (default: GRADIUM_API_KEY, then .env)")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="describe a voice and render N takes")
    g.add_argument("--name", required=True, help="working name for the voice, e.g. Receptionist")
    g.add_argument("--prompt", required=True, help=f"voice description, up to {MAX_PROMPT_CHARS} chars")
    g.add_argument("--line", default=DEFAULT_LINE, help=f"audition line every take speaks, up to {MAX_LINE_CHARS} chars")
    g.add_argument("--language", default="en", choices=LANGUAGES)
    g.add_argument("--takes", type=int, default=3, help=f"how many takes, 1 to {MAX_TAKES}")
    g.add_argument("--model", default=DEFAULT_MODEL, help="TTS model for the audition (experiments only)")
    g.add_argument("--out-dir", default=None, help="session directory (default: voices/<slug of name>)")
    g.add_argument("--image", default=None,
                   help=f"reference image the description was written from ({', '.join(IMAGE_EXTS)}); "
                        "a copy is kept with the session and the client shows it")
    g.set_defaults(func=cmd_generate)

    pl = sub.add_parser("play", help="play the takes")
    pl.add_argument("--session", required=True, help="session directory from generate")
    pl.add_argument("--take", type=int, default=None, help="play only this take")
    pl.add_argument("--gap", type=float, default=0.6, help="seconds of silence between takes")
    pl.set_defaults(func=cmd_play)

    k = sub.add_parser("keep", help="promote one take to a permanent voice")
    k.add_argument("--session", required=True)
    k.add_argument("--take", type=int, required=True, help="the take to keep, 1-based")
    k.add_argument("--name", default=None, help="voice name in the account (default: the session name)")
    k.add_argument("--description", default=None, help="voice description in the account (default: the prompt)")
    k.add_argument("--keep-others", action="store_true", help="do not delete the rejected takes")
    k.set_defaults(func=cmd_keep)

    d = sub.add_parser("discard", help="delete every unkept candidate in a session")
    d.add_argument("--session", required=True)
    d.set_defaults(func=cmd_discard)

    a = sub.add_parser("apply", help="write the kept voice_id into bot.py")
    a.add_argument("--bot", default="server/bot.py", help="path to the Pipecat bot file")
    a.add_argument("--session", default=None, help="session directory with a kept take")
    a.add_argument("--voice-id", default=None, help="a permanent voice_id, instead of --session")
    a.add_argument("--name", default=None, help="voice name for the comment (default: from the session)")
    a.add_argument("--brief", default=None, help="voice description for the comment (default: from the session)")
    a.add_argument("--language", default=None, choices=LANGUAGES,
                   help="language for GRADIUM_LANGUAGE (default: from the session)")
    a.add_argument("--persona", default=None,
                   help='one sentence for the PERSONA constant, e.g. "You are Fionn, the support agent for Northgate IT."')
    a.add_argument("--llm", default=None, choices=sorted(LLM_PROVIDERS),
                   help="LLM provider for the LLM_PROVIDER constant")
    a.set_defaults(func=cmd_apply)

    c = sub.add_parser("client", help="scaffold the web client and write its voice.json")
    c.add_argument("--session", default=None, help="session directory (name, image, brief, persona)")
    c.add_argument("--client", default="client", help="client directory (default: client)")
    c.add_argument("--name", default=None, help="voice name shown in the client (default: from the session)")
    c.add_argument("--image", default=None, help="image to show instead of the visualizer (default: the session's)")
    c.add_argument("--brief", default=None, help="voice description shown under the name (default: from the session)")
    c.add_argument("--persona", default=None, help="persona line (default: the one `apply` recorded)")
    c.set_defaults(func=cmd_client)

    e = sub.add_parser("env", help="create or update the .env the bot reads, and report what is set")
    e.add_argument("--provider", default=None, choices=sorted(LLM_PROVIDERS),
                   help="LLM provider whose key is required (default: LLM_PROVIDER from --bot)")
    e.add_argument("--bot", default="server/bot.py", help="bot file to read LLM_PROVIDER from")
    e.add_argument("--file", default=None, help=".env path (default: server/.env if present, else .env)")
    e.add_argument("--set", action="append", metavar="VAR=value",
                   help="write a variable (repeatable); the value is never printed")
    e.add_argument("--from-env", action="store_true",
                   help="copy required variables that are exported in the shell into the file")
    e.set_defaults(func=cmd_env)
    return p


def main() -> int:
    # A non-UTF-8 stdout (LC_ALL=C, a Windows console) would otherwise raise
    # UnicodeEncodeError when a name, brief or persona is not ASCII. Files are
    # always written as UTF-8; only what is echoed here degrades.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (OSError, ValueError):
                pass
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
