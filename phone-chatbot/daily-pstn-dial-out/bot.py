#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Daily PSTN dial-out bot.

This bot demonstrates how to make outbound phone calls using Daily's PSTN capabilities.
The bot initiates a call to a specified phone number and conducts a voice conversation.
"""

import os
from typing import Any, Optional

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.runner.types import RunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from server_utils import AgentRequest, DialoutSettings

load_dotenv()


class DialoutManager:
    """Manages dialout attempts with retry logic.

    Handles the complexity of initiating outbound calls with automatic retry
    on failure, up to a configurable maximum number of attempts.

    Args:
        transport: The Daily transport instance for making the dialout
        dialout_settings: Settings containing phone number and optional caller ID
        max_retries: Maximum number of dialout attempts (default: 5)
    """

    def __init__(
        self,
        transport: BaseTransport,
        dialout_settings: DialoutSettings,
        max_retries: Optional[int] = 5,
    ):
        self._transport = transport
        self._phone_number = dialout_settings.phone_number
        self._max_retries = max_retries
        self._attempt_count = 0
        self._is_successful = False

    async def attempt_dialout(self) -> bool:
        """Attempt to start a dialout call.

        Initiates an outbound call if retry limit hasn't been reached and
        no successful connection has been made yet.

        Returns:
            True if dialout attempt was initiated, False if max retries reached
            or call already successful
        """
        if self._attempt_count >= self._max_retries:
            logger.error(
                f"Maximum retry attempts ({self._max_retries}) reached. Giving up on dialout."
            )
            return False

        if self._is_successful:
            logger.debug("Dialout already successful, skipping attempt")
            return False

        self._attempt_count += 1
        logger.info(
            f"Attempting dialout (attempt {self._attempt_count}/{self._max_retries}) to: {self._phone_number}"
        )

        await self._transport.start_dialout({"phoneNumber": self._phone_number})
        return True

    def mark_successful(self):
        """Mark the dialout as successful to prevent further retry attempts."""
        self._is_successful = True

    def should_retry(self) -> bool:
        """Check if another dialout attempt should be made.

        Returns:
            True if retry limit not reached and call not yet successful
        """
        return self._attempt_count < self._max_retries and not self._is_successful


async def run_bot(
    transport: BaseTransport, handle_sigint: bool, dialout_settings: DialoutSettings
) -> None:
    """Run the voice bot for an outbound call.

    Sets up the bot pipeline with STT, LLM, and TTS services, then initiates
    the dialout and handles the conversation with retry logic.

    Args:
        transport: Daily transport for the call
        handle_sigint: Whether to handle SIGINT signals
        dialout_settings: Phone number and optional caller ID for the outbound call
    """

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id="b7d50908-b17c-442d-ad8d-810c63997ed9",  # Use Helpful Woman voice by default
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    # Initialize LLM context with system prompt
    messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly phone assistant. Your responses will be read aloud, "
                "so keep them concise and conversational. Avoid special characters or "
                "formatting. Begin by greeting the caller and asking how you can help them today."
            ),
        },
    ]

    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Initialize dialout manager
    dialout_manager = DialoutManager(transport, dialout_settings)

    @transport.event_handler("on_joined")
    async def on_joined(transport, data):
        await dialout_manager.attempt_dialout()

    @transport.event_handler("on_dialout_answered")
    async def on_dialout_answered(transport, data):
        logger.debug(f"Dial-out answered: {data}")
        dialout_manager.mark_successful()

    @transport.event_handler("on_dialout_error")
    async def on_dialout_error(transport, data: Any):
        logger.error(f"Dial-out error, retrying: {data}")

        if dialout_manager.should_retry():
            await dialout_manager.attempt_dialout()
        else:
            logger.error(f"No more retries allowed, stopping bot.")
            await task.cancel()

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud.

    Parses the runner arguments, configures the Daily transport with dialout
    capabilities, and starts the bot.

    Args:
        runner_args: Arguments from the Pipecat runner containing room details
            and dialout settings

    Raises:
        Exception: If bot initialization or execution fails
    """
    try:
        request = AgentRequest.model_validate(runner_args.body)

        transport_params = DailyParams(
            api_key=os.getenv("DAILY_API_KEY", ""),
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_out_enabled=False,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            turn_analyzer=LocalSmartTurnAnalyzerV3(),
        )

        transport = DailyTransport(
            request.room_url,
            request.token,
            "Daily PSTN Dial-out Bot",
            transport_params,
        )

        await run_bot(transport, runner_args.handle_sigint, request.dialout_settings)

    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise e


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
