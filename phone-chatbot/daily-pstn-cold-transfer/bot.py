#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    EndFrame,
    EndTaskFrame,
    LLMMessagesAppendFrame,
    LLMRunFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.runner.types import RunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyDialinSettings, DailyParams, DailyTransport
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def terminate_call(params: FunctionCallParams):
    """Function the bot can call to terminate the call."""
    await params.llm.queue_frame(EndTaskFrame(), FrameDirection.UPSTREAM)


async def dial_operator(transport: BaseTransport, params: FunctionCallParams):
    """Function the bot can call to dial an operator and transfer the call."""
    operator_number = os.getenv("OPERATOR_NUMBER", None)

    if operator_number:
        logger.info(f"Transferring call to operator: {operator_number}")

        # Inform the user about the transfer
        content = "I'm transferring you to a supervisor now. Please hold while I connect you."
        message = {
            "role": "system",
            "content": content,
        }

        # Queue the message to the context and let it speak
        await params.llm.push_frame(LLMMessagesAppendFrame([message], run_llm=True))

        # Start the dialout to transfer the call
        transfer_params = {"toEndPoint": operator_number}
        logger.debug(f"SIP call transfer parameters: {transfer_params}")
        await transport.sip_call_transfer(transfer_params)

    else:
        # No operator number configured
        content = "I'm sorry, but supervisor transfer is not available at this time. Is there anything else I can help you with?"
        message = {
            "role": "system",
            "content": content,
        }

        # Queue the message to the context
        await params.llm.push_frame(LLMMessagesAppendFrame([message], run_llm=True))
        logger.warning("No operator dialout settings available")


async def run_bot(transport: BaseTransport, handle_sigint: bool) -> None:
    """Run the voice bot with the given parameters."""
    # Operator dialout number

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id="b7d50908-b17c-442d-ad8d-810c63997ed9",  # Use Helpful Woman voice by default
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    # ------------ LLM AND CONTEXT SETUP ------------

    system_instruction = """You are Hailey, a friendly customer support representative. Your responses will be converted to speech, so use natural, conversational language without special characters or formatting.

Guidelines:
1. Start by greeting callers: "Hello, this is Hailey from customer support. What can I help you with today?"

2. When handling requests:
   - If a caller asks to speak with a supervisor, manager, or human agent, use the `dial_operator` function to transfer them
   - If a caller wants to end the conversation or says goodbye, use the `terminate_call` function

3. Be helpful and professional while assisting with their questions or concerns.

Note: When you transfer a call to a supervisor, you will leave the call and the customer will speak directly with the supervisor.

Available functions:
- `dial_operator`: Call this when the user requests to speak with a supervisor or manager (this will transfer the call)
- `terminate_call`: Call this when the user wants to end the conversation"""

    messages = [
        {
            "role": "system",
            "content": system_instruction,
        }
    ]

    # ------------ FUNCTION DEFINITIONS ------------

    # Define function schemas for tools
    terminate_call_function = FunctionSchema(
        name="terminate_call",
        description="Call this function to terminate the call.",
        properties={},
        required=[],
    )

    dial_operator_function = FunctionSchema(
        name="dial_operator",
        description="Call this function when the user asks to speak with a human",
        properties={},
        required=[],
    )

    # Create tools schema
    tools = ToolsSchema(standard_tools=[terminate_call_function, dial_operator_function])

    # Register functions with the LLM
    llm.register_function("terminate_call", terminate_call)
    llm.register_function("dial_operator", lambda params: dial_operator(transport, params))

    # Initialize LLM context and aggregator
    context = LLMContext(messages, tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]
            ),
        ),
    )

    # ------------ PIPELINE SETUP ------------

    # Build simple pipeline for cold transfer
    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            user_aggregator,  # User responses
            llm,
            tts,
            transport.output(),  # Transport bot output
            assistant_aggregator,  # Assistant spoken responses
        ]
    )

    # Create pipeline task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
        ),
    )

    # ------------ EVENT HANDLERS ------------

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        # Bot answers the phone and greets the user
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_dialout_answered")
    async def on_dialout_answered(transport, data):
        logger.info(f"Operator answered, transferring call: {data}")
        # Cold transfer: bot leaves the call, customer and operator continue
        # await task.cancel()
        await task.queue_frames([EndFrame()])

    @transport.event_handler("on_dialout_error")
    async def on_dialout_error(transport, data):
        logger.error(f"Operator dialout error: {data}")
        # Inform the customer that transfer failed
        content = "I'm sorry, but I'm unable to connect you with a supervisor at this time. Is there anything else I can help you with?"
        message = {"role": "system", "content": content}
        await task.queue_frames([LLMMessagesAppendFrame([message], run_llm=True)])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.debug(f"Participant left: {participant}, reason: {reason}")
        # If customer leaves, end the call
        await task.cancel()

    # ------------ RUN PIPELINE ------------

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    # Body is always a dict (compatible with both local and Pipecat Cloud)
    body_data = runner_args.body
    room_url = body_data.get("room_url")
    token = body_data.get("token")
    call_id = body_data.get("callId")
    call_domain = body_data.get("callDomain")

    if not all([call_id, call_domain]):
        logger.error("Call ID and Call Domain are required in the body.")
        return None

    daily_dialin_settings = DailyDialinSettings(call_id=call_id, call_domain=call_domain)

    transport = DailyTransport(
        room_url,
        token,
        "Call Transfer Bot",
        params=DailyParams(
            dialin_settings=daily_dialin_settings,
            api_key=os.getenv("DAILY_API_KEY"),
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    )

    await run_bot(transport, runner_args.handle_sigint)
