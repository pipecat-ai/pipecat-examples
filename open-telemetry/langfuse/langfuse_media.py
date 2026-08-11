#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Attach conversation audio to a Langfuse trace.

Pipecat sends spans to Langfuse over OTLP, but Langfuse media does not travel over OTLP.
Audio is uploaded out of band through the media REST API and linked to a trace, or to a
single observation inside it, by id. Langfuse renders a player from that link alone, so
nothing has to be written into the span payload and no span has to still be open.

That gives two levels of playback:

- The whole call, linked to the trace, playable from the trace root.
- Each turn, linked to that turn's ``turn`` span. The user's speech lands on the span's
  ``input`` and the bot's reply on its ``output``, so clicking a turn plays just that turn.

Because linking is by id, all uploading happens after the pipeline has shut down. Turn span
ids stay available through ``TurnTraceObserver.get_turn_context()``, which retains them for
the life of the observer.

See https://langfuse.com/docs/observability/features/multi-modality
"""

import asyncio
import base64
import hashlib
import io
import os
import time
import wave
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from loguru import logger
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor

# AudioBufferProcessor emits raw signed 16-bit little-endian PCM.
SAMPLE_WIDTH_BYTES = 2

# Stereo 24kHz s16 is roughly 350MB/hour, so cap the whole-call recording well below what
# Langfuse would accept and truncate loudly rather than exhausting the container.
DEFAULT_MAX_BYTES = 100 * 1024 * 1024

# How long to wait after the recording stops for the final on_audio_data event. Pipecat
# dispatches async event handlers as fire-and-forget tasks, so the audio arrives on a
# different task than the one that stopped the recording.
DEFAULT_FLUSH_TIMEOUT_S = 5.0

# Turn clips are uploaded one per turn per speaker, and every upload costs two calls against
# Langfuse's general API rate limit (30/min on Hobby, 100/min on Core). Cap how many turns
# get clips so a long call degrades to "the first N turns have audio" instead of a wall of
# 429s. The whole-call recording is always uploaded first.
DEFAULT_MAX_TURN_CLIPS = 40

# Uploads run a couple at a time. Higher concurrency just hits the rate limit sooner.
UPLOAD_CONCURRENCY = 2


class LangfuseRecordingUploader:
    """Uploads Pipecat call audio to Langfuse and links it to the trace and its turns.

    Args:
        host: Langfuse base URL, e.g. ``https://cloud.langfuse.com``.
        public_key: Langfuse public key, used as the HTTP Basic username.
        secret_key: Langfuse secret key, used as the HTTP Basic password.
        max_bytes: Truncate the whole-call recording beyond this many bytes of PCM.
        max_turn_clips: Upload per-turn audio for at most this many turns.
        flush_timeout_s: How long to wait for the final audio event after stopping.
    """

    def __init__(
        self,
        host: str,
        public_key: str,
        secret_key: str,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_turn_clips: int = DEFAULT_MAX_TURN_CLIPS,
        flush_timeout_s: float = DEFAULT_FLUSH_TIMEOUT_S,
    ):
        self._host = host.rstrip("/")
        self._auth = aiohttp.BasicAuth(public_key, secret_key)
        self._max_bytes = max_bytes
        self._max_turn_clips = max_turn_clips
        self._flush_timeout_s = flush_timeout_s

        # Whole-call recording.
        self._pcm = bytearray()
        self._sample_rate: Optional[int] = None
        self._num_channels: Optional[int] = None
        self._truncated = False
        self._audio_ready = asyncio.Event()

        # Per-turn clips: {turn_number: {"input": pcm, "output": pcm}}.
        self._turn_clips: dict[int, dict[str, bytes]] = {}
        self._turn_sample_rate: Optional[int] = None
        self._current_turn = 0

        # Captured while the pipeline is still running, see stop_and_collect().
        self._trace_id: Optional[str] = None

    def attach(self, audio_buffer: AudioBufferProcessor, turn_tracker=None) -> None:
        """Capture audio from the processor.

        Construct the processor with ``num_channels=2`` for a stereo whole-call recording
        (user left, bot right), and ``enable_turn_audio=True`` to also get per-turn clips.

        Args:
            audio_buffer: The pipeline's ``AudioBufferProcessor``.
            turn_tracker: The worker's ``turn_tracking_observer``. Needed to number the turn
                clips so they can be matched to their spans. Without it, only the whole-call
                recording is uploaded.
        """
        self._register_full_recording(audio_buffer)

        if turn_tracker is None:
            logger.debug("Langfuse recording: no turn tracker, per-turn audio disabled")
            return

        @turn_tracker.event_handler("on_turn_started")
        async def on_turn_started(tracker, turn_number: int):
            self._current_turn = turn_number

        self._register_turn_clips(audio_buffer)

    def _register_full_recording(self, audio_buffer: AudioBufferProcessor) -> None:
        @audio_buffer.event_handler("on_audio_data")
        async def on_audio_data(
            buffer: AudioBufferProcessor,
            audio: bytes,
            sample_rate: int,
            num_channels: int,
        ):
            if num_channels != 2:
                logger.warning(
                    f"Langfuse recording: num_channels={num_channels}; use num_channels=2 "
                    "for a stereo (user left / bot right) recording that preserves barge-in"
                )

            self._sample_rate = sample_rate
            self._num_channels = num_channels

            remaining = self._max_bytes - len(self._pcm)
            if remaining <= 0:
                self._truncated = True
            elif len(audio) > remaining:
                self._pcm.extend(audio[:remaining])
                self._truncated = True
            else:
                self._pcm.extend(audio)

            self._audio_ready.set()

    def _register_turn_clips(self, audio_buffer: AudioBufferProcessor) -> None:
        # Turn audio arrives mono, one buffer per speaker per turn. The user's clip is the
        # turn's input and the bot's is its output, which is how they are filed in Langfuse.
        @audio_buffer.event_handler("on_user_turn_audio_data")
        async def on_user_turn_audio_data(buffer, audio, sample_rate: int, num_channels: int):
            self._store_turn_clip("input", bytes(audio), sample_rate)

        @audio_buffer.event_handler("on_bot_turn_audio_data")
        async def on_bot_turn_audio_data(buffer, audio, sample_rate: int, num_channels: int):
            self._store_turn_clip("output", bytes(audio), sample_rate)

    def _store_turn_clip(self, field: str, audio: bytes, sample_rate: int) -> None:
        if not audio or not self._current_turn:
            return
        self._turn_sample_rate = sample_rate
        self._turn_clips.setdefault(self._current_turn, {})[field] = audio

    async def stop_and_collect(self, audio_buffer: AudioBufferProcessor, worker=None) -> None:
        """Stop recording and wait for the final audio event.

        Call this while the pipeline is still running, before cancelling the worker. The
        upload itself can happen later.

        Args:
            audio_buffer: The pipeline's ``AudioBufferProcessor``.
            worker: The ``PipelineWorker``. Passing it lets the trace id be read while the
                spans are still open, which is the most reliable moment to do it.
        """
        if worker is not None:
            self._trace_id = self._resolve_trace_id(getattr(worker, "turn_trace_observer", None))

        try:
            await audio_buffer.stop_recording()
            await asyncio.wait_for(self._audio_ready.wait(), timeout=self._flush_timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                f"Langfuse recording: no audio within {self._flush_timeout_s}s of stopping"
            )
        except Exception as e:
            logger.warning(f"Langfuse recording: could not collect audio: {e}")

    async def upload(self, worker) -> None:
        """Upload the recording and per-turn clips, and link them to the trace.

        Safe to call after the pipeline has shut down. Never raises: a recording that fails
        to upload must not turn into a failed call.

        Args:
            worker: The ``PipelineWorker`` that ran the conversation.
        """
        try:
            await self._upload(worker)
        except Exception as e:
            logger.warning(f"Langfuse recording: upload failed, continuing without audio: {e}")

    async def _upload(self, worker) -> None:
        trace_observer = getattr(worker, "turn_trace_observer", None)
        if trace_observer is None:
            logger.debug("Langfuse recording: tracing is off, skipping upload")
            return

        turn_contexts = self._collect_turn_contexts(trace_observer)
        trace_id = self._trace_id or self._resolve_trace_id(trace_observer)
        if not trace_id:
            logger.warning("Langfuse recording: no trace id available, skipping upload")
            return

        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)
            uploads = [self._upload_full_recording(session, semaphore, trace_id)]
            uploads += self._turn_uploads(session, semaphore, trace_id, turn_contexts)
            results = await asyncio.gather(*uploads, return_exceptions=True)

        attached = sum(1 for r in results if r is True)
        logger.info(
            f"Langfuse recording: attached {attached}/{len(results)} clips to trace {trace_id}"
        )

    def _collect_turn_contexts(self, trace_observer) -> dict:
        """Map turn number to its span context, using only public observer API."""
        contexts = {}
        for turn_number in sorted(self._turn_clips):
            context = trace_observer.get_turn_context(turn_number)
            if context is not None:
                contexts[turn_number] = context
        return contexts

    def _resolve_trace_id(self, trace_observer) -> Optional[str]:
        """Find the trace id, preferring public observer API.

        Tries, in order: any recorded turn's context (retained for the life of the observer,
        so this works long after the spans close), the live turn context, and finally the
        conversation span. The conversation span is public from pipecat-ai/pipecat#5272
        onward; older releases only have the private attribute.
        """
        if trace_observer is None:
            return None

        for turn_number in range(1, max(self._current_turn, 10) + 1):
            context = trace_observer.get_turn_context(turn_number)
            if context is not None:
                return format(context.trace_id, "032x")

        context = trace_observer.get_current_turn_context()
        if context is not None:
            return format(context.trace_id, "032x")

        span = getattr(trace_observer, "conversation_span", None) or getattr(
            trace_observer, "_conversation_span", None
        )
        if span is not None:
            return format(span.get_span_context().trace_id, "032x")
        return None

    async def _upload_full_recording(self, session, semaphore, trace_id: str) -> bool:
        if not self._pcm or not self._sample_rate:
            logger.warning("Langfuse recording: recording was empty, nothing to upload")
            return False

        if self._truncated:
            logger.warning(
                f"Langfuse recording: truncated at {self._max_bytes} bytes of PCM; "
                "the uploaded audio is shorter than the call"
            )

        wav = await asyncio.to_thread(
            _pcm_to_wav, bytes(self._pcm), self._sample_rate, self._num_channels or 1
        )
        async with semaphore:
            media_id = await self._upload_one(session, wav, trace_id, None, "output")
        if media_id:
            duration = len(self._pcm) / (
                self._sample_rate * SAMPLE_WIDTH_BYTES * (self._num_channels or 1)
            )
            logger.info(
                f"Langfuse recording: whole call attached "
                f"(mediaId={media_id}, {duration:.1f}s, trace {trace_id})"
            )
        return bool(media_id)

    def _turn_uploads(self, session, semaphore, trace_id: str, turn_contexts: dict) -> list:
        uploads = []
        dropped = 0
        for turn_number, clips in sorted(self._turn_clips.items()):
            context = turn_contexts.get(turn_number)
            if context is None:
                continue
            if len(uploads) >= self._max_turn_clips * 2:
                dropped += len(clips)
                continue
            observation_id = format(context.span_id, "016x")
            for field, pcm in clips.items():
                uploads.append(
                    self._upload_turn_clip(
                        session, semaphore, trace_id, observation_id, field, pcm, turn_number
                    )
                )
        if dropped:
            logger.warning(
                f"Langfuse recording: skipped {dropped} turn clips past the "
                f"max_turn_clips={self._max_turn_clips} cap to stay under the API rate limit"
            )
        return uploads

    async def _upload_turn_clip(
        self, session, semaphore, trace_id, observation_id, field, pcm, turn_number
    ) -> bool:
        # Turn audio is always mono, one speaker per clip.
        wav = await asyncio.to_thread(_pcm_to_wav, pcm, self._turn_sample_rate or 24000, 1)
        async with semaphore:
            media_id = await self._upload_one(session, wav, trace_id, observation_id, field)
        if media_id:
            logger.debug(
                f"Langfuse recording: turn {turn_number} {field} attached (mediaId={media_id})"
            )
        return bool(media_id)

    async def _upload_one(
        self,
        session: aiohttp.ClientSession,
        wav: bytes,
        trace_id: str,
        observation_id: Optional[str],
        field: str,
    ) -> Optional[str]:
        """Run Langfuse's three-call media upload. Returns the mediaId, or None."""
        # Langfuse validates a base64 SHA-256 digest, not hex.
        digest = base64.b64encode(hashlib.sha256(wav).digest()).decode()

        body = {
            "traceId": trace_id,
            "contentType": "audio/wav",
            "contentLength": len(wav),
            "sha256Hash": digest,
            "field": field,
        }
        if observation_id:
            body["observationId"] = observation_id

        payload = await self._post_media(session, body)
        if payload is None:
            return None

        media_id = payload["mediaId"]
        upload_url = payload.get("uploadUrl")

        # The media API is content addressed. Identical bytes return the same mediaId with a
        # null uploadUrl, already linked, so there is nothing left to upload.
        if not upload_url:
            return media_id

        started_at = time.monotonic()
        async with session.put(
            upload_url,
            data=wav,
            headers={"Content-Type": "audio/wav", "x-amz-checksum-sha256": digest},
        ) as response:
            upload_status = response.status
            if upload_status >= 400:
                logger.warning(
                    f"Langfuse recording: upload failed ({upload_status}): {await response.text()}"
                )
                return None
        upload_ms = int((time.monotonic() - started_at) * 1000)

        # Reporting success is what lets a later upload of identical bytes short circuit.
        async with session.patch(
            f"{self._host}/api/public/media/{media_id}",
            json={
                "uploadedAt": datetime.now(timezone.utc).isoformat(),
                "uploadHttpStatus": upload_status,
                "uploadTimeMs": upload_ms,
            },
            auth=self._auth,
        ) as response:
            if response.status >= 400:
                logger.warning(f"Langfuse recording: could not confirm upload ({response.status})")

        return media_id

    async def _post_media(self, session: aiohttp.ClientSession, body: dict) -> Optional[dict]:
        """Request an upload URL, retrying once if we are rate limited."""
        for attempt in (1, 2):
            async with session.post(
                f"{self._host}/api/public/media", json=body, auth=self._auth
            ) as response:
                if response.status == 429 and attempt == 1:
                    delay = float(response.headers.get("Retry-After", 2))
                    logger.warning(
                        f"Langfuse recording: rate limited, retrying in {delay:.0f}s. "
                        "Lower max_turn_clips if this keeps happening."
                    )
                    await asyncio.sleep(min(delay, 10))
                    continue
                if response.status >= 400:
                    logger.warning(
                        f"Langfuse recording: media request failed ({response.status}): "
                        f"{await response.text()}"
                    )
                    return None
                return await response.json()
        return None


def _pcm_to_wav(pcm: bytes, sample_rate: int, num_channels: int) -> bytes:
    """Wrap raw s16le PCM in a WAV container."""
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm)
        return buffer.getvalue()


def uploader_from_env() -> Optional[LangfuseRecordingUploader]:
    """Build an uploader from LANGFUSE_* env vars, or None if they are not all set."""
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        logger.info(
            "Langfuse recording disabled: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY "
            "to attach call audio to traces"
        )
        return None

    _warn_on_region_mismatch(host)

    return LangfuseRecordingUploader(host=host, public_key=public_key, secret_key=secret_key)


def _warn_on_region_mismatch(host: str) -> None:
    """Warn when the media host and the OTLP endpoint point at different Langfuse regions.

    Spans and media travel over two different URLs. If they disagree, the audio lands in a
    different project than the trace and no player appears, with no error anywhere.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    media_host = urlparse(host).netloc
    otlp_host = urlparse(endpoint).netloc
    if media_host and otlp_host and media_host != otlp_host:
        logger.warning(
            f"Langfuse recording: LANGFUSE_HOST ({media_host}) and "
            f"OTEL_EXPORTER_OTLP_ENDPOINT ({otlp_host}) are different hosts. The recording "
            "will upload to a different project than the trace, so no audio player will "
            "appear. Point both at the same region."
        )
