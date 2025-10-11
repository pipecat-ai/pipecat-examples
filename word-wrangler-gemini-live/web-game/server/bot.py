#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#


import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.filters.stt_mute_filter import STTMuteConfig, STTMuteFilter, STTMuteStrategy
from pipecat.processors.frameworks.rtvi import (
    RTVIConfig,
    RTVIObserver,
    RTVIProcessor,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

load_dotenv(override=True)


# Define conversation modes with their respective prompt templates
game_prompt = """You are the AI host and player for a game of Word Wrangler.

GAME RULES:
1. The user will be given a word or phrase that they must describe to you
2. The user CANNOT say any part of the word/phrase directly
3. You must try to guess the word/phrase based on the user's description
4. Once you guess correctly, the user will move on to their next word
5. The user is trying to get through as many words as possible in 60 seconds
6. The external application will handle timing and keeping score

YOUR ROLE:
1. Start with this exact brief introduction: "Welcome to Word Wrangler! I'll try to guess the words you describe. Remember, don't say any part of the word itself. Ready? Let's go!"
2. Listen carefully to the user's descriptions
3. Make intelligent guesses based on what they say
4. When you think you know the answer, state it clearly: "Is it [your guess]?"
5. If you're struggling, ask for more specific clues
6. Keep the game moving quickly - make guesses promptly
7. Be enthusiastic and encouraging

IMPORTANT:
- Keep all responses brief - the game is timed!
- Make multiple guesses if needed
- Use your common knowledge to make educated guesses
- If the user indicates you got it right, just say "Got it!" and prepare for the next word
- If you've made several wrong guesses, simply ask for "Another clue please?"

Start with the exact introduction specified above, then wait for the user to begin describing their first word."""

# Define personality presets
PERSONALITY_PRESETS = {
    "friendly": "You have a warm, approachable personality. You use conversational language, occasional humor, and express enthusiasm for the topic. Make the user feel comfortable and engaged.",
    "professional": "You have a formal, precise personality. You communicate clearly and directly with a focus on accuracy and relevance. Your tone is respectful and business-like.",
    "enthusiastic": "You have an energetic, passionate personality. You express excitement about the topic and use dynamic language. You're encouraging and positive throughout the conversation.",
    "thoughtful": "You have a reflective, philosophical personality. You speak carefully, considering multiple angles of each point. You ask thought-provoking questions and acknowledge nuance.",
    "witty": "You have a clever, humorous personality. While remaining informative, you inject appropriate wit and playful language. Your goal is to be engaging and entertaining while still being helpful.",
}


async def run_bot(transport: DailyTransport, runner_args: RunnerArguments):
    # Use the provided session logger if available, otherwise use the default logger
    config = runner_args.body
    logger.debug("Configuration: {}", config)

    # Extract configuration parameters with defaults
    personality = config.get("personality", "witty")

    personality_prompt = PERSONALITY_PRESETS.get(personality, PERSONALITY_PRESETS["friendly"])

    system_instruction = f"""{game_prompt}

{personality_prompt}

Important guidelines:
1. Your responses will be converted to speech, so keep them concise and conversational.
2. Don't use special characters or formatting that wouldn't be natural in speech.
3. Encourage the user to elaborate when appropriate."""

    intro_message = """Start with this exact brief introduction: "Welcome to Word Wrangler! I'll try to guess the words you describe. Remember, don't say any part of the word itself. Ready? Let's go!"""

    # Create the STT mute filter if we have strategies to apply
    stt_mute_filter = STTMuteFilter(
        config=STTMuteConfig(strategies={STTMuteStrategy.MUTE_UNTIL_FIRST_BOT_COMPLETE})
    )

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        system_instruction=system_instruction,
    )

    # Set up the initial context for the conversation
    messages = [
        {
            "role": "user",
            "content": intro_message,
        },
    ]

    # This sets up the LLM context by providing messages and tools
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # RTVI events for Pipecat client UI
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,
            stt_mute_filter,
            context_aggregator.user(),
            llm,
            transport.output(),
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
        logger.debug("Client ready event received")
        await rtvi.set_bot_ready()
        # Kick off the conversation
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with the FastAPI route handler."""
    if os.environ.get("ENV") != "local":
        from pipecat.audio.filters.krisp_filter import KrispFilter

        krisp_filter = KrispFilter()
    else:
        krisp_filter = None

    # We store functions so objects (e.g. SileroVADAnalyzer) don't get
    # instantiated. The function will be called when the desired transport gets
    # selected.
    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_in_filter=krisp_filter,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams()),
        )
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
