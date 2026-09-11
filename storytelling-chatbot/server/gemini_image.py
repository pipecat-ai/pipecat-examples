#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Image generation with a Gemini image model.

Pipecat's ``GoogleImageGenService`` drives Imagen, which the google-genai SDK
only serves through Vertex AI. This service uses a Gemini image model through
the Gemini Developer API instead, so a plain ``GOOGLE_API_KEY`` is enough.
"""

import io
from collections.abc import AsyncGenerator

from google import genai
from google.genai import types
from loguru import logger
from PIL import Image
from pipecat.frames.frames import ErrorFrame, Frame, OutputImageRawFrame
from pipecat.services.image_service import ImageGenService
from pipecat.services.settings import ImageGenSettings
from pipecat.utils.types import assert_given


class GeminiImageGenService(ImageGenService):
    """Generates one image per prompt with a Gemini image model."""

    def __init__(self, *, api_key: str, model: str = "gemini-2.5-flash-image", **kwargs):
        super().__init__(settings=ImageGenSettings(model=model), **kwargs)
        self._client = genai.Client(api_key=api_key)

    async def run_image_gen(self, prompt: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"Generating image from prompt: {prompt}")

        model = assert_given(self._settings.model)
        response = await self._client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )

        parts = response.candidates[0].content.parts if response.candidates else None
        for part in parts or []:
            if part.inline_data and part.inline_data.data:
                image = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                yield OutputImageRawFrame(image=image.tobytes(), size=image.size, format=image.mode)
                return

        yield ErrorFrame("Image generation returned no image")
