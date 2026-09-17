#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""file-upload with client uploads stored in Amazon S3.

The same bot as ``bot.py``, but the runner's ``POST /files`` upload endpoint
is backed by an S3 bucket instead of the local uploads folder: an upload is
written to the bucket and the endpoint returns an ``s3://`` URL, which the
client passes back in its ``send-file`` message.

At completion time the URL is resolved per provider: AWS Bedrock can read
``s3://`` URLs itself through its own IAM (the bucket must be readable by the
account making the Bedrock call), so they pass straight through; every other
provider has the ``FileResolver`` download the file from the bucket with this
process's AWS credentials and inline the bytes.

Requires:

- AWS credentials with read/write access to the bucket (the standard
  ``AWS_ACCESS_KEY_ID``/``AWS_SECRET_ACCESS_KEY``/``AWS_REGION`` env vars or
  any other botocore credential source)
- ``S3_UPLOADS_BUCKET`` set to the bucket name

Run the bot using::

    uv run bot_s3.py
    uv run bot_s3.py -llm bedrock
"""

import argparse
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any

import aiobotocore.session
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# The pipeline is identical to bot.py's; only the storage backend differs.
from bot import bot  # noqa: F401  (re-exported for the runner to discover)
from pipecat.runner.run import set_runner_file_storage
from pipecat.utils.file_storage import FileStorage

load_dotenv(override=True)


class S3FileStorage(FileStorage):
    """Client uploads in an S3 bucket, addressed as ``s3://`` URLs."""

    def __init__(self, bucket: str, region: str | None = None, prefix: str = "uploads/"):
        """Initialize S3-backed upload storage.

        Args:
            bucket: Name of the bucket to store uploads in.
            region: AWS region of the bucket; defaults to the credential
                chain's region.
            prefix: Key prefix for uploads within the bucket.
        """
        self._session = aiobotocore.session.get_session()
        self._bucket = bucket
        self._region = region
        self._prefix = prefix

    def _client(self) -> Any:
        return self._session.create_client("s3", region_name=self._region)

    async def save(self, filename: str, contents: bytes) -> str:
        """Upload `contents` to a new randomly-named key and return its ``s3://`` URL."""
        key = f"{self._prefix}{uuid.uuid4().hex}{Path(filename).suffix}"
        content_type, _ = mimetypes.guess_type(filename, strict=False)
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=contents,
                ContentType=content_type or "application/octet-stream",
            )
        return f"s3://{self._bucket}/{key}"

    async def load(self, file_url: str) -> bytes:
        """Download and return the object stored under `file_url`."""
        key = self._key_for(file_url)
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                async with response["Body"] as stream:
                    return await stream.read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise FileNotFoundError(file_url) from e
            raise

    async def delete(self, file_url: str) -> None:
        """Delete the object stored under `file_url`, if it exists."""
        try:
            key = self._key_for(file_url)
        except FileNotFoundError:
            return
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    def _key_for(self, file_url: str) -> str:
        """Validate `file_url` and return the object key it maps to."""
        prefix = f"s3://{self._bucket}/"
        if not file_url.startswith(prefix):
            raise FileNotFoundError(file_url)
        return file_url.removeprefix(prefix)


if __name__ == "__main__":
    from pipecat.runner.run import main

    set_runner_file_storage(
        S3FileStorage(bucket=os.environ["S3_UPLOADS_BUCKET"], region=os.getenv("AWS_REGION"))
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-llm",
        "--llm",
        choices=["anthropic", "openai", "bedrock", "gemini", "vertex"],
        default="anthropic",
        help="LLM provider to use (default: anthropic)",
    )
    main(parser)
