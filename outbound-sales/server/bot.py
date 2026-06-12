#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""outbound-sales - Hailey, an outbound sales voice agent.

Hailey calls a lead, introduces herself, and tries to reach the person who
handles IT decisions. She either gets transferred or collects the decision
maker's contact info, saves it to results.csv, says thanks, and hangs up.

Required AI services:
- Deepgram (Speech-to-Text)
- OpenAI (LLM)
- Cartesia (Text-to-Speech)

Run a real call (see README for the full flow)::

    uv run bot.py -t daily

Run in eval mode for fast, text-only testing::

    uv run bot.py -t eval
    uv run pipecat eval run scenarios/happy_path.yaml
"""

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndWorkerFrame, FunctionCallResultProperties
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.runner.types import EvalRunnerArguments, RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.transports.websocket.server import WebsocketServerParams
from pipecat.workers.runner import WorkerRunner

from results import append_result
from server_utils import AgentRequest, DialoutSettings, Lead

load_dotenv(override=True)

# Lead used when running evals (`-t eval`), where there's no real call request.
# Override it with `--runner-body lead.json` if a scenario needs a different lead.
EVAL_LEAD = Lead(phone="+15550100001", name="Beau", company="Acme Robotics")


class DialoutManager:
    """Manages dialout attempts with retry logic.

    Handles the complexity of initiating outbound calls with automatic retry
    on failure, up to a configurable maximum number of attempts.

    Args:
        transport: The Daily transport instance for making the dialout
        dialout_settings: Settings containing phone number and optional caller ID
        max_retries: Maximum number of dialout attempts (default: 5)
    """

    def __init__(
        self,
        transport: BaseTransport,
        dialout_settings: DialoutSettings,
        max_retries: int | None = 5,
    ):
        self._transport = transport
        self._phone_number = dialout_settings.phone_number
        self._max_retries = max_retries
        self._attempt_count = 0
        self._is_successful = False

    async def attempt_dialout(self) -> bool:
        """Attempt to start a dialout call.

        Returns:
            True if dialout attempt was initiated, False if max retries reached
            or call already successful
        """
        if self._attempt_count >= self._max_retries:
            logger.error(
                f"Maximum retry attempts ({self._max_retries}) reached. Giving up on dialout."
            )
            return False

        if self._is_successful:
            logger.debug("Dialout already successful, skipping attempt")
            return False

        self._attempt_count += 1
        logger.info(
            f"Attempting dialout (attempt {self._attempt_count}/{self._max_retries}) to: {self._phone_number}"
        )

        await self._transport.start_dialout({"phoneNumber": self._phone_number})
        return True

    def mark_successful(self):
        """Mark the dialout as successful to prevent further retry attempts."""
        self._is_successful = True

    @property
    def is_successful(self) -> bool:
        """Whether the dial-out has been answered."""
        return self._is_successful

    def should_retry(self) -> bool:
        """Check if another dialout attempt should be made."""
        return self._attempt_count < self._max_retries and not self._is_successful


@dataclass
class CallResult:
    """What we learned on one call. Written to results.csv when the call ends."""

    call_id: str
    lead: Lead
    contact: dict | None = None
    end_reason: str | None = None
    notes: str = ""
    # True once end_call has started the graceful pipeline shutdown.
    ending: bool = False

    @property
    def outcome(self) -> str:
        if self.contact:
            return "contact_captured"
        # "hung_up" means the call ended without Hailey calling end_call,
        # e.g. the callee hung up on her.
        return self.end_reason or "hung_up"

    def to_row(self) -> dict:
        contact = self.contact or {}
        return {
            "call_id": self.call_id,
            "lead_phone": self.lead.phone,
            "lead_name": self.lead.name or "",
            "lead_company": self.lead.company or "",
            "outcome": self.outcome,
            "contact_name": contact.get("name", ""),
            "contact_role": contact.get("role", ""),
            "contact_phone": contact.get("phone", ""),
            "contact_email": contact.get("email", ""),
            "notes": self.notes,
        }


def system_prompt(lead: Lead) -> str:
    if lead.name:
        lead_line = f"The lead list says this number belongs to {lead.name}"
        lead_line += f" at {lead.company}." if lead.company else "."
        greeting = f'"Hi, this is Hailey from Pipecat Labs. Am I speaking with {lead.name}?"'
    else:
        lead_line = "You don't know the name of the person who will answer."
        greeting = '"Hi, this is Hailey from Pipecat Labs." Then ask who you are speaking with.'

    return f"""You are Hailey, a friendly sales development representative at Pipecat Labs. You are on an outbound phone call. {lead_line}

This is a real phone conversation: your replies are spoken aloud. Keep them short (one or two sentences), warm, and natural. Never use lists, emojis, or any formatting that can't be spoken.

Your goal: find out who handles IT decisions at this company and get their contact information (name, role, and a phone number or email), or get transferred to them directly.

Follow this flow:
1. The person answering speaks first. Greet them with: {greeting}
2. Briefly explain why you're calling: Pipecat Labs helps companies add AI voice agents to their phone systems, and you'd love to share details with whoever runs IT.
3. Ask who handles IT decisions and how to reach them.
4. If they offer to transfer you, thank them briefly and stop talking. Do not introduce yourself again until the new person actually speaks. When they do, introduce yourself and continue from step 2. If you get transferred to the decision maker, you still want their direct contact info for follow-up.
5. Once you have the decision maker's name, role, and a phone number or email, call save_contact_info.
6. Always end the call yourself: thank them, say goodbye, and then call end_call with the right reason.

Rules:
- If they decline, aren't interested, or ask to be removed from your list: apologize once, thank them, say goodbye, and call end_call with reason "refused". Never argue or push back.
- If this is clearly a wrong number, apologize, say goodbye, and call end_call with reason "wrong_number".
- Don't ask again for information you already have.
- Never invent contact information. Only save what the person actually told you."""


async def run_bot(
    transport: BaseTransport,
    runner_args: RunnerArguments,
    *,
    lead: Lead,
    dialout_settings: DialoutSettings | None,
    call_id: str,
    save_results: bool,
) -> None:
    """Run Hailey for one session.

    Args:
        transport: The transport for this session (Daily for real calls, the
            eval websocket transport for `-t eval` runs).
        runner_args: Runner session arguments.
        lead: Who we're calling (name personalizes the greeting).
        dialout_settings: Dial-out settings for real calls; None on eval runs.
        call_id: Identifier for this call, minted by dialer.py ("eval" on eval runs).
        save_results: Whether to append an outcome row to results.csv at call end.
    """
    logger.info(f"Starting bot for call {call_id} to {lead.phone}")

    result = CallResult(call_id=call_id, lead=lead)

    # Speech-to-Text service
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    # Text-to-Speech service
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice=os.getenv("CARTESIA_VOICE_ID", "71a7ad14-091c-4e8e-a314-022ece01c121"),
        ),
    )

    # LLM service
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            system_instruction=system_prompt(lead),
        ),
    )

    async def save_contact_info(
        params: FunctionCallParams, name: str, role: str, phone: str = "", email: str = ""
    ):
        """Save the IT decision maker's contact information.

        Call this once the person on the call has told you who handles IT
        decisions and given you at least one way to reach them.

        Args:
            name: The decision maker's full name.
            role: Their role, e.g. "IT Director" or "CTO".
            phone: Their phone number, if given.
            email: Their email address, if given.
        """
        if not phone and not email:
            await params.result_callback(
                {"status": "error", "message": "Need at least a phone number or an email."}
            )
            return
        result.contact = {"name": name, "role": role, "phone": phone, "email": email}
        logger.info(f"Call {call_id}: saved contact info for {name} ({role})")
        await params.result_callback({"status": "saved"})

    async def end_call(params: FunctionCallParams, reason: str, notes: str = ""):
        """End the phone call. Only call this after you have said goodbye.

        Args:
            reason: Why the call is ending. One of: "contact_captured",
                "transferred_no_info", "refused", "wrong_number", "other".
            notes: Optional one-line note about how the call went.
        """
        result.end_reason = reason
        result.notes = notes
        logger.info(f"Call {call_id}: ending call ({reason})")
        # Don't run the LLM again; the goodbye was already spoken before this call.
        await params.result_callback(
            {"status": "ending"}, properties=FunctionCallResultProperties(run_llm=False)
        )
        # Drain the in-flight goodbye and function-call events first: the eval
        # websocket server closes its connection as soon as the EndFrame passes
        # the input transport, so anything still queued would be lost.
        await worker.flush_pipeline()
        # EndWorkerFrame flows upstream and shuts the pipeline down gracefully.
        result.ending = True
        await params.llm.push_frame(EndWorkerFrame(), FrameDirection.UPSTREAM)

    # Direct functions listed in the context are registered with the LLM automatically
    context = LLMContext(tools=[save_contact_info, end_call])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # Pipeline - assembled from reusable components
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
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
        ),
    )

    # Dial-out only applies to real calls; eval runs get minimal handlers below.
    if dialout_settings is not None:
        # Initialize dialout manager
        dialout_manager = DialoutManager(transport, dialout_settings)

        @transport.event_handler("on_joined")
        async def on_joined(transport, data):
            await dialout_manager.attempt_dialout()

        @transport.event_handler("on_dialout_answered")
        async def on_dialout_answered(transport, data):
            logger.debug(f"Dial-out answered: {data}")
            dialout_manager.mark_successful()

        @transport.event_handler("on_dialout_stopped")
        async def on_dialout_stopped(transport, data):
            logger.debug(f"Dial-out stopped: {data}")
            # Stopped before being answered means busy or no answer.
            if not dialout_manager.is_successful:
                result.end_reason = "no_answer"
            if not result.ending:
                await worker.cancel()

        @transport.event_handler("on_dialout_error")
        async def on_dialout_error(transport, data: Any):
            logger.error(f"Dial-out error, retrying: {data}")

            if dialout_manager.should_retry():
                await dialout_manager.attempt_dialout()
            else:
                logger.error("No more retries allowed, stopping bot.")
                result.end_reason = "dialout_error"
                await worker.cancel()

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Client disconnected")
            # If Hailey already ended the call, the pipeline is shutting down
            # gracefully; cancelling now would cut off that shutdown.
            if not result.ending:
                await worker.cancel()

    else:

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Client connected")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Client disconnected")
            if result.end_reason is None:
                await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)

    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        # The outcome row doubles as the "this call finished" signal for
        # dialer.py, so it must be written no matter how the call ended.
        if save_results:
            append_result(result.to_row())
            logger.info(f"Call {call_id}: recorded outcome '{result.outcome}'")


async def bot(runner_args: RunnerArguments):
    """Main bot entry point."""

    # Behavioral evals: run with `-t eval` to drive this bot via `pipecat eval`.
    # Eval runs don't dial out: the harness connects over a local WebSocket.
    if isinstance(runner_args, EvalRunnerArguments):
        transport = await create_transport(
            runner_args,
            {
                "eval": lambda: WebsocketServerParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                ),
            },
        )
        lead = Lead.model_validate(runner_args.body) if runner_args.body else EVAL_LEAD
        await run_bot(
            transport,
            runner_args,
            lead=lead,
            dialout_settings=None,
            call_id="eval",
            save_results=False,
        )
        return

    try:
        request = AgentRequest.model_validate(runner_args.body)

        transport = DailyTransport(
            request.room_url,
            request.token,
            "Hailey (Outbound Sales)",
            params=DailyParams(
                api_key=os.getenv("DAILY_API_KEY"),
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )

        await run_bot(
            transport,
            runner_args,
            lead=request.lead,
            dialout_settings=request.dialout_settings,
            call_id=request.call_id,
            save_results=True,
        )

    except Exception as e:
        logger.error(f"Error running bot: {e}")
        raise e


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
