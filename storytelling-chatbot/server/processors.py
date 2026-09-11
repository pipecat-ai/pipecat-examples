#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Frame processors that turn the LLM's story text into pages and pictures."""

import asyncio
import re

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    OutputImageRawFrame,
    TextFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.services.image_service import ImageGenService
from pipecat.services.llm_service import LLMService

from prompts import (
    CUE_ASSISTANT_TURN,
    CUE_USER_TURN,
    FIRST_IMAGE_PROMPT,
    IMAGE_GEN_PROMPT,
    IMAGE_PROMPT_INSTRUCTIONS,
    NEXT_IMAGE_PROMPT,
)
from utils.helpers import load_sounds

sounds = load_sounds(["talking.wav", "listening.wav", "ding.wav"])

# How long to wait for an illustration before narrating the page without one.
IMAGE_GEN_TIMEOUT_SECS = 15

# -------------- Frame Types ------------- #


class StoryPageFrame(TextFrame):
    """A sentence of the story, delimited by [break] in the LLM output."""

    pass


class StoryImageFrame(TextFrame):
    """An inline <image prompt> found in the LLM output."""

    pass


class StoryPromptFrame(TextFrame):
    """The question the LLM asks the user at the end of each response."""

    pass


# ------------ Frame Processors ----------- #


class StoryImageProcessor(FrameProcessor):
    """Illustrates each story page before it is narrated.

    For every `StoryPageFrame` the processor asks the LLM (out of band, via
    `run_inference`) for a short image prompt that keeps characters consistent
    with earlier pages, generates a picture from it, pushes the image frame to
    the transport's video output and then passes the page on to TTS.
    """

    def __init__(self, llm: LLMService, image_gen: ImageGenService):
        super().__init__()
        self._llm = llm
        self._image_gen = image_gen
        self._pages: list[str] = []
        self._image_descriptions: list[str] = []

    def can_generate_metrics(self) -> bool:
        return True

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StoryPageFrame):
            await self._illustrate(frame.text)

        await self.push_frame(frame, direction)

    async def _illustrate(self, page: str):
        if not self._pages:
            prompt = FIRST_IMAGE_PROMPT % page
        else:
            prompt = NEXT_IMAGE_PROMPT % (
                " ".join(self._pages),
                "; ".join(self._image_descriptions),
                page,
            )

        await self.start_ttfb_metrics()
        try:
            description = await self._llm.run_inference(
                LLMContext(messages=[{"role": "user", "content": prompt}]),
                system_instruction=IMAGE_PROMPT_INSTRUCTIONS,
            )
            if not description:
                logger.warning("No image description generated, skipping illustration")
                return

            self._pages.append(page)
            self._image_descriptions.append(description)

            async with asyncio.timeout(IMAGE_GEN_TIMEOUT_SECS):
                async for image in self._image_gen.run_image_gen(IMAGE_GEN_PROMPT % description):
                    if isinstance(image, OutputImageRawFrame):
                        await self.push_frame(image)
                    else:
                        logger.warning(f"Image generation returned {image}")
        except TimeoutError:
            logger.debug("Image generation timed out, narrating without an illustration")
        finally:
            await self.stop_ttfb_metrics()


class StoryProcessor(FrameProcessor):
    """Splits the streamed LLM output into story pages and image prompts.

    The prompt asks the LLM to end every story sentence with `[break]` and to
    wrap image prompts in `<...>`. This processor buffers the text frames,
    emits a `StoryPageFrame` per sentence (so TTS speaks one page at a time)
    and a `StoryImageFrame` per inline image prompt, and tells the client whose
    turn it is via RTVI server messages. See prompts.py for the format.
    """

    def __init__(self):
        super().__init__()
        self._text = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStoppedSpeakingFrame):
            # Let the UI know the bot is about to respond
            await self.push_frame(RTVIServerMessageFrame(data=CUE_ASSISTANT_TURN))
            await self.push_frame(sounds["talking"])
            await self.push_frame(frame, direction)

        elif isinstance(frame, TextFrame):
            # Add new text to the buffer
            # (character replace hack to fix TTS sequencing)
            self._text += frame.text.replace(";", "—")
            # Process any complete patterns in the order they appear
            await self.process_text_content()

        # End of a full LLM response
        # Driven by the prompt, the LLM should have asked the user for input
        elif isinstance(frame, LLMFullResponseEndFrame):
            # We use a different frame type, as to avoid image generation ingest
            await self.push_frame(StoryPromptFrame(self._text))
            self._text = ""
            await self.push_frame(frame, direction)
            # Hand the turn back to the user
            await self.push_frame(RTVIServerMessageFrame(data=CUE_USER_TURN))
            await self.push_frame(sounds["listening"])

        # Anything that is not a TextFrame passes through
        else:
            await self.push_frame(frame, direction)

    async def process_text_content(self):
        """Process text content in order of appearance, handling both image prompts and story breaks."""
        while True:
            # Find the first occurrence of each pattern
            image_match = re.search(r"<(.*?)>", self._text)
            break_match = re.search(r"\[[bB]reak\]", self._text)

            # If neither pattern is found, we're done processing
            if not image_match and not break_match:
                break

            # Find which pattern comes first in the text
            image_pos = image_match.start() if image_match else float("inf")
            break_pos = break_match.start() if break_match else float("inf")

            if image_match and image_pos < break_pos:
                # Process image prompt first
                image_prompt = image_match.group(1)
                # Remove the image prompt from the text
                self._text = self._text[: image_match.start()] + self._text[image_match.end() :]
                await self.push_frame(StoryImageFrame(image_prompt))
            else:
                # Process story break first
                parts = re.split(r"\[[bB]reak\]", self._text, flags=re.IGNORECASE, maxsplit=1)
                before_break = parts[0].replace("\n", " ").strip()

                if len(before_break) > 2:
                    await self.push_frame(StoryPageFrame(before_break))
                    await self.push_frame(RTVIServerMessageFrame(data=CUE_ASSISTANT_TURN))

                # Keep the remainder (if any) in the buffer
                self._text = parts[1].strip() if len(parts) > 1 else ""
