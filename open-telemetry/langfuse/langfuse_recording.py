#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Attach call audio to a Langfuse trace.

Pipecat sends spans to Langfuse over OTLP, but media does not travel over OTLP.
Audio goes up separately through the media REST API and is linked to a trace, or
to a single observation inside it, by id. Langfuse renders a player from that
link alone, so nothing has to be written into the span payload and no span has
to still be open.

That gives two levels of playback:

- The whole call, linked to the trace and playable from the trace root.
- Each turn, linked to that turn's ``turn`` span. The user's speech lands on the
  span's ``input`` and the bot's reply on its ``output``, so clicking a turn in
  the Langfuse UI plays just that turn.

Because linking is by id, all uploading happens after the pipeline has shut
down. Turn span ids stay reachable through ``TurnTraceObserver.get_turn_context()``,
which retains them for the life of the observer.

The media API is called directly over aiohttp. The ``langfuse`` package is not
used: its client starts a second OpenTelemetry tracer provider, which conflicts
with Pipecat's ``setup_tracing()``, and its ``LangfuseMedia`` class only uploads
media embedded in spans the Langfuse SDK itself created.

See https://langfuse.com/docs/observability/features/multi-modality
"""

import asyncio
import base64
import hashlib
import os
import time
from datetime import UTC, datetime
from urllib.parse import unquote, urlparse

import aiohttp
from loguru import logger
from pipecat.audio.utils import pcm_to_wav
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor, TurnAudioData

# AudioBufferProcessor emits raw signed 16-bit PCM.
SAMPLE_WIDTH_BYTES = 2

# Stereo 24kHz s16 runs about 350MB/hour, so cap the whole-call recording well
# below what Langfuse would accept and truncate loudly rather than letting a long
# call exhaust the container.
MAX_RECORDING_BYTES = 100 * 1024 * 1024

# How long to wait after stopping for the final on_audio_data event. Pipecat
# dispatches event handlers as background tasks, so the audio lands on a
# different task than the one that stopped the recording.
FLUSH_TIMEOUT_SECS = 5.0

# Each turn clip costs two calls against Langfuse's general API rate limit
# (30/min on Hobby, 100/min on Core). Capping the number of turns that get clips
# degrades a long call to "the first N turns have audio" instead of a wall of
# 429s. Raise or drop this cap when self-hosting. The whole-call recording is
# always uploaded first.
MAX_TURN_CLIPS = 40

# Uploads run a couple at a time; more concurrency just reaches the rate limit
# sooner.
UPLOAD_CONCURRENCY = 2


class LangfuseRecorder:
    """Collects a call's audio and attaches it to the call's Langfuse trace.

    Example::

        audiobuffer = AudioBufferProcessor(
            num_channels=2, enable_turn_audio=True, auto_start_recording=True
        )
        # ... place audiobuffer in the pipeline, after transport.output() ...

        recorder = LangfuseRecorder.from_env()
        if recorder:
            recorder.attach(audiobuffer, worker)

        # While the pipeline is still running:
        await recorder.stop_and_collect()

        # After the runner returns:
        await recorder.upload()
    """

    def __init__(self, host: str, public_key: str, secret_key: str):
        """Initialize the recorder.

        Args:
            host: Langfuse base URL, e.g. ``https://cloud.langfuse.com``.
            public_key: Langfuse public key, used as the HTTP Basic username.
            secret_key: Langfuse secret key, used as the HTTP Basic password.
        """
        self._host = host.rstrip("/")
        # Built by hand so the presigned storage PUT can stay auth-free: session
        # level auth would leak onto it, and aiohttp's per-request auth= is
        # deprecated.
        credentials = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self._auth_headers = {"Authorization": f"Basic {credentials}"}

        self._audiobuffer: AudioBufferProcessor | None = None
        self._worker: PipelineWorker | None = None
        self._auth_failed = False

        # Whole-call recording.
        self._pcm = bytearray()
        self._sample_rate: int | None = None
        self._num_channels: int = 2
        self._truncated = False
        self._audio_ready = asyncio.Event()

        # Per-turn clips, as {turn_number: {"input": pcm, "output": pcm}}.
        self._turn_clips: dict[int, dict[str, bytes]] = {}
        self._turn_sample_rate: int | None = None

    @classmethod
    def from_env(cls) -> "LangfuseRecorder | None":
        """Build a recorder from the environment, or None if there are no keys.

        Prefers ``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY`` / ``LANGFUSE_HOST``.
        Falls back to the credentials and host the span exporter already uses,
        read from ``OTEL_EXPORTER_OTLP_HEADERS`` and ``OTEL_EXPORTER_OTLP_ENDPOINT``.
        Media and spans have to reach the same Langfuse project or the audio
        attaches to nothing, and deriving both from one source is the only way to
        guarantee that.
        """
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        source = "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY"

        if not public_key or not secret_key:
            credentials = _credentials_from_otlp_headers()
            if credentials:
                public_key, secret_key = credentials
                source = "OTEL_EXPORTER_OTLP_HEADERS"

        if not public_key or not secret_key:
            logger.info(
                "Langfuse recording disabled: set LANGFUSE_PUBLIC_KEY and "
                "LANGFUSE_SECRET_KEY to attach call audio to traces"
            )
            return None

        host = os.getenv("LANGFUSE_HOST")
        if host:
            _warn_on_region_mismatch(host)
        else:
            host = _host_from_otlp_endpoint() or "https://cloud.langfuse.com"

        logger.debug(f"Langfuse recording: uploading to {host}, keys from {source}")

        return cls(host=host, public_key=public_key, secret_key=secret_key)

    def attach(self, audiobuffer: AudioBufferProcessor, worker: PipelineWorker) -> None:
        """Start collecting audio from the pipeline.

        Args:
            audiobuffer: The pipeline's audio buffer processor. Construct it with
                ``num_channels=2`` for a stereo whole-call recording (user left,
                bot right) and ``enable_turn_audio=True`` for per-turn clips.
            worker: The worker running the conversation, which holds the trace
                everything is attached to.
        """
        self._audiobuffer = audiobuffer
        self._worker = worker

        @audiobuffer.event_handler("on_audio_data")
        async def on_audio_data(buffer, audio: bytes, sample_rate: int, num_channels: int):
            if num_channels != 2:
                logger.warning(
                    f"Langfuse recording: num_channels={num_channels}; use num_channels=2 "
                    "for a stereo (user left / bot right) recording that preserves barge-in"
                )

            self._sample_rate = sample_rate
            self._num_channels = num_channels

            remaining = MAX_RECORDING_BYTES - len(self._pcm)
            if remaining <= 0:
                self._truncated = True
            elif len(audio) > remaining:
                self._pcm.extend(audio[:remaining])
                self._truncated = True
            else:
                self._pcm.extend(audio)

            self._audio_ready.set()

        # Turn audio arrives mono, once per speaker per turn. The user's speech
        # is the turn's input and the bot's reply its output, which is how they
        # are filed in Langfuse.
        @audiobuffer.event_handler("on_user_turn_audio")
        async def on_user_turn_audio(buffer, turn: TurnAudioData):
            self._store_turn_clip(turn, "input")

        @audiobuffer.event_handler("on_bot_turn_audio")
        async def on_bot_turn_audio(buffer, turn: TurnAudioData):
            self._store_turn_clip(turn, "output")

    def _store_turn_clip(self, turn: TurnAudioData, field: str):
        self._turn_sample_rate = turn.sample_rate
        self._turn_clips.setdefault(turn.turn_number, {})[field] = turn.audio

    async def stop_and_collect(self) -> None:
        """Stop recording and wait for the final audio.

        Call this while the pipeline is still running, before ending or
        cancelling the worker. The upload itself can happen later.
        """
        if self._audiobuffer is None:
            return

        try:
            await self._audiobuffer.stop_recording()
            await asyncio.wait_for(self._audio_ready.wait(), timeout=FLUSH_TIMEOUT_SECS)
        except TimeoutError:
            logger.warning(f"Langfuse recording: no audio within {FLUSH_TIMEOUT_SECS}s of stopping")
        except Exception as e:
            logger.warning(f"Langfuse recording: could not collect audio: {e}")

    async def upload(self) -> None:
        """Upload the recording and turn clips and link them to the trace.

        Safe to call after the pipeline has shut down. Never raises: a recording
        that fails to upload must not turn into a failed call.
        """
        try:
            await self._upload()
        except Exception as e:
            logger.warning(f"Langfuse recording: upload failed, continuing without audio: {e}")

    async def _upload(self) -> None:
        if self._worker is None:
            return

        trace_observer = self._worker.turn_trace_observer
        if trace_observer is None:
            logger.debug("Langfuse recording: tracing is off, skipping upload")
            return

        trace_id = self._resolve_trace_id(trace_observer)
        if not trace_id:
            logger.warning("Langfuse recording: no trace id available, skipping upload")
            return

        async with aiohttp.ClientSession() as session:
            semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY)
            uploads = [self._upload_recording(session, semaphore, trace_id)]
            uploads += self._turn_uploads(session, semaphore, trace_id, trace_observer)
            results = await asyncio.gather(*uploads, return_exceptions=True)

        attached = sum(1 for r in results if r is True)
        logger.info(
            f"Langfuse recording: attached {attached}/{len(results)} clips to trace {trace_id}"
        )

    def _resolve_trace_id(self, trace_observer) -> str | None:
        """Find the trace to attach audio to.

        Every span in the call shares one trace id, so any turn span will do.
        Recorded turns come first because the observer retains their contexts for
        its whole life, which still works long after the spans have closed. Turn
        1 opens with the pipeline, so it covers a recording with no turn clips of
        its own — a whole-call recording made with ``enable_turn_audio=False``.
        """
        for turn_number in (*sorted(self._turn_clips), 1):
            context = trace_observer.get_turn_context(turn_number)
            if context is not None:
                return format(context.trace_id, "032x")

        context = trace_observer.get_current_turn_context()
        if context is not None:
            return format(context.trace_id, "032x")

        return None

    async def _upload_recording(self, session, semaphore, trace_id: str) -> bool:
        if not self._pcm or not self._sample_rate:
            logger.warning("Langfuse recording: recording was empty, nothing to upload")
            return False

        if self._truncated:
            logger.warning(
                f"Langfuse recording: truncated at {MAX_RECORDING_BYTES} bytes of PCM; "
                "the uploaded audio is shorter than the call"
            )

        wav = await asyncio.to_thread(
            pcm_to_wav, bytes(self._pcm), self._sample_rate, self._num_channels
        )
        async with semaphore:
            media_id = await self._upload_one(session, wav, trace_id, None, "output")

        if media_id:
            seconds = len(self._pcm) / (self._sample_rate * SAMPLE_WIDTH_BYTES * self._num_channels)
            logger.info(
                f"Langfuse recording: whole call attached "
                f"(mediaId={media_id}, {seconds:.1f}s, trace {trace_id})"
            )
        return bool(media_id)

    def _turn_uploads(self, session, semaphore, trace_id: str, trace_observer) -> list:
        uploads = []
        dropped = 0
        for turn_number, clips in sorted(self._turn_clips.items()):
            context = trace_observer.get_turn_context(turn_number)
            if context is None:
                continue
            if len(uploads) >= MAX_TURN_CLIPS * 2:
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
                f"MAX_TURN_CLIPS={MAX_TURN_CLIPS} cap to stay under the API rate limit"
            )
        return uploads

    async def _upload_turn_clip(
        self, session, semaphore, trace_id, observation_id, field, pcm, turn_number
    ) -> bool:
        # Turn audio is always mono, one speaker per clip.
        wav = await asyncio.to_thread(pcm_to_wav, pcm, self._turn_sample_rate or 24000, 1)
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
        observation_id: str | None,
        field: str,
    ) -> str | None:
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

        payload = await self._request_upload(session, body)
        if payload is None:
            return None

        media_id = payload["mediaId"]
        upload_url = payload.get("uploadUrl")

        # The media API is content addressed. Identical bytes come back with the
        # same mediaId and a null uploadUrl, already linked, so there is nothing
        # left to send.
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

        # Reporting success is what lets a later upload of identical bytes skip
        # the transfer.
        async with session.patch(
            f"{self._host}/api/public/media/{media_id}",
            json={
                "uploadedAt": datetime.now(UTC).isoformat(),
                "uploadHttpStatus": upload_status,
                "uploadTimeMs": upload_ms,
            },
            headers=self._auth_headers,
        ) as response:
            if response.status >= 400:
                logger.warning(f"Langfuse recording: could not confirm upload ({response.status})")

        return media_id

    async def _request_upload(self, session: aiohttp.ClientSession, body: dict) -> dict | None:
        """Ask for an upload URL, retrying once if we are rate limited."""
        # Rejected credentials reject every clip, so report them once rather than
        # once per clip.
        if self._auth_failed:
            return None

        for attempt in (1, 2):
            async with session.post(
                f"{self._host}/api/public/media", json=body, headers=self._auth_headers
            ) as response:
                if response.status in (401, 403):
                    self._auth_failed = True
                    logger.error(
                        f"Langfuse recording: {self._host} rejected the credentials "
                        f"({response.status}). Traces still upload over OTLP, which "
                        "authenticates separately, so check that LANGFUSE_PUBLIC_KEY and "
                        "LANGFUSE_SECRET_KEY belong to the same project as "
                        "OTEL_EXPORTER_OTLP_ENDPOINT — or unset them and let the recorder "
                        "read the keys from OTEL_EXPORTER_OTLP_HEADERS."
                    )
                    return None
                if response.status == 429 and attempt == 1:
                    delay = float(response.headers.get("Retry-After", 2))
                    logger.warning(
                        f"Langfuse recording: rate limited, retrying in {delay:.0f}s. "
                        "Lower MAX_TURN_CLIPS if this keeps happening."
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


def _credentials_from_otlp_headers() -> tuple[str, str] | None:
    """Recover the Langfuse key pair from the OTLP exporter's auth header.

    Langfuse authenticates the OTLP endpoint with HTTP Basic over the same key
    pair the REST API wants, so the header the span exporter is already using
    carries everything the media upload needs.
    """
    raw = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
    if not raw:
        return None

    for header in raw.split(","):
        name, _, value = header.partition("=")
        if name.strip().lower() != "authorization":
            continue
        # The value is percent-encoded, so the space after "Basic" often arrives
        # as %20.
        scheme, _, token = unquote(value.strip()).partition(" ")
        if scheme.lower() != "basic":
            continue
        try:
            public_key, _, secret_key = base64.b64decode(token).decode().partition(":")
        except (ValueError, UnicodeDecodeError):
            return None
        if public_key and secret_key:
            return public_key, secret_key
    return None


def _host_from_otlp_endpoint() -> str | None:
    """The Langfuse base URL implied by the OTLP endpoint, if one is set."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _warn_on_region_mismatch(host: str) -> None:
    """Warn when the media host and the OTLP endpoint point at different regions.

    Spans and media travel over two different URLs. When they disagree the audio
    lands in a different project than the trace and no player appears, with no
    error anywhere.
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
