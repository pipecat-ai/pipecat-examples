#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat Multi-LLM Fallback Example with Runtime Error Recovery.

How it Works:
-------------
This example demonstrates a multi-LLM fallback mechanism with runtime recovery:

1️⃣ Tries Ollama local model
2️⃣ If fails or unavailable → tries Google Gemini via API key
3️⃣ If fails → falls back to OpenAI via API key
4️⃣ If all fail → exits with an error message

This bot listens to voice input and responds naturally using local or cloud LLMs.

Required AI services:
---------------------
- Deepgram (Speech-to-Text)
- Ollama local LLM (recommended)
- Google Gemini or OpenAI API keys (optional)
- Cartesia (Text-to-Speech)

Run:
    uv run botLLMFB.py
"""

import os
from dotenv import load_dotenv
from loguru import logger
import httpx

print("🚀 Starting Pipecat bot...")
print("⏳ Loading models and imports (first run may take ~20s)")

# ---------------- Environment Setup ----------------
load_dotenv(override=True)

print("\n📋 Environment Check:")
print(f"   OLLAMA_URL: {os.getenv('OLLAMA_URL', 'http://localhost:11434')}")
print(f"   OLLAMA_MODEL: {os.getenv('OLLAMA_MODEL', 'qwen2.5:latest')}")
print(f"   GEMINI_API_KEY: {'✓ Set' if os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY') else '✗ Not set'}")
print(f"   OPENAI_API_KEY: {'✓ Set' if os.getenv('OPENAI_API_KEY') else '✗ Not set'}")
print()

# ---------------- Core Pipecat Imports ----------------
logger.info("Loading core Pipecat modules...")
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
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams

logger.info("✅ All Pipecat components loaded successfully!")

# ---------------- Constants ----------------
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_URL_V1 = os.getenv("OLLAMA_URL_V1", "http://localhost:11434/v1")  # v1 endpoint
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


# ---------------- Helper Functions ----------------
async def check_ollama_available(base_url: str = OLLAMA_URL) -> bool:
    """Check if Ollama service is running."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            if response.status_code == 200:
                logger.debug("Ollama is running and reachable.")
                return True
            logger.warning(f"Ollama responded with {response.status_code}")
            return False
    except Exception as e:
        logger.debug(f"Ollama not accessible: {str(e)[:100]}")
        return False


# ---------------- LLM Fallback Chain ----------------
async def get_llm_service():
    """Try Ollama → Gemini → OpenAI in order, with runtime fallback."""

    # 1️⃣ Try local Ollama
    try:
        logger.info("🔹 Trying Ollama local model...")
        base_url = OLLAMA_URL
        base_url_v1 = OLLAMA_URL_V1  # Use v1 endpoint if specified
        model = OLLAMA_MODEL

        if not await check_ollama_available(base_url):
            raise ValueError("Ollama service not running")

        #llm = OLLamaLLMService(model=model, base_url=base_url)
        llm= OLLamaLLMService(
            model=model,
            base_url=base_url_v1  # Default Ollama API endpoint
        )
        logger.success(f"✅ Using local Ollama model ({model}) — runtime errors will fallback automatically")
        return llm, "ollama"

    except Exception as e:
        logger.warning(f"⚠️ Ollama unavailable: {str(e)[:150]}")

    # 2️⃣ Try Google Gemini
    try:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY not found")

        logger.info("🔹 Trying Google Gemini...")
        llm = GoogleLLMService(model=GEMINI_MODEL, api_key=api_key)
        logger.success(f"✅ Using Google Gemini LLM ({GEMINI_MODEL})")
        return llm, "gemini"

    except Exception as e:
        logger.warning(f"⚠️ Google Gemini unavailable: {str(e)[:150]}")

    # 3️⃣ Try OpenAI
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")

        logger.info("🔹 Trying OpenAI GPT...")
        llm = OpenAILLMService(model=OPENAI_MODEL, api_key=api_key)
        logger.success(f"✅ Using OpenAI fallback ({OPENAI_MODEL})")
        return llm, "openai"

    except Exception as e:
        logger.error(f"⚠️ OpenAI unavailable: {str(e)[:150]}")

    # ❌ If all fail
    logger.critical("❌ No available LLM service found. Exiting.")
    logger.info("\n💡 Quick fix:")
    logger.info(f"   For Ollama: Run 'ollama pull {OLLAMA_MODEL}'")
    logger.info("   For Gemini: Set GEMINI_API_KEY in .env")
    logger.info("   For OpenAI: Set OPENAI_API_KEY in .env\n")
    raise SystemExit("No working LLM service found!")


# ---------------- BOT LOGIC ----------------
async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("🎧 Starting bot pipeline...")

    # Speech-to-Text
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    # Text-to-Speech
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    # LLM Fallback
    llm, llm_type = await get_llm_service()
    logger.info(f"🤖 Selected LLM: {llm_type}")

    # Initial prompt
    messages = [{"role": "system", "content": "You are a friendly AI assistant. Respond naturally and conversationally."}]
    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(context)
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    # Build pipeline
    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[RTVIObserver(rtvi)],
    )

    # Client connect/disconnect handlers
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("👋 Client connected")
        messages.append({"role": "system", "content": "Say hello and introduce yourself briefly."})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("❎ Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point."""
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

    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
