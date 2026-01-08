#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""
Pipecat Local Setup Example
===========================

This example runs a simple **voice AI bot** that you can connect to
via your browser and speak with in real-time.

Supported Local AI Services:
----------------------------
✅ Whisper (Speech-to-Text)
✅ Ollama (Local LLM)
✅ Piper (Text-to-Speech)

Usage:
------
Run the bot locally with:

    uv run botLocal.py
"""

import os
import aiohttp
from dotenv import load_dotenv
from loguru import logger

# ==============================================================
# 🔹 Initial Setup
# ==============================================================
print("🚀 Starting Pipecat bot...")
print("⏳ Loading models and imports (first run may take ~20s)\n")

# ==============================================================
# 🔹 Import Local Models and Core Components
# ==============================================================
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams

# Local services
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.piper.tts import PiperTTSService
from pipecat.services.whisper.stt import WhisperSTTService, Model

logger.info("✅ All components loaded successfully!")

# Load environment variables
load_dotenv(override=True)


# ==============================================================
# 🔹 Bot Core Logic
# ==============================================================
async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Main function to initialize and run the Pipecat bot."""

    logger.info("Starting local AI pipeline...")

    # --- Speech-to-Text (Whisper Local) ---
    stt = WhisperSTTService(
        model=Model.TINY,  # Options: tiny, base, small, medium, large
        device="auto",     # Uses GPU if available, else CPU
    )

    # --- Text-to-Speech (Piper Local) ---
    tts = PiperTTSService(
        base_url=os.getenv("PIPER_BASE_URL", "http://127.0.0.1:5002/api/tts"),
        aiohttp_session=aiohttp.ClientSession(),
    )

    # --- Local LLM (Ollama) ---
    llm = OLLamaLLMService(
        model="llama3.2:1b",  # Change model name as needed
        base_url="http://localhost:11434/v1",
    )

    # --- Conversation Context ---
    messages = [
        {
            "role": "system",
            "content": (
                "You are a friendly and helpful AI assistant. "
                "Respond naturally and conversationally."
            ),
        },
    ]
    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(context)

    # --- Real-Time Voice Interface ---
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    # ==============================================================
    # 🔹 Define Pipeline Flow
    # ==============================================================
    pipeline = Pipeline(
        [
            transport.input(),             # Incoming audio
            rtvi,                           # Real-time processing
            stt,                            # Speech-to-Text
            context_aggregator.user(),      # User input aggregation
            llm,                            # Local LLM
            tts,                            # Text-to-Speech
            transport.output(),             # Output back to user
            context_aggregator.assistant(), # Store AI responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[RTVIObserver(rtvi)],
    )

    # ==============================================================
    # 🔹 Transport Events
    # ==============================================================
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected ✅")
        messages.append(
            {"role": "system", "content": "Say hello and introduce yourself briefly."}
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected ❌")
        await task.cancel()

    # ==============================================================
    # 🔹 Run the Pipeline
    # ==============================================================
    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


# ==============================================================
# 🔹 Bot Entry Point
# ==============================================================
async def bot(runner_args: RunnerArguments):
    """Main entry point for local bot execution."""

    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            turn_analyzer=LocalSmartTurnAnalyzerV3(),
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            turn_analyzer=LocalSmartTurnAnalyzerV3(),
        ),
    }

    # Create and start transport (WebRTC / Daily)
    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


# ==============================================================
# 🔹 Script Entry
# ==============================================================
if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
