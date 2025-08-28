#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
import sys
from typing import List

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesUpdateFrame,
    LLMTextFrame,
    TranscriptionMessage,
    TranscriptionUpdateFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import (
    OpenAILLMContext,
    OpenAILLMContextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from runner import configure

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class LLMTextLogger(FrameProcessor):
    """A processor that logs LLMTextFrame content."""

    def __init__(self):
        """Initialize the LLMTextLogger."""
        super().__init__()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process a frame and log LLMTextFrame content.

        Args:
            frame (Frame): The frame to process.
            direction (FrameDirection): The direction of the frame.
        """
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMTextFrame):
            logger.info(f"LLMTextFrame: {frame.text}")
        elif isinstance(frame, LLMFullResponseStartFrame):
            logger.info("LLMFullResponseStartFrame: LLM response started")
        elif isinstance(frame, LLMFullResponseEndFrame):
            logger.info("LLMFullResponseEndFrame: LLM response ended")

        await self.push_frame(frame)


class SummaryProcessor(FrameProcessor):
    """A processor that logs OpenAILLMContextFrame content."""

    def __init__(self):
        """Initialize the SummaryProcessor."""
        super().__init__()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process a frame and log OpenAILLMContextFrame content.

        Args:
            frame (Frame): The frame to process.
            direction (FrameDirection): The direction of the frame.
        """
        await super().process_frame(frame, direction)

        if isinstance(frame, OpenAILLMContextFrame):
            logger.info(f"OpenAILLMContextFrame: {frame.context}")

        await self.push_frame(frame)


class TranscriptHandler:
    """Handler to capture conversation transcript and log summaries.

    Maintains a list of conversation messages and logs them with timestamps.
    Tracks participant information to include names in transcriptions.
    """

    def __init__(self, transport: DailyTransport):
        """Initialize the TranscriptHandler with an empty list of messages.

        Args:
            transport: DailyTransport instance to get participant information
        """
        self.messages: List[TranscriptionMessage] = []
        self.transport = transport
        self.participants = {}  # user_id -> participant info

    def update_participant(self, participant_id: str, participant_info: dict):
        """Update participant information.

        Args:
            participant_id: The participant's user ID
            participant_info: Dictionary containing participant details
        """
        self.participants[participant_id] = participant_info
        logger.info(f"Updated participant info: {participant_id} -> {participant_info}")

    def get_participant_name(self, user_id: str | None) -> str:
        """Get participant name from user ID.

        Args:
            user_id: The user ID to look up (can be None)

        Returns:
            Participant name or fallback identifier
        """
        if not user_id:
            return "Unknown-User"

        if user_id in self.participants:
            participant = self.participants[user_id]
            # Try different name fields that might be available
            name = (
                participant.get("info", {}).get("userName")
                or participant.get("info", {}).get("user_name")
                or participant.get("userName")
                or participant.get("user_name")
                or f"Participant-{user_id[:8]}"
            )
            return name
        return f"Unknown-{user_id[:8]}"

    async def on_transcript_update(
        self, processor: TranscriptProcessor, frame: TranscriptionUpdateFrame
    ):
        """Handle new transcript messages.

        Args:
            processor: The TranscriptProcessor that emitted the update
            frame: TranscriptionUpdateFrame containing new messages
        """
        self.messages.extend(frame.messages)

        # Log the new messages with participant names
        logger.info("New transcript messages:")
        for msg in frame.messages:
            timestamp = f"[{msg.timestamp}] " if msg.timestamp else ""

            if msg.role == "user":
                # Get participant name for user messages
                participant_name = self.get_participant_name(msg.user_id)
                role_display = f"{participant_name}"
            else:
                role_display = "Summary"

            logger.info(f"{timestamp}{role_display}: {msg.content}")


async def main():
    """Main function to set up and run the summary bot pipeline."""
    async with aiohttp.ClientSession() as session:
        (room_url, token) = await configure(session)

        transport = DailyTransport(
            room_url,
            token,
            "Summary Bot",
            DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=False,  # Silent bot - no audio output
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )

        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY", ""))

        llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY", ""))
        context = OpenAILLMContext()
        context_aggregator = llm.create_context_aggregator(context)

        transcript = TranscriptProcessor()
        transcript_handler = TranscriptHandler(transport)
        llm_text_logger = LLMTextLogger()
        summary_processor = SummaryProcessor()

        # Register event handler for transcript updates
        @transcript.event_handler("on_transcript_update")
        async def on_transcript_update(processor, frame):
            await transcript_handler.on_transcript_update(processor, frame)

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                transcript.user(),  # User transcripts
                context_aggregator.user(),  # Process user context for LLM
                summary_processor,  # Log OpenAILLMContextFrame objects
                llm,
                # No TTS or audio output - silent bot
                # transcript.assistant(),  # Summary transcripts
                transcript.assistant(),  # Full transcript including summaries
                context_aggregator.assistant(),
                # llm_text_logger,
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            logger.info("First participant joined - starting summary generation")
            transcript_handler.update_participant(participant["id"], participant)

        @transport.event_handler("on_participant_joined")
        async def on_participant_joined(transport, participant):
            logger.info(f"Participant joined: {participant}")
            transcript_handler.update_participant(participant["id"], participant)

        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            logger.info(f"Participant left: {participant}")

            logger.debug(f"Generating summary")

            # Convert messages list to a formatted string
            conversation_text = ""
            for msg in transcript_handler.messages:
                participant_name = transcript_handler.get_participant_name(msg.user_id)
                conversation_text += f"{participant_name}: {msg.content}\n"

            logger.debug(f"""conversation_text: 
            {conversation_text}
            """)

            # Set the context with our messages first
            from typing import cast

            from openai.types.chat import ChatCompletionMessageParam

            messages_for_context: list[ChatCompletionMessageParam] = [
                {
                    "role": "system",
                    "content": "You will be provided with a conversation. Provide a summary.",
                },
                {"role": "user", "content": conversation_text},
            ]

            messages_for_frame = [
                {
                    "role": "system",
                    "content": "You will be provided with a conversation. Provide a summary.",
                },
                {"role": "user", "content": conversation_text},
            ]

            logger.debug(f"Generated messages for LLM: {messages_for_frame}")

            # Set the context messages and then trigger LLM
            context.set_messages(messages_for_context)
            await task.queue_frame(LLMMessagesUpdateFrame(messages_for_frame, run_llm=True))
            await task.queue_frame(EndFrame())

        runner = PipelineRunner()

        await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
