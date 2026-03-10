#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os

import boto3
from bedrock_agentcore import BedrockAgentCoreApp
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
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

AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
KVS_CHANNEL_NAME = os.getenv("KVS_CHANNEL_NAME", "voice-agent-turn")


def get_kvs_ice_servers():
    """Get temporary TURN credentials from Amazon Kinesis Video Streams.

    Uses a KVS signaling channel for managed TURN credential provisioning.
    The channel is used only for TURN credentials — Pipecat's WebRTC transport
    handles all signaling and media.
    """
    kvs = boto3.client("kinesisvideo", region_name=AWS_REGION)

    # Get or create signaling channel
    try:
        resp = kvs.describe_signaling_channel(ChannelName=KVS_CHANNEL_NAME)
        channel_arn = resp["ChannelInfo"]["ChannelARN"]
    except kvs.exceptions.ResourceNotFoundException:
        logger.info(f"Creating KVS signaling channel: {KVS_CHANNEL_NAME}")
        resp = kvs.create_signaling_channel(
            ChannelName=KVS_CHANNEL_NAME, ChannelType="SINGLE_MASTER"
        )
        channel_arn = resp["ChannelARN"]

    # Get HTTPS endpoint for the signaling channel
    resp = kvs.get_signaling_channel_endpoint(
        ChannelARN=channel_arn,
        SingleMasterChannelEndpointConfiguration={
            "Protocols": ["HTTPS"],
            "Role": "MASTER",
        },
    )
    endpoint = resp["ResourceEndpointList"][0]["ResourceEndpoint"]

    # Get temporary TURN credentials
    signaling = boto3.client(
        "kinesis-video-signaling",
        region_name=AWS_REGION,
        endpoint_url=endpoint,
    )
    resp = signaling.get_ice_server_config(ChannelARN=channel_arn, Service="TURN")

    # Convert to Pipecat IceServer format
    ice_servers = []
    for server in resp["IceServerList"]:
        turn_urls = [u for u in server["Uris"] if u.startswith("turn:")]
        if turn_urls:
            ice_servers.append(
                IceServer(
                    urls=turn_urls,
                    username=server.get("Username"),
                    credential=server.get("Password"),
                )
            )

    logger.info(f"Retrieved {len(ice_servers)} TURN server(s) from KVS")
    return ice_servers


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
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @task.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info(f"Client ready")
        # Kick off the conversation.
        context.add_message(
            {"role": "user", "content": "Say hello and briefly introduce yourself."}
        )
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

    ice_servers = get_kvs_ice_servers()

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
    """Bot entry point for running locally."""
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
