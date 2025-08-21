#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
import sys
from pathlib import Path
import aiohttp
from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.gemini_multimodal_live.gemini import GeminiMultimodalLiveLLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.frames.frames import (
    EndFrame
)
from pipecat.processors.frameworks.rtvi import (
    RTVIBotTranscriptionProcessor,
    RTVIConfig,
    RTVIBotLLMProcessor,
    RTVIProcessor,
    RTVISpeakingProcessor,
    RTVIUserTranscriptionProcessor,
)

sys.path.append(str(Path(__file__).parent.parent))
from runner import configure

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

# Search tool can only be used together with other tools when using the Multimodal Live API
# Otherwise it should be used alone.
# We are registering the tools here, but who are handling them is the RTVI client
search_tool = {'google_search': {}}
tools = [
    {
        "function_declarations": [
            {
                "name": "get_my_current_location",
                "description": "Retrieves the user current location",
                "parameters": None,  # Specify None for no parameters
            },
            {
                "name": "set_restaurant_location",
                "description": "Sets the location of the chosen restaurant",
                "parameters": {
                    "type": "object",
                    "properties": {
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
                        }
                    },
                    "required": ["restaurant", "lat", "lon", "address"],
                },
            },
        ]
    },
    search_tool
]

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


async def main():
    async with aiohttp.ClientSession() as session:
        (room_url, token) = await configure(session)

        transport = DailyTransport(
            room_url,
            token,
            "Latest news!",
            DailyParams(
                audio_out_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                vad_audio_passthrough=True,
            ),
        )

        # Initialize the Gemini Multimodal Live model
        llm = GeminiMultimodalLiveLLMService(
            api_key=os.getenv("GOOGLE_API_KEY"),
            voice_id="Puck",  # Aoede, Charon, Fenrir, Kore, Puck
            transcribe_user_audio=True,
            transcribe_model_audio=True,
            system_instruction=system_instruction,
            tools=tools,
        )

        context = OpenAILLMContext(
            [{"role": "user", "content": """
            Start by briefly introduction yourself and tell me what you can do.
            """}],
        )
        context_aggregator = llm.create_context_aggregator(context)

        #
        # RTVI events for Pipecat client UI
        #

        # This will send `user-*-speaking` and `bot-*-speaking` messages.
        rtvi_speaking = RTVISpeakingProcessor()

        # This will emit UserTranscript events.
        rtvi_user_transcription = RTVIUserTranscriptionProcessor()

        # This will emit BotTranscript events.
        rtvi_bot_transcription = RTVIBotTranscriptionProcessor()

        # This will send `bot-llm-*` messages.
        rtvi_bot_llm = RTVIBotLLMProcessor()

        # Handles RTVI messages from the client
        rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

        # Registering the functions to be invoked by RTVI
        llm.register_function(
            None, rtvi.handle_function_call, start_callback=rtvi.handle_function_call_start
        )

        pipeline = Pipeline(
            [
                transport.input(),
                rtvi,
                context_aggregator.user(),
                llm,
                rtvi_bot_llm,
                rtvi_speaking,
                rtvi_user_transcription,
                rtvi_bot_transcription,
                transport.output(),
                context_aggregator.assistant(),
            ]
        )

        task = PipelineTask(pipeline, PipelineParams(allow_interruptions=True))

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            await transport.capture_participant_transcription(participant["id"])
            await task.queue_frames([context_aggregator.user().get_context_frame()])

        @rtvi.event_handler("on_client_ready")
        async def on_client_ready(rtvi):
            await rtvi.set_bot_ready()

        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            print(f"Participant left: {participant}")
            await task.queue_frame(EndFrame())

        runner = PipelineRunner()
        await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
