#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Client-side function calling - Pipecat Voice Agent.

The LLM is given tools that only the client can answer: the user's local time
and the page's background color. The bot declares the tools, and the client
runs them with ``registerFunctionCallHandler`` and sends the result back.

How a call travels:

1. The LLM calls ``get_local_time``. Its server function returns without
   calling ``result_callback``, so the call stays in progress.
2. ``RTVIObserver`` sends ``llm-function-call-in-progress`` to the client with
   the function name and arguments (allowed by ``function_call_report_level``).
3. The client runs its handler and replies with ``llm-function-call-result``.
4. ``RTVIProcessor`` turns the reply into a ``FunctionCallResultFrame``; the
   assistant aggregator adds it to the context and runs the LLM again.

Required AI services:
- Deepgram (Speech-to-Text)
- OpenAI (LLM)
- Cartesia (Text-to-Speech)

Run the bot using::

    uv run bot.py
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import (
    RTVIFunctionCallReportLevel,
    RTVIObserverParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

SYSTEM_INSTRUCTION = (
    "You are a friendly voice assistant running inside a web page. "
    "Your output is spoken aloud, so keep replies short and avoid lists, markdown and emojis. "
    "Use get_local_time whenever the user asks about the time, date or their timezone. "
    "Use set_background_color when the user asks to change the page's color; "
    "pass a CSS color such as a name or a hex value."
)

# The tools are direct functions: Pipecat builds each one's schema from its
# signature and docstring. Their bodies don't call ``params.result_callback``,
# which leaves the call open until the client's ``llm-function-call-result``
# arrives. The client's handlers are in client/javascript/src/app.js.


async def get_local_time(params: FunctionCallParams):
    """Get the current local date, time and timezone from the user's device."""
    logger.info("get_local_time: waiting for the client's result")


async def set_background_color(params: FunctionCallParams, color: str):
    """Change the background color of the web page the user is looking at.

    Args:
        color: A CSS color, such as "lightblue" or "#ffcc00".
    """
    logger.info(f"set_background_color({color!r}): waiting for the client's result")


CLIENT_TOOLS = [get_local_time, set_background_color]


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Run the voice bot for this session."""
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        ),
    )

    context = LLMContext(tools=CLIENT_TOOLS)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
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

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        # The client needs a call's name and arguments to pick and run its
        # handler; the default level ("none") reports neither.
        rtvi_observer_params=RTVIObserverParams(
            function_call_report_level={
                "*": RTVIFunctionCallReportLevel.NONE,
                **{tool.__name__: RTVIFunctionCallReportLevel.ARGUMENTS for tool in CLIENT_TOOLS},
            },
        ),
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        context.add_message(
            {
                "role": "developer",
                "content": "Greet the user briefly and say you can tell them the time "
                "or change the page's color.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport_params = {
        "daily": lambda: DailyParams(audio_in_enabled=True, audio_out_enabled=True),
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
