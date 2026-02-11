#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

# pyright: reportUnusedFunction=false

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
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.mixers.soundfile_mixer import SoundfileMixer
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    ControlFrame,
    EndTaskFrame,
    Frame,
    LLMMessagesAppendFrame,
    LLMRunFrame,
    MixerEnableFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext, LLMContextMessage
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
from pipecat.transports.daily.transport import DailyDialinSettings, DailyParams, DailyTransport
from pipecat.turns.user_mute.base_user_mute_strategy import BaseUserMuteStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from server_utils import AgentRequest, TransferTarget, WarmTransferConfig

load_dotenv(override=True)


class TransferState(Enum):
    """States in the warm transfer flow."""

    TALKING_TO_CUSTOMER = "talking_to_customer"
    HOLDING_CUSTOMER = "holding_customer"
    TALKING_TO_AGENT = "talking_to_agent"
    CONNECTED = "connected"
    TRANSFER_FAILED = "transfer_failed"


@dataclass
class CustomerHoldFrame(ControlFrame):
    """Control frame to toggle customer hold state."""

    on_hold: bool


@dataclass
class StartTransferFrame(ControlFrame):
    """Control frame to initiate a warm transfer."""

    target: TransferTarget
    summary: str


@dataclass
class DialoutAnsweredFrame(ControlFrame):
    """Agent answered the dialout call."""

    pass


@dataclass
class DialoutStoppedFrame(ControlFrame):
    """Dialout stopped - agent hung up or call failed."""

    pass


@dataclass
class DialoutErrorFrame(ControlFrame):
    """Dialout error occurred."""

    pass


@dataclass
class ParticipantLeftFrame(ControlFrame):
    """A participant left the call."""

    pass


# ------------ MUTE STRATEGIES ------------


class HoldMuteStrategy(BaseUserMuteStrategy):
    """Mutes user input when customer is on hold during a warm transfer.

    Listens for CustomerHoldFrame to toggle hold state. When on hold,
    the LLMUserAggregator suppresses all user input frames automatically.
    """

    def __init__(self) -> None:
        super().__init__()
        self._on_hold = False

    async def process_frame(self, frame: Frame) -> bool:
        await super().process_frame(frame)

        if isinstance(frame, CustomerHoldFrame):
            self._on_hold = frame.on_hold
            logger.info(f"Customer hold state: {'ON HOLD' if frame.on_hold else 'ACTIVE'}")

        return self._on_hold


# ------------ FRAME PROCESSORS ------------


class TransferCoordinator(FrameProcessor):
    """Coordinates the warm transfer flow using frame-based control.

    All transfer state management happens here via frames:
    - StartTransferFrame: Begin transfer, wait for hold message to finish
    - BotStoppedSpeakingFrame: Hold message done, activate hold and dial agent
    - DialoutAnsweredFrame: Agent answered, connect customer
    - DialoutStoppedFrame: Agent hung up or call failed
    - DialoutErrorFrame: Dialout error, return to customer
    - ParticipantLeftFrame: Participant left, end call if customer
    """

    def __init__(self, transport: DailyTransport, config: WarmTransferConfig) -> None:
        super().__init__()
        self._transport = transport
        self._config = config
        self._state = TransferState.TALKING_TO_CUSTOMER
        self._awaiting_hold_message_completion = False
        self._transfer_target: TransferTarget | None = None
        self._transfer_summary: str | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
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

            # Enable hold music
            await self.push_frame(MixerEnableFrame(True))

            # Push CustomerHoldFrame UPSTREAM to reach HoldMuteStrategy
            await self.push_frame(CustomerHoldFrame(on_hold=True), FrameDirection.UPSTREAM)

            # Dial the agent
            if self._transfer_target:
                dialout_params = {"phoneNumber": self._transfer_target.phone_number}
                logger.info(f"Dialing agent: {self._transfer_target.phone_number}")
                try:
                    await self._transport.start_dialout(dialout_params)
                except Exception as e:
                    logger.error(f"Failed to start dialout: {e}")
                    await self._handle_dialout_error()

        # Agent answered the dialout call
        elif isinstance(frame, DialoutAnsweredFrame):
            logger.info("Agent answered, connecting customer")
            self._state = TransferState.CONNECTED

            # Take customer off hold (hold music already stopped in on_dialout_connected)
            await self.push_frame(CustomerHoldFrame(on_hold=False), FrameDirection.UPSTREAM)

            # Brief the agent (customer will also hear this)
            briefing = (
                "A customer is on hold waiting to speak with you. "
                f"Here's what they need help with:\n\n{self._transfer_summary}\n\n"
                f"{self._config.transfer_messages.connecting_message}"
            )
            message = {"role": "system", "content": briefing}
            await self.push_frame(
                LLMMessagesAppendFrame([message], run_llm=True), FrameDirection.UPSTREAM
            )
            return

        # Dialout stopped - could be success (agent hung up) or failure
        elif isinstance(frame, DialoutStoppedFrame):
            if self._state == TransferState.CONNECTED:
                logger.info("Agent hung up after successful transfer, ending call")
                await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
            else:
                logger.info("Dialout failed before agent answered, returning to customer")
                await self._handle_dialout_error()
            return

        # Dialout error
        elif isinstance(frame, DialoutErrorFrame):
            await self._handle_dialout_error()
            return

        # Participant left
        elif isinstance(frame, ParticipantLeftFrame):
            if self._state in (TransferState.TALKING_TO_CUSTOMER, TransferState.CONNECTED):
                logger.info(f"Participant left during {self._state.value}, ending call")
                await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)
            return

        await self.push_frame(frame, direction)

    async def _handle_dialout_error(self):
        """Handle dialout failure - return to customer."""
        logger.error("Dialout failed, returning to customer")
        self._state = TransferState.TRANSFER_FAILED

        # Disable hold music
        await self.push_frame(MixerEnableFrame(False))

        # Take customer off hold
        await self.push_frame(CustomerHoldFrame(on_hold=False), FrameDirection.UPSTREAM)

        # Notify customer
        message = {
            "role": "system",
            "content": self._config.transfer_messages.transfer_failed_message,
        }
        await self.push_frame(
            LLMMessagesAppendFrame([message], run_llm=True), FrameDirection.UPSTREAM
        )

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


# ------------ MAIN BOT LOGIC ------------


async def run_bot(
    transport: DailyTransport, config: WarmTransferConfig, handle_sigint: bool
) -> None:
    """Run the warm transfer voice bot.

    Participant join order:
    1. Bot joins first
    2. Customer joins second (triggers on_first_participant_joined)
    3. Agent joins third via dialout (triggers on_participant_joined after dialout)
    """

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY", ""))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id="b7d50908-b17c-442d-ad8d-810c63997ed9",  # Helpful Woman voice
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    system_instruction = build_system_prompt(config)

    messages: list[LLMContextMessage] = [{"role": "system", "content": system_instruction}]

    # ------------ REGISTER FUNCTIONS ------------

    async def terminate_call(params: FunctionCallParams, **kwargs: Any) -> None:
        """Terminate the call when the customer is done or says goodbye."""
        await params.llm.queue_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

    async def initiate_warm_transfer(
        params: FunctionCallParams, target_name: str, summary: str, **kwargs: Any
    ) -> None:
        """Initiate a warm transfer to connect the customer with a specialist.

        Args:
            target_name (str): The name of the team to transfer to (e.g., 'Sales Team', 'Support Team').
            summary (str): A brief 2-3 sentence summary of what the customer needs help with.
        """
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
        await params.llm.push_frame(StartTransferFrame(target=target, summary=summary))

    llm.register_direct_function(terminate_call)
    llm.register_direct_function(initiate_warm_transfer)

    tools = ToolsSchema(standard_tools=[terminate_call, initiate_warm_transfer])

    # Initialize LLM context and aggregator
    hold_mute_strategy = HoldMuteStrategy()
    context = LLMContext(messages, tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())]
            ),
            user_mute_strategies=[hold_mute_strategy],
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
        ),
    )

    transfer_coordinator = TransferCoordinator(transport, config)

    # ------------ PIPELINE SETUP ------------

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
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

    # ------------ EVENT HANDLERS ------------

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant) -> None:
        # First participant after bot is always the customer
        logger.info(f"Customer joined: {participant.get('id')}")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_dialout_connected")
    async def on_dialout_connected(transport, data) -> None:
        logger.info(f"Dialout connected (ringing): {data}")
        # Stop hold music so customer hears the ringing
        await task.queue_frame(MixerEnableFrame(False))

    @transport.event_handler("on_dialout_answered")
    async def on_dialout_answered(transport, data) -> None:
        logger.info(f"Dialout answered: {data}")
        await task.queue_frame(DialoutAnsweredFrame())

    @transport.event_handler("on_dialout_stopped")
    async def on_dialout_stopped(transport, data) -> None:
        logger.info(f"Dialout stopped: {data}")
        await task.queue_frame(DialoutStoppedFrame())

    @transport.event_handler("on_dialout_error")
    async def on_dialout_error(transport, data) -> None:
        logger.error(f"Dialout error: {data}")
        await task.queue_frame(DialoutErrorFrame())

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant) -> None:
        logger.info(f"Participant joined: {participant.get('id')}")

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason) -> None:
        logger.info(f"Participant left: {participant.get('id')}, reason: {reason}")
        await task.queue_frame(ParticipantLeftFrame())

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


def _create_hold_music_mixer() -> SoundfileMixer | None:
    """Create hold music mixer if the audio file exists."""
    hold_music_path = Path(__file__).parent / "hold_music.wav"
    if not hold_music_path.exists():
        logger.warning(f"Hold music file not found: {hold_music_path}")
        return None
    return SoundfileMixer(
        sound_files={"hold": str(hold_music_path)},
        default_sound="hold",
        volume=0.5,
        mixing=False,
        loop=True,
    )


async def bot(runner_args: RunnerArguments) -> None:
    """Main bot entry point compatible with Pipecat Cloud."""
    request = AgentRequest.model_validate(runner_args.body)

    transport = DailyTransport(
        request.room_url,
        request.token,
        "Warm Transfer Bot",
        params=DailyParams(
            api_key=os.getenv("DAILY_API_KEY", ""),
            dialin_settings=DailyDialinSettings(
                call_id=request.call_id,
                call_domain=request.call_domain,
            ),
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_mixer=_create_hold_music_mixer(),
        ),
    )

    await run_bot(transport, request.warm_transfer_config, runner_args.handle_sigint)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
