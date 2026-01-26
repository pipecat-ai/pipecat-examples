#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Gemini Live + Twilio Example.

A Pipecat bot that uses Google Gemini Live and Twilio.
You can connect to this bot using either SmallWebRTC or Twilio.

Required AI services:
- Google Gemini Live (LLM)
- Twilio (Voice)

Run the bot locally using SmallWebRTC::

    uv run bot.py
"""

import asyncio
import os

from dotenv import load_dotenv
from google.genai.types import ThinkingConfig
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import EndTaskFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    UserTurnStoppedMessage,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, InputParams
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams

from game_content import GameContent

load_dotenv(override=True)

NUM_ROUNDS = 4


# Define the end_game function handler (needs access to task)
async def end_game_handler(params: FunctionCallParams):
    """Handle end_game function call by pushing EndTaskFrame to end the conversation."""
    logger.info("Game ended - pushing EndTaskFrame")
    await params.result_callback({"status": "game_ended"})
    # TODO: Remove this once we handle frame queueing more gracefully
    await asyncio.sleep(3)
    # Push EndTaskFrame to gracefully end the task
    await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    # Generate game rounds (2 truths + 1 lie each)
    game = GameContent(num_rounds=NUM_ROUNDS)
    all_rounds = game.get_formatted_rounds()

    # Define end_game function for graceful disconnect
    end_game_function = FunctionSchema(
        name="end_game",
        description=f"Call this function after completing all {NUM_ROUNDS} rounds to end the game and say goodbye to the player",
        properties={},
        required=[],
    )

    tools = ToolsSchema(standard_tools=[end_game_function])

    instructions = f"""You are an enthusiastic game show host playing "Two Truths and a Lie."

GAME RULES:
1. Present three numbered statements - two TRUE, one LIE
2. Player guesses which is the lie (by number or description)
3. Reveal answer briefly, then immediately start next round (unless all rounds are complete)
4. Keep running score
5. After completing all {NUM_ROUNDS} rounds, call the end_game function to end the game

YOUR STATEMENTS ARE PRE-WRITTEN:
You must present the statements EXACTLY as written below, in order. Do not make up your own statements.
Each round shows which statement is the lie.

{all_rounds}

PRESENTATION STYLE:
- Read each statement naturally and enthusiastically
- Present all three statements before asking for their guess
- After each guess, briefly reveal the answer and move to the next round (unless all rounds are complete)
- Keep your commentary concise - the statements themselves are already detailed

BE CONCISE FOR:
- Your intro (1-2 sentences): "Let's play Two Truths and a Lie! I'll give you three facts, you pick the fake. Ready?"
- Your response to their guess (1-2 sentences): "Correct! Number 2 was the lie. That's 2 points!"

PERSONALITY:
- Energetic and fun
- Quick reactions after their guess: "Yes!", "Ooh, so close!", "Nice!"
- Keep the game moving fast
- The facts are already rich and interesting, so just present them enthusiastically

ENDING THE GAME:
After round {NUM_ROUNDS}, give a brief final score and say goodbye in 1-2 sentences, then call the end_game function.
Example: "...and we're all out of time. You got {NUM_ROUNDS - 1} out of {NUM_ROUNDS}. Nice job. Thanks for playing!"

EXAMPLE FLOW:
"Let's play Two Truths and a Lie! Ready? Here's round 1:
[Read the three statements from ROUND 1]
Which one's the lie?"

[After their guess]
"That's right! Number 2 was the lie. You're 1 for 1!"

Remember: Present the pre-written statements exactly as shown, keep your commentary brief, and call end_game after round {NUM_ROUNDS}!"""

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model="gemini-2.5-flash-native-audio-preview-09-2025",
        voice_id="Charon",  # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
        system_instruction=instructions,
        tools=tools,
        params=InputParams(thinking=ThinkingConfig(thinking_budget=0)),
    )

    # Register the function with the LLM
    llm.register_function("end_game", end_game_handler)

    messages = [
        {
            "role": "user",
            "content": "Introduce the game in one sentence, then say 'Ready? Here's round 1:' and present the first three statements from ROUND 1.",
        },
    ]

    context = LLMContext(messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    # Add RTVI to the pipeline to receive events for the SmallWebRTC Prebuilt UI
    # Only needed for client/server messaging and events
    # You can remove RTVI processors and observers for Twilio/phone use cases
    rtvi = RTVIProcessor()

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            rtvi,
            user_aggregator,  # User respones
            llm,  # LLM
            transport.output(),  # Transport bot output
            assistant_aggregator,  # Assistant spoken responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        observers=[RTVIObserver(rtvi)],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # Kick off the conversation.
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    @user_aggregator.event_handler("on_user_turn_stopped")
    async def on_user_turn_stopped(aggregator, strategy, message: UserTurnStoppedMessage):
        timestamp = f"[{message.timestamp}] " if message.timestamp else ""
        line = f"{timestamp}user: {message.content}"
        logger.info(f"Transcript: {line}")

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
        timestamp = f"[{message.timestamp}] " if message.timestamp else ""
        line = f"{timestamp}assistant: {message.content}"
        logger.info(f"Transcript: {line}")

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    # Krisp is available when deployed to Pipecat Cloud
    if os.environ.get("ENV") != "local":
        from pipecat.audio.filters.krisp_filter import KrispFilter

        krisp_filter = KrispFilter()
    else:
        krisp_filter = None

    # We store functions so objects (e.g. SileroVADAnalyzer) don't get
    # instantiated. The function will be called when the desired transport gets
    # selected.
    transport_params = {
        "twilio": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_in_filter=krisp_filter,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_in_filter=krisp_filter,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
        ),
    }

    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
