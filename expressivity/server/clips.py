"""The demo's premade clips, and the processor that plays one into the pipeline as the user's audio.

A clip goes in just after the transport's input, 20 ms at a time in real time, so everything after
it (the VAD, the STT, the perception reader) treats it exactly as it would a caller's voice. The
same audio goes out through the transport, so the visitor hears the clip too. The microphone isn't
heard while a clip plays.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from loguru import logger
from pipecat.frames.frames import Frame, InputAudioRawFrame, OutputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

SAMPLE_RATE = 16000
CLIPS_DIR = Path(__file__).resolve().parent / "clips"

_CHUNK_SECS = 0.02
_CHUNK_BYTES = int(SAMPLE_RATE * _CHUNK_SECS) * 2  # 16-bit mono


@dataclass(frozen=True)
class Clip:
    """One premade clip.

    Parameters:
        id: Its name in messages to and from the page.
        mood: How it was said, such as ``"sarcastic"``.
        sincerity: Whether it was meant: ``"sincere"`` or ``"sarcastic"``.
        voice: Who says it.
        text: Its words.
        duration: Its length in seconds.
        audio: Its sound, 16 kHz 16-bit mono PCM.
    """

    id: str
    mood: str
    sincerity: str
    voice: str
    text: str
    duration: float
    audio: bytes

    def describe(self) -> dict[str, Any]:
        """The clip as the page lists it."""
        return {
            "id": self.id,
            "mood": self.mood,
            "sincerity": self.sincerity,
            "voice": self.voice,
            "text": self.text,
            "duration": self.duration,
        }


@cache
def load_clips(folder: Path = CLIPS_DIR) -> dict[str, Clip]:
    """The clips in a folder's ``manifest.json``, by id, in its order. Loaded once a process.

    A clip whose file is missing or isn't 16 kHz 16-bit mono is left out with a warning, so a folder
    that was never filled leaves the demo with the microphone alone.
    """
    manifest = folder / "manifest.json"
    if not manifest.is_file():
        logger.warning(f"No clips: {manifest} is missing")
        return {}
    clips: dict[str, Clip] = {}
    for entry in json.loads(manifest.read_text()):
        try:
            audio = _read_wav(folder / entry["file"])
        except (OSError, ValueError, wave.Error) as e:
            logger.warning(f"Clip {entry['id']} is left out: {e}")
            continue
        clips[entry["id"]] = Clip(
            id=entry["id"],
            mood=entry["mood"],
            sincerity=entry["sincerity"],
            voice=entry["voice"],
            text=entry["text"],
            duration=len(audio) / 2 / SAMPLE_RATE,
            audio=audio,
        )
    return clips


def _read_wav(path: Path) -> bytes:
    """A WAV file's samples, or a ValueError if it isn't 16 kHz 16-bit mono."""
    with wave.open(str(path), "rb") as wav:
        found = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
        if found != (SAMPLE_RATE, 1, 2):
            raise ValueError(f"{path.name} is {found}, not 16 kHz 16-bit mono")
        return wav.readframes(wav.getnframes())


class ClipPlayer(FrameProcessor):
    """Plays a premade clip into the pipeline as the user's audio, and out to be heard.

    Goes right after the transport's input. While a clip plays, the microphone's audio is dropped
    and the clip's takes its place, followed by enough silence for the VAD to find the end of its
    speech. One clip plays at a time: playing another stops the one playing first.

    The page is told with two RTVI server messages: ``{"type": "clip-started", "clipId": ...}``
    before a clip's first audio, and ``{"type": "clip-finished", "clipId": ..., "completed": ...}``
    after its silence, where ``completed`` says whether it played to its end rather than being
    stopped.
    """

    def __init__(self, clips: Mapping[str, Clip], *, silence_secs: float, **kwargs):
        """Initialize the player.

        Args:
            clips: The clips it can play, by id, in the order they're played when none is named.
            silence_secs: Seconds of silence played after a clip, longer than the VAD waits before
                it says the speech stopped.
            **kwargs: Additional arguments passed to the parent.
        """
        super().__init__(**kwargs)
        self._clips = dict(clips)
        self._up_next = itertools.cycle(self._clips.values())
        self._silence = bytes(_CHUNK_BYTES) * round(silence_secs / _CHUNK_SECS)
        self._playing: asyncio.Task | None = None
        # Set to stop the latest clip asked for. Each clip has its own, so stopping one that waits
        # its turn doesn't stop the one after it.
        self._stop = asyncio.Event()

    @property
    def clips(self) -> list[Clip]:
        """The clips it can play, in order."""
        return list(self._clips.values())

    @property
    def playing(self) -> bool:
        """Whether a clip, or the silence after it, is being played."""
        return self._playing is not None and not self._playing.done()

    async def play(self, clip_id: str | None = None) -> bool:
        """Play a clip, once any clip already playing has been stopped and its silence played.

        Args:
            clip_id: The clip to play. With none, the next one, round and round.

        Returns:
            Whether there is such a clip.
        """
        clip = self._clips.get(clip_id) if clip_id else next(self._up_next, None)
        if clip is None:
            return False
        self.stop()
        self._stop = asyncio.Event()
        self._playing = self.create_task(self._play(clip, self._stop, after=self._playing))
        return True

    def stop(self):
        """Stop the clip playing, if any. Its silence still plays, so the VAD ends its speech."""
        self._stop.set()

    async def cleanup(self):
        await super().cleanup()
        if self._playing:
            await self.cancel_task(self._playing)
            self._playing = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame) and self.playing:
            return  # the microphone isn't heard over a clip
        await self.push_frame(frame, direction)

    async def _play(self, clip: Clip, stop: asyncio.Event, *, after: asyncio.Task | None):
        if after:
            # A wait that doesn't cancel the earlier clip's silence, nor fails if it was cancelled.
            await asyncio.wait({after})
        if stop.is_set():
            return  # stopped while it waited its turn: none of it was heard
        await self._tell("clip-started", clipId=clip.id)
        completed = await self._feed(clip.audio, stop)
        await self._feed(self._silence)
        await self._tell("clip-finished", clipId=clip.id, completed=completed)

    async def _feed(self, audio: bytes, stop: asyncio.Event | None = None) -> bool:
        """Push audio in as the user's, in real time. Returns False if stopped before its end.

        A clip, which comes with ``stop``, also goes out through the transport to be heard. The
        silence after it has none: it's played whole, since the VAD needs all of it, and isn't sent
        out.
        """
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index, offset in enumerate(range(0, len(audio), _CHUNK_BYTES)):
            if stop and stop.is_set():
                return False
            chunk = audio[offset : offset + _CHUNK_BYTES]
            await self.push_frame(
                InputAudioRawFrame(audio=chunk, sample_rate=SAMPLE_RATE, num_channels=1)
            )
            if stop:
                await self.push_frame(
                    OutputAudioRawFrame(audio=chunk, sample_rate=SAMPLE_RATE, num_channels=1)
                )
            # Paced against the audio's start, so the sleeps' overshoot doesn't add up.
            await asyncio.sleep(max(0.0, started + (index + 1) * _CHUNK_SECS - loop.time()))
        return True

    async def _tell(self, kind: str, **fields: Any):
        await self.push_frame(RTVIServerMessageFrame(data={"type": kind, **fields}))
