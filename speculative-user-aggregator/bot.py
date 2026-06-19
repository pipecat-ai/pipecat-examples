#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#


from __future__ import annotations

import os
from dataclasses import dataclass
from typing import cast

from dotenv import load_dotenv
from loguru import logger
from openai.types.chat import ChatCompletionUserMessageParam
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMRunFrame,
    SystemFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMUserAggregator,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.cartesia.turns.stt import CartesiaTurnsSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from typing_extensions import Literal

load_dotenv(override=True)


@dataclass
class TurnEagerEndFrame(SystemFrame):
    """Cartesia STT predicted the user is done; speculate on this transcript."""

    transcript: str = ""


@dataclass
class TurnResumeFrame(SystemFrame):
    """Cartesia STT detected the user kept talking after an eager end."""

    pass


class SpeculativeUserAggregator(LLMUserAggregator):
    """User aggregator that speculatively triggers the LLM on eager-end interims.

    - On TurnEagerEndFrame: appends the eager transcript as a user message and
      pushes the context downstream so the LLM starts generating immediately.
    - On TurnResumeFrame: pushes an InterruptionFrame to cancel any in-flight
      LLM/TTS work, then rolls back the speculative user message along with any
      reply the speculative run already committed to the context.
    - On the final TranscriptionFrame: if we already speculated, replaces the
      speculative content with the final transcript in place. If the final
      transcript matches the eager guess we keep the in-flight response;
      otherwise we drop the stale reply, interrupt, and re-run.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._speculative_msg: ChatCompletionUserMessageParam | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, TurnEagerEndFrame):
            await super().process_frame(frame, direction)
            await self._handle_turn_eager_end(frame)
            return
        if isinstance(frame, TurnResumeFrame):
            await super().process_frame(frame, direction)
            await self._handle_turn_resume(frame)
            return
        return await super().process_frame(frame, direction)

    async def _handle_turn_eager_end(self, frame: TurnEagerEndFrame) -> None:
        text = frame.transcript.strip()
        if not text or self._speculative_msg is not None:
            return

        msg: ChatCompletionUserMessageParam = {"role": "user", "content": text}
        self._speculative_msg = msg
        self._context.add_message(msg)

        logger.info(f"turn.eager_end: {text!r}")
        await self.push_context_frame()

    def _find_speculative_index(self) -> int | None:
        """Locate the speculative user message in the shared context by identity.

        Returns its index, or None (after logging a warning) if it is no longer
        present — e.g. the context was reset out from under us.
        """
        for idx, msg in enumerate(self._context.messages):
            if msg is self._speculative_msg:
                return idx
        logger.warning("speculative message not found in context; nothing to roll back")
        return None

    async def _handle_turn_resume(self, frame: TurnResumeFrame) -> None:
        if self._speculative_msg is None:
            return
        logger.info("turn.resume: cancelling speculative response")
        # Cancel in-flight LLM/TTS work first, then mutate the shared context it
        # was generating from.
        await self.push_frame(InterruptionFrame())
        idx = self._find_speculative_index()
        if idx is not None:
            # Drop the speculative user message and anything the speculative run
            # appended after it (e.g. an assistant reply that completed before
            # the user resumed), so we never keep a response to a turn the user
            # did not finish.
            dropped = self._context.messages[idx:]
            del self._context.messages[idx:]
            if len(dropped) > 1:
                logger.info(f"discarded speculative reply ({len(dropped) - 1} message(s))")
        self._speculative_msg = None

    async def push_aggregation(self) -> str:
        if len(self._aggregation) == 0:
            return ""

        aggregation = self.aggregation_string()
        await self.reset()

        if self._speculative_msg is not None:
            previous = self._speculative_msg["content"]

            if isinstance(previous, str) and aggregation.strip() == previous.strip():
                # Final transcript confirms the eager guess: keep the message and
                # the response already in flight; no second LLM run needed.
                self._speculative_msg["content"] = aggregation
                self._speculative_msg = None
                logger.info(
                    f"turn.end matches turn.eager_end; continuing with speculative aggregation: {aggregation!r}"
                )
                return aggregation

            # Final transcript differs from the eager guess. Interrupt the stale
            # response, drop any reply the speculative run already committed to
            # the context, rewrite the user message with the final transcript,
            # and re-run.
            logger.info(
                f"turn.end differs from turn.eager_end; interrupting and re-running "
                f"speculative={previous!r} final={aggregation!r}"
            )
            await self.push_frame(InterruptionFrame())
            idx = self._find_speculative_index()
            if idx is not None and idx + 1 < len(self._context.messages):
                stale = len(self._context.messages) - (idx + 1)
                del self._context.messages[idx + 1 :]
                logger.info(f"discarded stale speculative reply ({stale} message(s))")
            self._speculative_msg["content"] = aggregation
            self._speculative_msg = None
            await self.push_context_frame()
            return aggregation

        # _handle_turn_eager_end was not called for this aggregation
        self._context.add_message(
            {"role": cast(Literal["user"], self.role), "content": aggregation}
        )
        await self.push_context_frame()
        return aggregation


# We store functions so objects don't get instantiated.
# The function will be called when the desired transport gets selected.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


SYSTEM_INSTRUCTION = """You are a friendly voice assistant built using Pipecat, designed for natural, open-ended conversation.

# Personality

Warm, curious, genuine, lighthearted. Knowledgeable but not showy.

# Voice and tone

Speak like a thoughtful friend, not a formal assistant or customer service bot.
Use contractions and casual phrasing—the way people actually talk.
Match the caller's energy: playful if they're playful, grounded if they're serious.
Show genuine interest: "Oh that's interesting" or "Hmm, let me think about that."

# Response style

Keep responses to 1-2 sentences for most exchanges. This is a conversation, not a lecture.
For complex topics, break information into digestible pieces and check in with the caller.
Never use lists, bullet points, or structured formatting—speak in natural prose.
Never say "Great question!" or other hollow affirmations.

# Handling common situations

Didn't catch something: "Sorry, I didn't catch that—could you say that again?"
Don't know the answer: "I'm not sure about that. Want me to look it up?"
Caller seems frustrated: Acknowledge it, try a different approach
Off-topic or unusual request: Roll with it—you can chat about anything

# Topics you can discuss

Anything the caller wants: their day, current events, science, culture, philosophy, personal decisions, interesting ideas. Help think through problems by asking clarifying questions. Use light, natural humor when appropriate.

You were built with speculative user aggregation, triggered by turn.eager_end events coming from the speech to text (STT) service in your audio pipeline.
This makes you prepare responses slightly sooner than normal, reducing the latency between when the user stops talking and you start.
You do not have any further details on your implementation. Don't make up how it works."""


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    logger.info(f"Starting bot")

    stt = CartesiaTurnsSTTService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTurnsSTTService.Settings(model="ink-2"),
    )

    llm = OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(
            model="gpt-5-mini",
            system_instruction=SYSTEM_INSTRUCTION,
        ),
    )

    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTTSService.Settings(
            voice="db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
            model="sonic-3.5",
        ),
    )

    context = LLMContext()
    user_aggregator = SpeculativeUserAggregator(
        context,
        params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    assistant_aggregator = LLMAssistantAggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,  # STT
            user_aggregator,  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            assistant_aggregator,  # Assistant spoken responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_out_sample_rate=44100,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @stt.event_handler("on_turn_eager_end")
    async def on_turn_eager_end(_service, transcript: str):
        await task.queue_frames([TurnEagerEndFrame(transcript=transcript)])

    @stt.event_handler("on_turn_resume")
    async def on_turn_resume(_service):
        await task.queue_frames([TurnResumeFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # Kick off the conversation.
        context.add_message(
            {
                "role": "developer",
                "content": "Please introduce yourself to the user.",
            }
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments) -> None:
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
