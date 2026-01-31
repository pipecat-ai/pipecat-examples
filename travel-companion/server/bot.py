#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Gemini Travel Companion

This module implements a chatbot using Google's Gemini Live model.
It includes:
- Real-time audio interaction through Daily
- Function calling
- Google search

The bot runs as part of a pipeline that processes audio frames and manages
the conversation flow using Gemini's streaming capabilities.
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import AdapterType, ToolsSchema
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
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyParams

load_dotenv(override=True)

# We store functions so objects (e.g. SileroVADAnalyzer) don't get
# instantiated. The function will be called when the desired transport gets
# selected.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_in_enabled=True,
    ),
}

# Search tool can only be used together with other tools when using the Gemini Live API
# Otherwise it should be used alone.
# We are registering the tools here, but who are handling them is the RTVI client
get_location_function = FunctionSchema(
    name="get_my_current_location",
    description="Retrieves the user current location",
    properties={},
    required=[],
)

set_restaurant_function = FunctionSchema(
    name="set_restaurant_location",
    description="Sets the location of the chosen restaurant",
    properties={
        "restaurant": {
            "type": "string",
            "description": "Restaurant name",
        },
        "lat": {
            "type": "string",
            "description": "Latitude of the location",
        },
        "lon": {
            "type": "string",
            "description": "Longitude of the location",
        },
        "address": {
            "type": "string",
            "description": "Complete address of the location in this format: {street, number, city}",
        },
    },
    required=["restaurant", "lat", "lon", "address"],
)

search_tool = {"google_search": {}}
tools = ToolsSchema(
    standard_tools=[get_location_function, set_restaurant_function],
    custom_tools={AdapterType.GEMINI: [search_tool]},
)


system_instruction = """
You are a travel companion, and your responses will be converted to audio, so keep them simple and avoid special characters or complex formatting.

You can:
- Use get_my_current_location to determine the user's current location. Once retrieved, inform the user of the city they are in, rather than providing coordinates.
- Use google_search to check the weather and share it with the user. Describe the temperature in Celsius and Fahrenheit.
- Use google_search to recommend restaurants that are nearby to the user's location, less than 10km. 
- Use set_restaurant_location to share the location of a selected restaurant with the user. Also check on google_search first for the precise location.
- Use google_search to provide recent and relevant news from the user's current location.

Answer any user questions with accurate, concise, and conversational responses.
"""


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Main bot execution function.

    Sets up and runs the bot pipeline including:
    - Gemini Live model integration
    - Voice activity detection
    - Animation processing
    - RTVI event handling
    """

    # Initialize the Gemini Live model
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        voice_id="Puck",  # Aoede, Charon, Fenrir, Kore, Puck
        system_instruction=system_instruction,
        tools=tools,
    )

    messages = [
        {
            "role": "user",
            "content": "Start by briefly introduction yourself and tell me what you can do.",
        },
    ]
    # Set up conversation context and management
    # The context_aggregator will automatically collect conversation context
    context = LLMContext(messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    )

    # RTVI processor for Pipecat client UI
    # Created separately so we can register function calls before task creation
    rtvi = RTVIProcessor()

    # Registering the functions to be invoked by RTVI
    llm.register_function(None, rtvi.handle_function_call)

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
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
        rtvi_processor=rtvi,
    )

    @task.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Kick off the conversation (set_bot_ready is called automatically)
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    @task.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, msg):
        print("RTVI client message:", msg.type, msg.data)
        # Sample message to show how it works
        if msg.type == "get-llm-vendor":
            await rtvi.send_server_response(msg, "Google")

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
