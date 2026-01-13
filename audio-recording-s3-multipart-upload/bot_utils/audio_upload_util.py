import asyncio
import io
import os
import struct
import time
import wave
from typing import Optional

import boto3
from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
)
from pipecat.processors.frame_processor import FrameProcessor


class AudioUploader:
    """Util to manage audio uploads"""

    def __init__(self, conversation_id: str, audio_buffer_size: int, s3_key: str):
        """Initializes AudioUploader. Manages multipart and standalone file uploads
        to an AWS s3 bucket.

        Args:
            conversation_id: UUID of the conversation; used for audio filename.
            audio_buffer_size: Size of the audio buffer chunks to upload.
            s3_key: S3 key in bucket.
        """

        self._conversation_id = conversation_id
        self._audio_buffer_size = audio_buffer_size

        self._bucket_name = os.getenv("AWS_BUCKET_NAME")
        self._s3_audio_uploader = None
        self._s3_bot_audio_uploader = None
        self._s3_user_audio_uploader = None

        # s3 key
        self._s3_conversation_artifact_path = f"{s3_key}/{self._conversation_id}/"
        self._s3_object_key_prefix = f"{self._s3_conversation_artifact_path}{self._conversation_id}"

        self._multipart_upload_started = False

        # set up s3 uploaders
        self._s3_audio_uploader = s3MultipartUploader(
            self._bucket_name, f"{self._s3_object_key_prefix}.wav"
        )
        self._s3_bot_audio_uploader = s3MultipartUploader(
            self._bucket_name, f"{self._s3_object_key_prefix}_bot.wav"
        )
        self._s3_user_audio_uploader = s3MultipartUploader(
            self._bucket_name, f"{self._s3_object_key_prefix}_user.wav"
        )

    async def upload_audio_wav_to_s3(
        self, audio: bytes, sample_rate: int, num_channels: int, suffix=None
    ):
        """
        Determines whether the audio buffer should be uploaded as part of a multipart upload
        or as a standalone audio file.
        """
        # are we saving merged audio, or by track (bot, user)
        # filename_suffix = ["", "_bot", "_user"]
        if suffix:
            filename_suffix = f"_{suffix}"
        else:
            filename_suffix = ""

        try:
            if len(audio) < self._audio_buffer_size and not self._multipart_upload_started:
                logger.info(f"`upload_audio_wav_to_s3` - upload *standalone .wav file* to s3.")
                # standalone upload
                # this is not the last part of a multipart upload and
                # audio buffer is short enough to upload standalone file to s3
                # directly write WAV to s3 bucket (`s3.put_object`)
                with io.BytesIO() as buffer:
                    with wave.open(buffer, "wb") as wf:
                        wf.setsampwidth(2)
                        wf.setnchannels(num_channels)
                        wf.setframerate(sample_rate)
                        wf.writeframes(audio)
                    s3_object_key = f"{self._s3_object_key_prefix}{filename_suffix}.wav"

                    try:
                        self._s3_audio_uploader.upload_standalone_audio(
                            s3_object_key, buffer.getvalue()
                        )

                    except Exception as e:
                        logger.error(f"Error uploading standalone audio: {e}")
            else:
                logger.info(f"`upload_audio_wav_to_s3` - upload *multipart file* to s3.")
                # multipart upload
                # this is part of a multipart upload; use `s3_audio_uploader.upload_multipart_audio`
                self._multipart_upload_started = True

                try:
                    if "" == filename_suffix:
                        await self._s3_audio_uploader.upload_multipart_audio(
                            audio, sample_rate, num_channels
                        )
                    elif "_bot" == filename_suffix:
                        await self._s3_bot_audio_uploader.upload_multipart_audio(
                            audio, sample_rate, num_channels
                        )
                    elif "_user" == filename_suffix:
                        await self._s3_user_audio_uploader.upload_multipart_audio(
                            audio, sample_rate, num_channels
                        )
                except Exception as e:
                    logger.error(f"Error uploading multipart audio: {e}")
        except Exception as e:
            logger.error(f"upload_audio_wav_to_s3 error: {e}")

    async def finalize_upload_audio_wav_to_s3(self, is_track_audio: Optional[bool] = None):
        if self._multipart_upload_started:
            logger.info(f"finalizing multipart uploads")
            await self._s3_bot_audio_uploader.finalize_multipart_upload()
            await self._s3_user_audio_uploader.finalize_multipart_upload()
            await self._s3_audio_uploader.finalize_multipart_upload()


class s3MultipartUploader:
    """Manages s3 multipart uploads"""

    def __init__(self, bucket_name: str, key: str, bits_per_sample: int = 16):
        self._bucket_name = bucket_name
        self._s3_client = self._get_s3_client()
        self.key = key
        self.sample_rate = None
        self.num_channels = None
        self.bits_per_sample = bits_per_sample

        self.upload_id: Optional[str] = None
        self.parts = []
        self.part_number = 1
        self.total_audio_bytes = 0

        # WAV format calculations
        self.bytes_per_sample = self.bits_per_sample // 8
        self.block_align = None
        self.byte_rate = None

        self._upload_in_progress = False

        self._first_chunk_audio_bytes = bytearray()

        self._saved_latest_audio_chunk_complete = asyncio.Event()
        self._saved_latest_audio_chunk_complete.set()

    # thx claude
    def _get_s3_client(self):
        sts = boto3.client("sts")

        # Use .env credentials to assume the role
        assumed = sts.assume_role(
            RoleArn=os.getenv("AWS_ROLE_ARN"),
            RoleSessionName="pipecat-upload-audio-session",
            DurationSeconds=3600,  # 1hr, refresh as needed
        )

        creds = assumed["Credentials"]
        return boto3.client(
            "s3",
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )

    # thx claude
    def _create_wav_header(self, data_size: int, sample_rate: int, num_channels: int) -> bytes:
        """Create WAV file header with known data size"""

        # WAV format calculations
        self.block_align = num_channels * self.bytes_per_sample
        self.byte_rate = sample_rate * self.block_align

        file_size = 36 + data_size  # 44 byte header - 8 bytes for RIFF chunk

        header = io.BytesIO()
        header.write(b"RIFF")
        header.write(struct.pack("<I", file_size))
        header.write(b"WAVE")
        header.write(b"fmt ")
        header.write(struct.pack("<I", 16))  # PCM format chunk size
        header.write(struct.pack("<H", 1))  # PCM format
        header.write(struct.pack("<H", num_channels))
        header.write(struct.pack("<I", sample_rate))
        header.write(struct.pack("<I", self.byte_rate))
        header.write(struct.pack("<H", self.block_align))
        header.write(struct.pack("<H", self.bits_per_sample))
        header.write(b"data")
        header.write(struct.pack("<I", data_size))

        return header.getvalue()

    def upload_standalone_audio(self, s3_object_key: str, body: str):
        """Upload a single standalone audio file to s3. (Essentially, just s3.put_object)."""

        # performance seems better if we open and close a new s3 client here
        # instead of using `self._s3_client`
        standalone_s3_client = self._get_s3_client()
        standalone_s3_client.put_object(Bucket=self._bucket_name, Key=s3_object_key, Body=body)

        logger.info(
            f"s3.put_object complete. Audio successfully written to '{self._bucket_name}/{s3_object_key}'"
        )

        standalone_s3_client.close()

    async def start_multipart_upload(self, sample_rate: int, num_channels: int):
        """Initialize a multipart upload"""

        self.sample_rate = sample_rate
        self.num_channels = num_channels

        self._upload_in_progress = True
        response = await asyncio.to_thread(
            self._s3_client.create_multipart_upload,
            Bucket=self._bucket_name,
            Key=self.key,
            ContentType="audio/wav",
        )
        self.upload_id = response["UploadId"]

        # Upload placeholder header as first part (will be replaced when we know full size of wav)
        placeholder_header = self._create_wav_header(0, sample_rate, num_channels)
        return placeholder_header

    async def upload_multipart_audio(self, audio: bytes, sample_rate: int, num_channels: int):
        """Callback to save audio chunk"""
        self._saved_latest_audio_chunk_complete.clear()

        body = audio
        if not self.upload_id:
            header = await self.start_multipart_upload(sample_rate, num_channels)
            body = header + audio
            self._first_chunk_audio_bytes = audio

        # Upload audio chunk as next part
        response = await asyncio.to_thread(
            self._s3_client.upload_part,
            Bucket=self._bucket_name,
            Key=self.key,
            PartNumber=self.part_number,
            UploadId=self.upload_id,
            Body=body,
        )

        self.parts.append({"ETag": response["ETag"], "PartNumber": self.part_number})
        self.part_number += 1
        self.total_audio_bytes += len(audio)

        self._saved_latest_audio_chunk_complete.set()

    async def finalize_multipart_upload(self):
        """Complete the multipart upload with correct WAV header"""
        if not self.upload_id:
            logger.debug(f"No upload in progress")
            return

        # wait for last audio chunk to be uploaded
        await self._saved_latest_audio_chunk_complete.wait()

        # Create correct header with final audio data size
        correct_header = self._create_wav_header(
            self.total_audio_bytes, self.sample_rate, self.num_channels
        )

        # Replace the first part with correct header
        response = self._s3_client.upload_part(
            Bucket=self._bucket_name,
            Key=self.key,
            PartNumber=1,
            UploadId=self.upload_id,
            Body=correct_header + self._first_chunk_audio_bytes,
        )

        # Update first part's ETag
        self.parts[0]["ETag"] = response["ETag"]

        # Complete multipart upload
        response = self._s3_client.complete_multipart_upload(
            Bucket=self._bucket_name,
            Key=self.key,
            UploadId=self.upload_id,
            MultipartUpload={"Parts": self.parts},
        )
        logger.info(
            f"s3 multipart upload complete. Audio successfully written to '{self._bucket_name}/{self.key}'"
        )
        self._s3_client.close()

    def abort_upload(self, passedin_upload_id: Optional[int] = None):
        """Cancel the multipart upload"""
        upload_id = passedin_upload_id or self.upload_id
        if upload_id:
            self._s3_client.abort_multipart_upload(
                Bucket=self._bucket_name, Key=self.key, UploadId=upload_id
            )
            self.upload_id = None
            self.parts = []
            self._upload_in_progress = False
