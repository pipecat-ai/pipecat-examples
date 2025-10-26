#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Daily + Twilio SIP dial-out voice bot implementation."""

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
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from server_utils import AgentRequest, DialoutSettings

load_dotenv(override=True)


class DialoutManager:
    """Manages dialout attempts with retry logic.

    Handles the complexity of initiating outbound calls with automatic retry
    on failure, up to a configurable maximum number of attempts.

    Args:
        transport: The Daily transport instance for making the dialout
        dialout_settings: Settings containing SIP URI
        max_retries: Maximum number of dialout attempts (default: 5)
    """

    def __init__(
        self,
        transport: DailyTransport,
        dialout_settings: DialoutSettings,
        max_retries: Optional[int] = 5,
    ):
        self._transport = transport
        self._sip_uri = dialout_settings.sip_uri
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
            f"Attempting dialout (attempt {self._attempt_count}/{self._max_retries}) to: {self._sip_uri}"
        )

        await self._transport.start_dialout({"sipUri": self._sip_uri})
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
    transport: DailyTransport, dialout_settings: DialoutSettings, handle_sigint: bool
) -> None:
    """Run the voice bot with the given parameters.

    Args:
        transport: The Daily transport instance
        dialout_settings: Settings containing SIP URI for dialout
    """
    logger.info(f"Starting dial-out bot, dialing out to: {dialout_settings.sip_uri}")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    # Create system message and initialize messages list
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

    # Build pipeline
    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            context_aggregator.assistant(),  # Assistant spoken responses
        ]
    )

    # Create pipeline task
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
    """Main bot entry point compatible with Pipecat Cloud."""
    try:
        request = AgentRequest.model_validate(runner_args.body)

        transport = DailyTransport(
            request.room_url,
            request.token,
            "SIP Dial-out Bot",
            params=DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
                turn_analyzer=LocalSmartTurnAnalyzerV3(),
            ),
        )

        await run_bot(transport, request.dialout_settings, runner_args.handle_sigint)

    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise e


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
