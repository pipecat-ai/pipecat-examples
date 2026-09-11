#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Frame processors that turn the LLM's story text into pages and pictures."""

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pipecat.frames.frames import (
    AggregatedTextFrame,
    CancelFrame,
    EndFrame,
    Frame,
    LLMFullResponseEndFrame,
    OutputImageRawFrame,
    StartFrame,
    TextFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.services.image_service import ImageGenService
from pipecat.services.llm_service import LLMService
from pipecat.utils.text.base_text_aggregator import AggregationType

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

# How long to wait for an illustration before giving up on it.
IMAGE_GEN_TIMEOUT_SECS = 20

# -------------- Frame Types ------------- #


@dataclass
class StoryPageFrame(AggregatedTextFrame):
    """A sentence of the story, delimited by [break] in the LLM output.

    It is an already-aggregated sentence so the TTS service speaks it as soon
    as it arrives instead of buffering it with the next page.
    """

    aggregated_by: AggregationType | str = AggregationType.SENTENCE


class StoryImageFrame(TextFrame):
    """An inline <image prompt> found in the LLM output."""

    pass


class StoryPromptFrame(TextFrame):
    """The question the LLM asks the user at the end of each response."""

    pass


# ------------ Frame Processors ----------- #


class StoryImageProcessor(FrameProcessor):
    """Illustrates each story page while it is being narrated.

    Pages are queued to a background task so narration is never held up by
    image generation. For each page the task asks the LLM (out of band, via
    `run_inference`) for a short image prompt that keeps characters consistent
    with earlier pages, generates a picture from it and pushes the image frame
    to the transport's video output.
    """

    def __init__(self, llm: LLMService[Any], image_gen: ImageGenService):
        super().__init__()
        self._llm = llm
        self._image_gen = image_gen
        self._pages: list[str] = []
        self._image_descriptions: list[str] = []
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._task = self.create_task(self._illustrate_pages())
        elif isinstance(frame, (EndFrame, CancelFrame)):
            await self._stop()
        elif isinstance(frame, StoryPageFrame):
            await self._queue.put(frame.text)

        await self.push_frame(frame, direction)

    async def _stop(self):
        if self._task:
            await self.cancel_task(self._task)
            self._task = None

    async def _illustrate_pages(self):
        while True:
            page = await self._queue.get()
            try:
                async with asyncio.timeout(IMAGE_GEN_TIMEOUT_SECS):
                    await self._illustrate(page)
            except TimeoutError:
                logger.debug("Image generation timed out, skipping this illustration")
            except Exception as e:
                logger.warning(f"Image generation failed: {e}")

    async def _illustrate(self, page: str):
        if not self._pages:
            prompt = FIRST_IMAGE_PROMPT % page
        else:
            prompt = NEXT_IMAGE_PROMPT % (
                " ".join(self._pages),
                "; ".join(self._image_descriptions),
                page,
            )

        description = await self._llm.run_inference(
            LLMContext(messages=[{"role": "user", "content": prompt}]),
            system_instruction=IMAGE_PROMPT_INSTRUCTIONS,
        )
        if not description:
            logger.warning("No image description generated, skipping illustration")
            return

        self._pages.append(page)
        self._image_descriptions.append(description)

        async for image in self._image_gen.run_image_gen(IMAGE_GEN_PROMPT % description):
            if isinstance(image, OutputImageRawFrame):
                await self.push_frame(image)
            else:
                logger.warning(f"Image generation returned {image}")


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
                    await self.push_frame(StoryPageFrame(text=before_break))
                    await self.push_frame(RTVIServerMessageFrame(data=CUE_ASSISTANT_TURN))

                # Keep the remainder (if any) in the buffer
                self._text = parts[1].strip() if len(parts) > 1 else ""
