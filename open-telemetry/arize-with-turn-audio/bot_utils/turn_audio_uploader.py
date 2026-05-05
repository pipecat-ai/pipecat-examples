#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Per-turn audio uploader for S3 with presigned-URL-up-front strategy.

For each turn segment:
1. Compute a deterministic S3 key.
2. Generate a presigned GET URL synchronously (no S3 round-trip).
3. Return the URL immediately so it can be attached as a span attribute.
4. Kick off the actual `put_object` upload as a background task.

The link 404s until the upload lands, and dies if the upload fails — both
acceptable trade-offs for trace-first artifact persistence.
"""

import asyncio
import io
import os
import wave

import boto3
from loguru import logger


class TurnAudioUploader:
    """Uploads per-turn audio segments to S3 and returns presigned URLs synchronously."""

    def __init__(self, conversation_id: str, s3_key_prefix: str, url_expiry_seconds: int = 7 * 24 * 3600):
        """Initialize the turn audio uploader.

        Args:
            conversation_id: UUID of the conversation; used in the S3 key.
            s3_key_prefix: Path prefix inside the bucket (e.g. "conversations").
            url_expiry_seconds: Lifetime of the presigned GET URL.
        """
        self._conversation_id = conversation_id
        self._s3_key_prefix = s3_key_prefix.rstrip("/")
        self._url_expiry_seconds = url_expiry_seconds
        self._bucket_name = os.getenv("AWS_BUCKET_NAME")

        # Long-lived IAM-user credentials picked up from the environment by boto3.
        # (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION)
        self._s3_client = boto3.client("s3")

    def _wav_bytes(self, audio: bytes, sample_rate: int, num_channels: int) -> bytes:
        with io.BytesIO() as buffer:
            with wave.open(buffer, "wb") as wf:
                wf.setsampwidth(2)
                wf.setnchannels(num_channels)
                wf.setframerate(sample_rate)
                wf.writeframes(audio)
            return buffer.getvalue()

    def _build_key(self, turn_number: int, role: str) -> str:
        return f"{self._s3_key_prefix}/{self._conversation_id}/turn-{turn_number:04d}/{role}.wav"

    def get_presigned_url_and_upload(
        self, audio: bytes, sample_rate: int, num_channels: int, turn_number: int, role: str
    ) -> str:
        """Return a presigned URL and start the upload as a background task.

        The URL is valid as soon as the upload completes. The caller can attach
        it to a span attribute synchronously.
        """
        s3_key = self._build_key(turn_number, role)

        url = self._s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_name, "Key": s3_key},
            ExpiresIn=self._url_expiry_seconds,
        )

        body = self._wav_bytes(audio, sample_rate, num_channels)
        asyncio.create_task(self._put_object(s3_key, body))
        return url

    async def _put_object(self, s3_key: str, body: bytes):
        try:
            await asyncio.to_thread(
                self._s3_client.put_object,
                Bucket=self._bucket_name,
                Key=s3_key,
                Body=body,
                ContentType="audio/wav",
            )
            logger.info(f"Uploaded turn audio to s3://{self._bucket_name}/{s3_key}")
        except Exception as e:
            logger.error(f"Failed to upload turn audio to s3://{self._bucket_name}/{s3_key}: {e}")
