#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Gemini + Twilio Example: Cascaded models.

A Pipecat bot that uses Google STT, Google TTS, and Gemini LLM in cascade.
You can connect to this bot using either SmallWebRTC or Twilio.

Required AI services:
- Google STT (Speech-to-Text)
- Google Gemini (LLM)
- Google TTS (Text-to-Speech)
- Twilio (Voice)

Run the bot locally using SmallWebRTC::

    uv run bot-cascade.py
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import EndTaskFrame, LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    UserTurnStoppedMessage,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.google.stt import GoogleSTTService
from pipecat.services.google.tts import GoogleTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from game_content import GameContent

load_dotenv(override=True)

NUM_ROUNDS = 4


# Define the end_game function handler (needs access to task)
async def end_game_handler(params: FunctionCallParams):
    """Handle end_game function call by pushing EndTaskFrame to end the conversation."""
    logger.info("Game ended - pushing EndTaskFrame")
    await params.result_callback({"status": "game_ended"})
    await params.llm.push_frame(
        TTSSpeakFrame("And that's all the time we have for today. Thanks for playing!")
    )
    # Push EndTaskFrame to gracefully end the task
    await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    stt = GoogleSTTService(
        params=GoogleSTTService.InputParams(languages=Language.EN_US),
        credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH"),
    )

    tts = GoogleTTSService(
        voice_id="en-US-Chirp3-HD-Charon",
        params=GoogleTTSService.InputParams(language=Language.EN_US),
        credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH"),
    )

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

    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        model="gemini-2.5-flash",
        # Turn on thinking if you want it
        # params=GoogleLLMService.InputParams(extra={"thinking_config": {"thinking_budget": 4096}}),)
    )

    # Register the function with the LLM
    llm.register_function("end_game", end_game_handler)

    messages = [
        {
            "role": "system",
            "content": f"""You are an enthusiastic game show host playing "Two Truths and a Lie."

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
After round {NUM_ROUNDS}, call the end_game function.

EXAMPLE FLOW:
"Let's play Two Truths and a Lie! Ready? Here's round 1:
[Read the three statements from ROUND 1]
Which one's the lie?"

[After their guess]
"That's right! Number 2 was the lie. You're 1 for 1!"

Remember: Present the pre-written statements exactly as shown, keep your commentary brief, and call end_game after round {NUM_ROUNDS}!""",
        },
        {
            "role": "user",
            "content": "Introduce the game in one sentence, then say 'Ready? Here's the first one:' then present the first three statements.",
        },
    ]

    context = LLMContext(messages, tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]
            ),
        ),
    )

    # Add RTVI to the pipeline to receive events for the SmallWebRTC Prebuilt UI
    # Only needed for client/server messaging and events
    # You can remove RTVI processors and observers for Twilio/phone use cases
    rtvi = RTVIProcessor()

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            rtvi,
            stt,  # STT
            user_aggregator,  # User respones
            llm,  # LLM
            tts,  # TTS
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
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_in_filter=krisp_filter,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
