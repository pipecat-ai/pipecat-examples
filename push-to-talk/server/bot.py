#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    LLMRunFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIClientMessageFrame
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.turns.types import ProcessFrameResult
from pipecat.turns.user_start.base_user_turn_start_strategy import BaseUserTurnStartStrategy
from pipecat.turns.user_stop.external_user_turn_stop_strategy import ExternalUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

# We store functions so transport params don't get instantiated until the
# desired transport is selected. The function will be called when the desired
# transport gets selected.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


class PushToTalkUserTurnStartStrategy(BaseUserTurnStartStrategy):
    """Start a user turn when the client presses the push-to-talk button.

    Reacts directly to the `push_to_talk` RTVI client message (state == "start").
    Interruptions are enabled, so pressing the button while the bot is talking
    barges in and stops its speech.
    """

    def __init__(self, **kwargs):
        super().__init__(enable_interruptions=True, enable_user_speaking_frames=False, **kwargs)

    async def process_frame(self, frame: Frame) -> ProcessFrameResult:
        await super().process_frame(frame)

        if (
            isinstance(frame, RTVIClientMessageFrame)
            and frame.type == "push_to_talk"
            and (frame.data or {}).get("state") == "start"
        ):
            logger.info("User turn started")
            # STT runs continuously, so transcripts can accumulate in the
            # aggregator while the button is up. Discard them on press so only
            # speech captured after the press is aggregated into the user message.
            await self.trigger_reset_aggregation()
            await self.trigger_user_turn_started()
            return ProcessFrameResult.STOP

        return ProcessFrameResult.CONTINUE


class PushToTalkUserTurnStopStrategy(ExternalUserTurnStopStrategy):
    """Stop a user turn when the client releases the push-to-talk button.

    Reacts directly to the `push_to_talk` RTVI client message and drives the
    parent `ExternalUserTurnStopStrategy`'s transcript-aware finalization:
    "start" primes the turn and "stop" ends it (after the trailing transcript
    arrives). All other frames (e.g. transcriptions) are delegated to the parent.
    """

    async def process_frame(self, frame: Frame) -> ProcessFrameResult:
        if isinstance(frame, RTVIClientMessageFrame) and frame.type == "push_to_talk":
            state = (frame.data or {}).get("state")
            if state == "start":
                await self._handle_user_started_speaking(UserStartedSpeakingFrame())
            elif state == "stop":
                logger.info("User turn stopped")
                await self._handle_user_stopped_speaking(UserStoppedSpeakingFrame())
            return ProcessFrameResult.CONTINUE

        return await super().process_frame(frame)


class PushToTalkUserTurnStrategies(UserTurnStrategies):
    """User turn strategies driven entirely by the push-to-talk button."""

    def __init__(self):
        self.start = [PushToTalkUserTurnStartStrategy()]
        self.stop = [PushToTalkUserTurnStopStrategy()]


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            system_instruction="You are a helpful assistant. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a creative and helpful way.",
        ),
    )

    context = LLMContext()
    # The push-to-talk button is the sole authority over user turns. The custom
    # strategies react to the client's `push_to_talk` message: the aggregator
    # only collects transcription between a button press and release, then pushes
    # the aggregation to the LLM (waiting briefly for the trailing transcript).
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=PushToTalkUserTurnStrategies(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            user_aggregator,  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            assistant_aggregator,  # Assistant spoken responses
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info("Client ready event received")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # Kick off the conversation.
        context.add_message({"role": "user", "content": "Please introduce yourself to the user."})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
