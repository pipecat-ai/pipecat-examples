#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    LLMRunFrame,
    LLMSetToolsFrame,
    LLMUpdateSettingsFrame,
    TranscriptionMessage,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.services.openai_realtime import (
    InputAudioNoiseReduction,
    InputAudioTranscription,
    OpenAIRealtimeLLMService,
    SemanticTurnDetection,
    SessionProperties,
)
from pipecat.services.openai_realtime.events import AudioConfiguration, AudioInput
from pipecat.transports.daily.transport import DailyParams, DailyTransport

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

SYSTEM_INSTRUCTION = """
"You are a Chatbot, a friendly, helpful robot.
Your goal is to demonstrate your capabilities in a succinct way.
Your output will be converted to audio so don't include special characters in your answers.
Respond to what the user said in a creative and helpful way. Keep your responses brief. One or two sentences at most.
"""


def extract_arguments():
    parser = argparse.ArgumentParser(description="Instant Voice Example")
    parser.add_argument(
        "-u", "--url", type=str, required=True, help="URL of the Daily room to join"
    )
    parser.add_argument(
        "-t",
        "--token",
        type=str,
        required=False,
        help="Token of the Daily room to join",
    )
    args, unknown = parser.parse_known_args()
    url = args.url or os.getenv("DAILY_SAMPLE_ROOM_URL")
    token = args.token
    return url, token


async def main():
    room_url, token = extract_arguments()
    print(f"room_url: {room_url}")

    daily_transport = DailyTransport(
        room_url,
        token,
        "Instant voice Chatbot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    llm = OpenAIRealtimeLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        send_transcription_frames=True,
        start_audio_paused=False,
        session_properties=SessionProperties(
            audio=AudioConfiguration(
                input=AudioInput(
                    transcription=InputAudioTranscription(
                        model="gpt-4o-transcribe",
                        language="en",
                    ),
                    turn_detection=SemanticTurnDetection(),
                    noise_reduction=InputAudioNoiseReduction(type="near_field"),
                )
            ),
            instructions=SYSTEM_INSTRUCTION,
        ),
    )

    context = LLMContext([{"role": "user", "content": "You are a helpful assistant."}])
    context_aggregator = LLMContextAggregatorPair(context)

    # RTVI events for Pipecat client UI
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]), transport=daily_transport)

    pipeline = Pipeline(
        [
            daily_transport.input(),
            context_aggregator.user(),
            rtvi,
            llm,  # LLM
            daily_transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        await rtvi.set_bot_ready()
        # Kick off the conversation
        # UNCOMMENT THIS TO MAKE IT WORK
        # await task.queue_frames([LLMRunFrame()])

    @daily_transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.debug("First participant joined: {}", participant["id"])

    @daily_transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.debug(f"Participant left: {participant}")
        from pprint import pprint

        print("context:")
        pprint(context.get_messages())
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
