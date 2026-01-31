#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

from bedrock_agentcore import BedrockAgentCoreApp
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.aws import AWSBedrockLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

app = BedrockAgentCoreApp()

request_handler: SmallWebRTCRequestHandler = None

load_dotenv(override=True)


# We store functions so objects (e.g. SileroVADAnalyzer) don't get
# instantiated. The function will be called when the desired transport gets
# selected.
transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    yield {"status": "initializing bot"}

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    # Automatically uses AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION env vars.
    llm = AWSBedrockLLMService(
        model="us.amazon.nova-2-lite-v1:0",
        params=AWSBedrockLLMService.InputParams(temperature=0.8),
    )

    messages = [
        {
            "role": "system",
            "content": "You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be spoken aloud, so avoid special characters that can't easily be spoken, such as emojis or bullet points. Respond to what the user said in a creative and helpful way.",
        },
        {"role": "user", "content": "Say hello and briefly introduce yourself."},
    ]

    context = LLMContext(messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
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
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @task.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info(f"Client ready")
        # Kick off the conversation.
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    task_id = app.add_async_task("voice_agent")

    await runner.run(task)

    app.complete_async_task(task_id)

    yield {"status": "completed"}


async def initialize_connection_and_run_bot(request: SmallWebRTCRequest):
    """Handle initial WebRTC connection setup and run the bot."""

    raw_urls = os.getenv("ICE_SERVER_URLS")
    urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
    ice_servers = [
        IceServer(
            urls=urls,
            username=os.getenv("ICE_SERVER_USERNAME"),
            credential=os.getenv("ICE_SERVER_CREDENTIAL"),
        )
    ]

    transport = None
    runner_args = None

    async def webrtc_connection_callback(connection: SmallWebRTCConnection):
        nonlocal transport, runner_args
        runner_args = SmallWebRTCRunnerArguments(
            webrtc_connection=connection, body=request.request_data
        )
        transport = await create_transport(runner_args, transport_params)

    yield {"status": "initializing connection"}
    global request_handler
    request_handler = SmallWebRTCRequestHandler(ice_servers=ice_servers)
    answer = await request_handler.handle_web_request(
        request=request, webrtc_connection_callback=webrtc_connection_callback
    )
    yield {"status": "ANSWER:START"}
    yield {"answer": answer}
    yield {"status": "ANSWER:END"}

    async for result in run_bot(transport, runner_args):
        yield result


async def add_ice_candidates(patch_request: SmallWebRTCPatchRequest):
    """Handle ICE candidate additions for existing connections."""
    await request_handler.handle_patch_request(patch_request)
    yield {"status": "success"}


@app.entrypoint
async def agentcore_bot(payload, context):
    """Bot entry point for running on Amazon Bedrock AgentCore Runtime."""
    request_type = payload.get("type", "unknown")
    logger.info(f"Received request of type: {request_type}")

    data = payload.get("data")
    if not data:
        logger.error("No data found in payload")
        yield {"status": "error", "message": "No data found in payload"}
        return

    match request_type:
        case "offer":
            # Initial connection setup
            try:
                request = SmallWebRTCRequest.from_dict(data)
            except Exception as e:
                logger.error(f"Failed to deserialize SmallWebRTCRequest: {e}")
                yield {"status": "error", "message": f"Invalid request payload: {str(e)}"}
                return
            async for result in initialize_connection_and_run_bot(request):
                yield result
        case "ice-candidates":
            # ICE candidate additions
            try:
                if "candidates" in data:
                    data["candidates"] = [IceCandidate(**c) for c in data["candidates"]]
                patch_request = SmallWebRTCPatchRequest(**data)
            except Exception as e:
                logger.error(f"Failed to deserialize SmallWebRTCPatchRequest: {e}")
                yield {"status": "error", "message": f"Invalid request payload: {str(e)}"}
                return
            async for result in add_ice_candidates(patch_request):
                yield result
        case _:
            logger.error(f"Unknown request type: {request_type}")
            yield {"status": "error", "message": f"Unknown request type: {request_type}"}
            return


# Used for local development
async def bot(runner_args: RunnerArguments):
    """Bot entry point for running locally and on Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    async for result in run_bot(transport, runner_args):
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
