#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Attach a conversation recording to a Langfuse trace.

Pipecat sends spans to Langfuse over OTLP, but Langfuse media (the audio player you see
in the trace view) does not travel over OTLP. Media is uploaded out of band to object
storage and referenced from the trace payload by a token:

    @@@langfuseMedia:type=audio/wav|id=<mediaId>|source=bytes@@@

So this module does two things: it uploads the WAV through Langfuse's three-call media
API, and it writes the resulting token onto the still-open ``conversation`` span as
``langfuse.trace.output``, which Langfuse maps to the trace's output field.

Timing matters here. Langfuse treats persisted traces as immutable, with no update by
id, so the token has to be on the span *before* the span ends. Pipecat ends the
conversation span inside ``PipelineWorker._cleanup()``, so the safe place to call
:meth:`LangfuseRecordingUploader.finalize` is the transport's ``on_client_disconnected``
handler, before ``worker.cancel()``.

See https://langfuse.com/docs/observability/features/multi-modality
"""

import asyncio
import base64
import hashlib
import io
import json
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

# Langfuse rejects uploads over its configured limit with a 400. The open-source default
# is 1GB, but a voice agent has no business buffering that much: stereo 24kHz s16 is
# roughly 350MB/hour, so cap it well below and truncate loudly instead of exhausting the
# container.
DEFAULT_MAX_BYTES = 100 * 1024 * 1024

# How long to wait after stop_recording() for the final on_audio_data event. Pipecat
# dispatches async event handlers as fire-and-forget tasks, so the audio arrives on a
# different task than the one that stopped the recording.
DEFAULT_FLUSH_TIMEOUT_S = 5.0


class LangfuseRecordingUploader:
    """Uploads an ``AudioBufferProcessor`` recording to Langfuse and links it to the trace.

    Args:
        host: Langfuse base URL, e.g. ``https://cloud.langfuse.com``.
        public_key: Langfuse public key, used as the HTTP Basic username.
        secret_key: Langfuse secret key, used as the HTTP Basic password.
        field: Which trace field carries the media, ``output`` or ``metadata``.
        max_bytes: Truncate the recording beyond this many bytes of PCM.
        flush_timeout_s: How long to wait for the final audio event after stopping.
    """

    def __init__(
        self,
        host: str,
        public_key: str,
        secret_key: str,
        field: str = "output",
        max_bytes: int = DEFAULT_MAX_BYTES,
        flush_timeout_s: float = DEFAULT_FLUSH_TIMEOUT_S,
    ):
        if field not in ("output", "metadata"):
            raise ValueError(f"field must be 'output' or 'metadata', got {field!r}")

        self._host = host.rstrip("/")
        self._auth = aiohttp.BasicAuth(public_key, secret_key)
        self._field = field
        self._max_bytes = max_bytes
        self._flush_timeout_s = flush_timeout_s

        self._audio_buffer: Optional[AudioBufferProcessor] = None
        self._pcm = bytearray()
        self._sample_rate: Optional[int] = None
        self._num_channels: Optional[int] = None
        self._truncated = False
        self._audio_ready = asyncio.Event()

    def attach(self, audio_buffer: AudioBufferProcessor) -> None:
        """Capture the merged audio this processor produces.

        Construct the processor with ``num_channels=2`` so the recording is stereo, user
        on the left and bot on the right. That is what makes a barge-in audible as
        overlap rather than as a gap.
        """
        self._audio_buffer = audio_buffer

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

    async def finalize(self, conversation_span) -> None:
        """Stop recording, upload the WAV, and reference it from the trace.

        Never raises. A recording that fails to upload must not take down a call, so
        every failure path logs and returns.

        Args:
            conversation_span: The open OpenTelemetry ``conversation`` span. Pass ``None``
                to skip, e.g. when tracing is disabled.
        """
        try:
            await self._finalize(conversation_span)
        except Exception as e:
            logger.warning(f"Langfuse recording: upload failed, continuing without audio: {e}")

    async def _finalize(self, conversation_span) -> None:
        if conversation_span is None:
            logger.debug("Langfuse recording: no conversation span, skipping upload")
            return

        pcm = await self._collect_pcm()
        if not pcm:
            return

        wav = await asyncio.to_thread(_pcm_to_wav, pcm, self._sample_rate, self._num_channels or 1)
        if self._truncated:
            logger.warning(
                f"Langfuse recording: truncated at {self._max_bytes} bytes of PCM; "
                "the uploaded audio is shorter than the call"
            )

        trace_id = format(conversation_span.get_span_context().trace_id, "032x")

        media_id = await self._upload(wav, trace_id)
        if not media_id:
            return

        token = f"@@@langfuseMedia:type=audio/wav|id={media_id}|source=bytes@@@"
        if self._field == "output":
            # The token has to be the whole string value. Langfuse's renderer gives up
            # and prints the raw token if anything else surrounds it, so never build a
            # sentence around it.
            conversation_span.set_attribute(
                "langfuse.trace.output", json.dumps({"recording": token})
            )
        else:
            conversation_span.set_attribute("langfuse.trace.metadata.recording", token)

        duration_s = len(pcm) / (
            (self._sample_rate or 1) * SAMPLE_WIDTH_BYTES * (self._num_channels or 1)
        )
        logger.info(
            f"Langfuse recording attached: mediaId={media_id} "
            f"({len(wav)} bytes, {duration_s:.1f}s, trace {trace_id})"
        )

    async def _collect_pcm(self) -> bytes:
        """Stop the recording and wait for the final audio event."""
        if self._audio_buffer is None:
            logger.debug("Langfuse recording: nothing attached, skipping upload")
            return b""

        await self._audio_buffer.stop_recording()

        # stop_recording() flushes the audio by firing on_audio_data as a task and does
        # not await it, so wait for our handler to actually run.
        try:
            await asyncio.wait_for(self._audio_ready.wait(), timeout=self._flush_timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                f"Langfuse recording: no audio within {self._flush_timeout_s}s of stopping"
            )
            return b""

        if not self._pcm or not self._sample_rate:
            logger.warning("Langfuse recording: recording was empty, nothing to upload")
            return b""

        return bytes(self._pcm)

    async def _upload(self, wav: bytes, trace_id: str) -> Optional[str]:
        """Run Langfuse's three-call media upload. Returns the mediaId, or None."""
        # Langfuse validates a base64 SHA-256 digest, not hex.
        digest = base64.b64encode(hashlib.sha256(wav).digest()).decode()

        # No session-level auth: the presigned PUT goes to object storage and must not
        # carry a Langfuse Authorization header.
        async with aiohttp.ClientSession() as session:
            body = {
                "traceId": trace_id,
                "contentType": "audio/wav",
                "contentLength": len(wav),
                "sha256Hash": digest,
                "field": self._field,
            }
            async with session.post(
                f"{self._host}/api/public/media", json=body, auth=self._auth
            ) as response:
                if response.status >= 400:
                    logger.warning(
                        f"Langfuse recording: media request failed "
                        f"({response.status}): {await response.text()}"
                    )
                    return None
                payload = await response.json()

            media_id = payload["mediaId"]
            upload_url = payload.get("uploadUrl")

            # The media API is content addressed. Identical bytes return the same
            # mediaId with a null uploadUrl, already linked to this trace, so there is
            # nothing left to upload.
            if not upload_url:
                logger.debug(f"Langfuse recording: mediaId={media_id} already uploaded")
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
                        f"Langfuse recording: upload failed "
                        f"({upload_status}): {await response.text()}"
                    )
                    return None
            upload_ms = int((time.monotonic() - started_at) * 1000)

            # Reporting success is what lets a later upload of identical bytes short
            # circuit, so do not skip this.
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
                    logger.warning(
                        f"Langfuse recording: could not confirm upload "
                        f"({response.status}): {await response.text()}"
                    )

            return media_id


def _pcm_to_wav(pcm: bytes, sample_rate: int, num_channels: int) -> bytes:
    """Wrap raw s16le PCM in a WAV container."""
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm)
        return buffer.getvalue()


def uploader_from_env(field: str = "output") -> Optional[LangfuseRecordingUploader]:
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

    return LangfuseRecordingUploader(
        host=host, public_key=public_key, secret_key=secret_key, field=field
    )


def _warn_on_region_mismatch(host: str) -> None:
    """Warn when the media host and the OTLP endpoint point at different Langfuse regions.

    Spans and media travel over two different URLs. If they disagree, the audio lands in a
    different project than the trace and the player never appears, with no error anywhere.
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
