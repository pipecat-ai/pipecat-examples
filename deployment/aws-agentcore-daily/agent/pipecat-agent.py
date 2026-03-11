#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from bedrock_agentcore import BedrockAgentCoreApp
from daily import Daily
from daily_agentcore_prep import prepare_daily_transport_for_agentcore
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.services.aws.llm import AWSBedrockLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

app = BedrockAgentCoreApp()

load_dotenv(override=True)


# =============================================================================
# Bot pipeline
# =============================================================================


async def run_bot(transport: DailyTransport):
    logger.info("Starting bot")

    yield {"status": "initializing bot"}

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

    # Automatically uses credentials from assumed IAM role when running in
    # AgentCore Runtime, or from environment variables when running locally.
    llm = AWSBedrockLLMService(
        settings=AWSBedrockLLMService.Settings(
            model="us.amazon.nova-2-lite-v1:0",
            temperature=0.8,
            system_instruction="You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be spoken aloud, so avoid special characters that can't easily be spoken, such as emojis or bullet points. Respond to what the user said in a creative and helpful way.",
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # Kick off the conversation.
        context.add_message(
            {"role": "user", "content": "Say hello and briefly introduce yourself."}
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    @transport.event_handler("on_call_state_updated")
    async def on_call_state_updated(transport, state):
        logger.info(f"Call state updated: {state}")
        if state == "left":
            await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=True)

    task_id = app.add_async_task("voice_agent")

    await runner.run(task)

    app.complete_async_task(task_id)

    yield {"status": "completed"}


# =============================================================================
# Entry points
# =============================================================================


@app.entrypoint
async def agentcore_bot(payload, context):
    """Bot entry point for running on Amazon Bedrock AgentCore Runtime."""
    logger.info(f"Received trigger payload: {payload}")

    room_url = payload.get("room_url")
    if not room_url:
        logger.error("No room_url in trigger payload")
        yield {"status": "error", "message": "room_url not provided in payload"}
        return

    transport = DailyTransport(
        room_url,
        None,
        "Pipecat Bot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    prepare_daily_transport_for_agentcore(transport)

    async for result in run_bot(transport):
        yield result


# Used for local development
async def bot(runner_args: RunnerArguments):
    """Bot entry point for running locally."""
    room_url = os.getenv("DAILY_ROOM_URL")
    if not room_url:
        raise ValueError("DAILY_ROOM_URL environment variable is not set")

    transport = DailyTransport(
        room_url,
        None,
        "Pipecat Bot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    async for result in run_bot(transport):
        pass  # Consume the stream


if __name__ == "__main__":
    # NOTE: ideally we shouldn't have to branch for local dev vs AgentCore, but
    # local AgentCore container-based dev doesn't seem to be working, or at
    # least not for this project.
    if os.getenv("PIPECAT_LOCAL_DEV") == "1":
        # Running locally
        from pipecat.runner.run import main

        main()
    else:
        # Running on AgentCore Runtime
        app.run()
