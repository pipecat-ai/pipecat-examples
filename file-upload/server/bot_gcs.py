#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""file-upload with client uploads stored in Google Cloud Storage.

The same bot as ``bot.py``, but the runner's ``POST /files`` upload endpoint
is backed by a GCS bucket instead of the local uploads folder: an upload is
written to the bucket and the endpoint returns a ``gs://`` URL, which the
client passes back in its ``send-file`` message.

At completion time the URL is resolved per provider: Gemini on Vertex AI can
read ``gs://`` URLs itself through its own IAM, so they pass straight through;
every other provider — including Gemini via the developer API, which can't
read ``gs://`` — has the ``FileResolver`` download the file from the bucket
with this process's Google credentials and inline the bytes.

Requires:

- ``google-cloud-storage``
- Application Default Credentials with read/write access to the bucket
  (``GOOGLE_APPLICATION_CREDENTIALS``, or ``gcloud auth application-default login``)
- ``GCS_UPLOADS_BUCKET`` set to the bucket name

Run the bot using::

    uv run bot_gcs.py
    uv run bot_gcs.py -llm vertex  # gs:// pass-through; needs GOOGLE_CLOUD_PROJECT_ID
"""

import argparse
import asyncio
import mimetypes
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google.api_core.exceptions import NotFound
from google.cloud import storage

# The pipeline is identical to bot.py's; only the storage backend differs.
from bot import bot  # noqa: F401  (re-exported for the runner to discover)
from pipecat.runner.run import set_runner_file_storage
from pipecat.utils.file_storage import FileStorage

load_dotenv(override=True)


class GCSFileStorage(FileStorage):
    """Client uploads in a Google Cloud Storage bucket, addressed as ``gs://`` URLs."""

    def __init__(self, bucket: str, prefix: str = "uploads/"):
        """Initialize GCS-backed upload storage.

        Args:
            bucket: Name of the bucket to store uploads in.
            prefix: Object-name prefix for uploads within the bucket.
        """
        self._bucket = storage.Client().bucket(bucket)
        self._prefix = prefix

    async def save(self, filename: str, contents: bytes) -> str:
        """Upload `contents` to a new randomly-named object and return its ``gs://`` URL."""
        blob_name = f"{self._prefix}{uuid.uuid4().hex}{Path(filename).suffix}"
        content_type, _ = mimetypes.guess_type(filename, strict=False)
        blob = self._bucket.blob(blob_name)
        await asyncio.to_thread(
            blob.upload_from_string,
            contents,
            content_type=content_type or "application/octet-stream",
        )
        return f"gs://{self._bucket.name}/{blob_name}"

    async def load(self, file_url: str) -> bytes:
        """Download and return the object stored under `file_url`."""
        blob = self._blob_for(file_url)
        try:
            return await asyncio.to_thread(blob.download_as_bytes)
        except NotFound as e:
            raise FileNotFoundError(file_url) from e

    async def delete(self, file_url: str) -> None:
        """Delete the object stored under `file_url`, if it exists."""
        try:
            await asyncio.to_thread(self._blob_for(file_url).delete)
        except (FileNotFoundError, NotFound):
            pass

    def _blob_for(self, file_url: str) -> storage.Blob:
        """Validate `file_url` and return the blob it maps to."""
        prefix = f"gs://{self._bucket.name}/"
        if not file_url.startswith(prefix):
            raise FileNotFoundError(file_url)
        return self._bucket.blob(file_url.removeprefix(prefix))


if __name__ == "__main__":
    from pipecat.runner.run import main

    set_runner_file_storage(GCSFileStorage(bucket=os.environ["GCS_UPLOADS_BUCKET"]))

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-llm",
        "--llm",
        choices=["anthropic", "openai", "bedrock", "gemini", "vertex"],
        default="anthropic",
        help="LLM provider to use (default: anthropic)",
    )
    main(parser)
