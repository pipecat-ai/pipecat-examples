#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
import sys
from typing import Any, Dict, List, override

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from openai.types.chat import ChatCompletionMessageParam
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, Frame, TranscriptionMessage, TranscriptionUpdateFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import (
    OpenAILLMContext,
    OpenAILLMContextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from runner import configure

load_dotenv(override=True)

logger.remove(handler_id=0)
logger.add(sink=sys.stderr, level="DEBUG")


class SummaryProcessor(FrameProcessor):
    """A processor that logs LLMTextFrame content."""

    @override
    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process a frame and log LLMTextFrame content.

        Args:
            frame (Frame): The frame to process.
            direction (FrameDirection): The direction of the frame.
        """
        await super().process_frame(frame, direction)

        if isinstance(frame, OpenAILLMContextFrame):
            if len(frame.context.messages) > 1:
                content = frame.context.messages[-1].get("content", "No summary available")
                logger.info(f"{content}")
            else:
                logger.info("No summary available.")

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
        self.participants: Dict[str, str] = {}  # user_id -> participant info

    def update_participant(self, participant_id: str, user_name: str | None):
        """Update participant information.

        Args:
            participant_id: The participant's user ID
            user_name: The participant's user name
        """
        logger.debug(f"Updating participant {participant_id} with name {user_name}")
        self.participants[participant_id] = user_name if user_name else participant_id
        logger.info(f"Updated participant info: {participant_id} -> {user_name}")

    def get_participant_name(self, participant_id: str | None) -> str:
        """Get participant name from user ID.

        Args:
            participant_id: The participant ID to look up

        Returns:
            Participant name or fallback identifier
        """

        if participant_id is None:
            return "Unknown"

        return self.participants.get(participant_id, participant_id)

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

            participant_name = self.get_participant_name(msg.user_id)

            logger.info(f"{timestamp} {participant_name}: {msg.content}")


async def main():
    """Main function to set up and run the summary bot pipeline."""
    async with aiohttp.ClientSession() as session:
        (room_url, token) = await configure(session)

        transport = DailyTransport(
            room_url=room_url,
            token=token,  # TODO: Make this a token where presence is false
            bot_name="Summary Bot",
            params=DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=False,  # Silent bot - no audio output
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )

        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY", ""))
        llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY", ""))

        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": "You will be provided with a conversation. Provide a summary.",
            }
        ]
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)

        transcript = TranscriptProcessor()
        transcript_handler = TranscriptHandler(transport)
        summary = SummaryProcessor()

        # Register event handler for transcript updates
        @transcript.event_handler("on_transcript_update")
        async def on_transcript_update(
            processor: TranscriptProcessor, frame: TranscriptionUpdateFrame
        ) -> None:
            await transcript_handler.on_transcript_update(processor, frame)

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                transcript.user(),  # User transcripts
                llm,
                # No TTS or audio output - silent bot
                context_aggregator.assistant(),
                summary,  # Log LLM text frames
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
                allow_interruptions=True,
            ),
            idle_timeout_secs=None,  # Disable idle timeout for summary bot
        )

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(
            transport: DailyTransport, participant: Dict[str, Any]
        ):
            logger.info("First participant joined - starting summary generation")
            transcript_handler.update_participant(
                participant["id"], participant.get("info", {}).get("userName", None)
            )

        @transport.event_handler("on_participant_joined")
        async def on_participant_joined(
            transport: DailyTransport, participant: Dict[str, Any]
        ) -> None:
            logger.info(f"Participant joined: {participant}")
            transcript_handler.update_participant(
                participant["id"], participant.get("info", {}).get("userName", None)
            )

        @transport.event_handler("on_participant_left")
        async def on_participant_left(
            transport: DailyTransport, participant: Dict[str, Any], reason: str
        ) -> None:
            logger.info(f"Participant left: {participant}")

            # Convert messages list to a formatted string
            conversation_text = ""
            for msg in transcript_handler.messages:
                participant_name = transcript_handler.get_participant_name(msg.user_id)
                conversation_text += f"{msg.timestamp} {participant_name}: {msg.content}\n"

            messages.append({"role": "user", "content": conversation_text})
            await task.queue_frames(
                [
                    context_aggregator.user().get_context_frame(),  # Trigger bot response
                    EndFrame(),
                ]
            )

        runner = PipelineRunner()

        await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
