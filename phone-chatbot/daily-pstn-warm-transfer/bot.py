#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Daily PSTN Warm Transfer Bot.

This bot handles customer calls and performs warm transfers:
1. Talks with customer to understand their needs
2. Decides which specialist team to connect them with
3. Places customer on hold with music
4. Dials out to specialist and briefs them
5. Connects customer with specialist
6. Falls back to customer if transfer fails
"""

import os
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.mixers.soundfile_mixer import SoundfileMixer
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    ControlFrame,
    EndFrame,
    EndTaskFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    LLMMessagesAppendFrame,
    LLMRunFrame,
    MixerEnableFrame,
    OutputAudioRawFrame,
    STTMuteFrame,
    TTSAudioRawFrame,
    UserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyDialinSettings, DailyParams, DailyTransport
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from models import AgentRequest, TransferTarget, WarmTransferConfig

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


# ------------ TRANSFER STATE ------------


class TransferState(Enum):
    """States in the warm transfer flow."""

    TALKING_TO_CUSTOMER = "talking_to_customer"
    HOLDING_CUSTOMER = "holding_customer"
    TALKING_TO_AGENT = "talking_to_agent"
    CONNECTED = "connected"
    TRANSFER_FAILED = "transfer_failed"


# ------------ CUSTOM CONTROL FRAMES ------------


@dataclass
class CustomerHoldFrame(ControlFrame):
    """Control frame to toggle customer hold state."""

    on_hold: bool


@dataclass
class StartTransferFrame(ControlFrame):
    """Control frame to initiate a warm transfer."""

    target: TransferTarget
    summary: str


# ------------ FRAME PROCESSORS ------------


class CustomerHoldGate(FrameProcessor):
    """Gates customer audio input when on hold.

    Listens for CustomerHoldFrame to toggle hold state.
    When on hold, suppresses customer audio input and mutes STT.
    """

    def __init__(self):
        super().__init__()
        self._on_hold = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Listen for hold control frame
        if isinstance(frame, CustomerHoldFrame):
            self._on_hold = frame.on_hold
            logger.info(f"Customer hold state: {'ON HOLD' if frame.on_hold else 'ACTIVE'}")
            # Mute STT when on hold
            await self.push_frame(STTMuteFrame(mute=frame.on_hold))
            await self.push_frame(frame, direction)
            return

        # When on hold, suppress customer audio input frames
        if self._on_hold and isinstance(
            frame,
            (
                InputAudioRawFrame,
                UserStartedSpeakingFrame,
                InterruptionFrame,
            ),
        ):
            logger.trace(f"{frame.__class__.__name__} suppressed - Customer on hold")
            return  # Suppress customer input

        await self.push_frame(frame, direction)


class BotAudioGate(FrameProcessor):
    """Routes bot audio output when on hold.

    Listens for CustomerHoldFrame to toggle hold state.
    When on hold, routes bot audio to agent track only and enables hold music.
    """

    def __init__(self):
        super().__init__()
        self._on_hold = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Listen for hold control frame
        if isinstance(frame, CustomerHoldFrame):
            self._on_hold = frame.on_hold
            # Control hold music mixer
            await self.push_frame(MixerEnableFrame(frame.on_hold))
            await self.push_frame(frame, direction)
            return

        # When on hold, route bot audio to agent track only
        if self._on_hold and isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)):
            frame.transport_destination = "agent"

        await self.push_frame(frame, direction)


class TransferCoordinator(FrameProcessor):
    """Coordinates the warm transfer flow using frame-based control.

    Listens for StartTransferFrame to begin transfer, waits for
    BotStoppedSpeakingFrame to know when hold message is complete,
    then activates hold and dials the agent.
    """

    def __init__(self, transport: BaseTransport, config: WarmTransferConfig):
        super().__init__()
        self._transport = transport
        self._config = config
        self._state = TransferState.TALKING_TO_CUSTOMER
        self._awaiting_hold_message_completion = False
        self._awaiting_briefing_completion = False
        self._transfer_target: TransferTarget | None = None
        self._transfer_summary: str | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Listen for transfer initiation
        if isinstance(frame, StartTransferFrame):
            self._transfer_target = frame.target
            self._transfer_summary = frame.summary
            self._awaiting_hold_message_completion = True
            self._state = TransferState.HOLDING_CUSTOMER
            logger.info(f"Transfer initiated to {frame.target.name}, waiting for hold message")
            await self.push_frame(frame, direction)
            return

        # Detect when hold message finishes speaking
        if (
            self._awaiting_hold_message_completion
            and isinstance(frame, BotStoppedSpeakingFrame)
            and self._state == TransferState.HOLDING_CUSTOMER
        ):
            self._awaiting_hold_message_completion = False
            logger.info("Hold message complete, activating hold and dialing agent")

            # Push CustomerHoldFrame to activate hold (processed by other gates)
            await self.push_frame(CustomerHoldFrame(on_hold=True))

            # Dial the agent
            if self._transfer_target:
                dialout_params = {"phoneNumber": self._transfer_target.phone_number}
                logger.info(f"Dialing agent: {self._transfer_target.phone_number}")
                await self._transport.start_dialout(dialout_params)

        # Detect when agent briefing finishes speaking
        if (
            self._awaiting_briefing_completion
            and isinstance(frame, BotStoppedSpeakingFrame)
            and self._state == TransferState.TALKING_TO_AGENT
        ):
            self._awaiting_briefing_completion = False
            logger.info("Agent briefing complete, connecting customer")

            # Take customer off hold
            await self.push_frame(CustomerHoldFrame(on_hold=False))
            self._state = TransferState.CONNECTED

        await self.push_frame(frame, direction)

    async def handle_dialout_answered(self, task: PipelineTask):
        """Called when agent answers the call."""
        logger.info("Agent answered, briefing them on customer issue")
        self._state = TransferState.TALKING_TO_AGENT
        self._awaiting_briefing_completion = True

        # Brief the agent
        briefing = f"""A customer is on hold waiting to speak with you. Here's what they need help with:

{self._transfer_summary}

{self._config.transfer_messages.connecting_message}"""

        message = {"role": "system", "content": briefing}
        await task.queue_frames([LLMMessagesAppendFrame([message], run_llm=True)])

    async def handle_dialout_error(self, task: PipelineTask):
        """Called when dialout fails."""
        logger.error("Dialout failed, returning to customer")
        self._state = TransferState.TRANSFER_FAILED

        # Take customer off hold
        await self.push_frame(CustomerHoldFrame(on_hold=False))

        # Notify customer
        message = {"role": "system", "content": self._config.transfer_messages.transfer_failed_message}
        await task.queue_frames([LLMMessagesAppendFrame([message], run_llm=True)])

        # Reset for potential retry
        self._state = TransferState.TALKING_TO_CUSTOMER
        self._transfer_target = None
        self._transfer_summary = None


# ------------ SYSTEM PROMPT BUILDER ------------


def build_system_prompt(config: WarmTransferConfig) -> str:
    """Build system prompt with transfer targets."""
    targets_description = "\n".join(
        [f"   - **{t.name}**: {t.description}" for t in config.transfer_targets]
    )

    return f"""You are Hailey, a friendly customer support representative. Your responses will be converted to speech, so use natural, conversational language without special characters or formatting.

## Guidelines

1. Start by greeting callers: "Hello, this is Hailey from customer support. How can I help you today?"

2. Listen to the customer's needs and try to help them directly when possible.

3. When the customer needs to speak with a specialist or you cannot fully resolve their issue:
   - Determine which team would best help based on their need
   - Use the `initiate_warm_transfer` function with the appropriate target name
   - Provide a brief summary of the customer's issue for the specialist

4. When a caller wants to end the conversation or says goodbye, use the `terminate_call` function.

## Available Transfer Targets

{targets_description}

## How Warm Transfer Works

When you call `initiate_warm_transfer`:
1. You will tell the customer you're connecting them with a specialist
2. The customer will hear hold music while you brief the specialist
3. Once you've briefed the specialist, the customer will be connected
4. If the specialist doesn't answer, you'll be reconnected with the customer

## Important Notes

- Never mention technical details like "muting" or "transferring" - use natural language like "connecting you" or "putting you through"
- If a transfer fails, apologize and offer to try again or help in another way
- Be warm and professional throughout the interaction
"""


# ------------ FUNCTION HANDLERS ------------


async def terminate_call(params: FunctionCallParams):
    """Function the bot can call to terminate the call."""
    await params.llm.queue_frame(EndTaskFrame(), FrameDirection.UPSTREAM)


async def initiate_warm_transfer(
    transport: BaseTransport,
    task: PipelineTask,
    config: WarmTransferConfig,
    transfer_coordinator: TransferCoordinator,
    params: FunctionCallParams,
):
    """Function the bot can call to initiate a warm transfer."""
    target_name = params.arguments.get("target_name", "")
    summary = params.arguments.get("summary", "")

    # Find the target
    target = next(
        (t for t in config.transfer_targets if t.name.lower() == target_name.lower()),
        None,
    )

    if not target:
        # Target not found - inform bot
        available = ", ".join(t.name for t in config.transfer_targets)
        message = {
            "role": "system",
            "content": f"Transfer target '{target_name}' not found. Available targets are: {available}. Please try again with a valid target name.",
        }
        await params.llm.push_frame(LLMMessagesAppendFrame([message], run_llm=True))
        return

    logger.info(f"Initiating warm transfer to {target.name}")

    # Speak hold message to customer
    hold_message = {"role": "system", "content": config.transfer_messages.hold_message}
    await params.llm.push_frame(LLMMessagesAppendFrame([hold_message], run_llm=True))

    # Push StartTransferFrame to begin the transfer flow
    # TransferCoordinator will handle the rest after BotStoppedSpeakingFrame
    await task.queue_frames([StartTransferFrame(target=target, summary=summary)])


# ------------ MAIN BOT LOGIC ------------


async def run_bot(transport: BaseTransport, config: WarmTransferConfig, handle_sigint: bool) -> None:
    """Run the warm transfer voice bot."""

    # ------------ SERVICES ------------

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id="b7d50908-b17c-442d-ad8d-810c63997ed9",  # Helpful Woman voice
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    # ------------ LLM AND CONTEXT SETUP ------------

    system_instruction = build_system_prompt(config)

    messages = [{"role": "system", "content": system_instruction}]

    # ------------ FUNCTION DEFINITIONS ------------

    terminate_call_function = FunctionSchema(
        name="terminate_call",
        description="Call this function to terminate the call when the customer is done.",
        properties={},
        required=[],
    )

    initiate_warm_transfer_function = FunctionSchema(
        name="initiate_warm_transfer",
        description="Call this function to initiate a warm transfer to connect the customer with a specialist.",
        properties={
            "target_name": {
                "type": "string",
                "description": "The name of the team to transfer to (e.g., 'Sales Team', 'Support Team')",
            },
            "summary": {
                "type": "string",
                "description": "A brief 2-3 sentence summary of what the customer needs help with",
            },
        },
        required=["target_name", "summary"],
    )

    tools = ToolsSchema(standard_tools=[terminate_call_function, initiate_warm_transfer_function])

    # Initialize LLM context and aggregator
    context = LLMContext(messages, tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]
            ),
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    )

    # ------------ PROCESSORS ------------

    customer_hold_gate = CustomerHoldGate()
    bot_audio_gate = BotAudioGate()
    transfer_coordinator = TransferCoordinator(transport, config)

    # ------------ PIPELINE SETUP ------------

    pipeline = Pipeline(
        [
            transport.input(),
            customer_hold_gate,
            stt,
            user_aggregator,
            llm,
            tts,
            bot_audio_gate,
            transfer_coordinator,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
        ),
    )

    # ------------ REGISTER FUNCTIONS ------------

    llm.register_function("terminate_call", terminate_call)
    llm.register_function(
        "initiate_warm_transfer",
        lambda params: initiate_warm_transfer(transport, task, config, transfer_coordinator, params),
    )

    # ------------ EVENT HANDLERS ------------

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.info(f"Customer joined: {participant.get('id')}")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_dialout_answered")
    async def on_dialout_answered(transport, data):
        logger.info(f"Dialout answered: {data}")
        await transfer_coordinator.handle_dialout_answered(task)

    @transport.event_handler("on_dialout_error")
    async def on_dialout_error(transport, data):
        logger.error(f"Dialout error: {data}")
        await transfer_coordinator.handle_dialout_error(task)

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info(f"Participant left: {participant}, reason: {reason}")
        # If customer leaves, end the call
        await task.cancel()

    # ------------ RUN PIPELINE ------------

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    try:
        request = AgentRequest.model_validate(runner_args.body)

        # Get hold music file path
        hold_music_path = Path(__file__).parent / "hold_music.wav"

        # Initialize hold music mixer
        hold_music_mixer = SoundfileMixer(
            sound_files={"hold": str(hold_music_path)},
            default_sound="hold",
            volume=0.5,
            loop=True,
        )

        daily_dialin_settings = DailyDialinSettings(
            call_id=request.callId, call_domain=request.callDomain
        )

        transport = DailyTransport(
            request.room_url,
            request.token,
            "Warm Transfer Bot",
            params=DailyParams(
                dialin_settings=daily_dialin_settings,
                api_key=os.getenv("DAILY_API_KEY"),
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_out_mixer=hold_music_mixer,
                audio_out_destinations=["agent"],
            ),
        )

        await run_bot(transport, request.warm_transfer_config, runner_args.handle_sigint)

    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise e


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
