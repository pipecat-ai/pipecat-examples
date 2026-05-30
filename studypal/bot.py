#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

from __future__ import annotations

import io
import os
from dataclasses import dataclass

import aiohttp
import tiktoken
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import Frame, InterruptionFrame, LLMRunFrame, SystemFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMUserAggregator,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.cartesia.turns.stt import CartesiaTurnsSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner
from pypdf import PdfReader
from typing_extensions import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionUserMessageParam
    from pipecat.processors.frame_processor import FrameDirection

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
    - On TurnResumeFrame: rolls back the speculative user message and pushes an
      InterruptionFrame to cancel any in-flight LLM/TTS work.
    - On the final TranscriptionFrame: if we already speculated, replaces the
      speculative content with the final transcript in place and skips the
      second LLM run.
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
        logger.info(f"speculating on eager end: {text!r}")
        await self.push_context_frame()

    async def _handle_turn_resume(self, _frame: TurnResumeFrame) -> None:
        if self._speculative_msg is None:
            return
        logger.info("user resumed — cancelling speculative response")
        await self.push_frame(InterruptionFrame())
        try:
            self._context.messages.remove(self._speculative_msg)
        except ValueError:
            pass
        self._speculative_msg = None

    async def push_aggregation(self) -> str:
        if len(self._aggregation) == 0:
            return ""

        aggregation = self.aggregation_string()
        await self.reset()

        if self._speculative_msg is not None:
            previous = self._speculative_msg["content"]
            self._speculative_msg["content"] = aggregation
            self._speculative_msg = None

            if isinstance(previous, str) and aggregation.strip() == previous.strip():
                logger.info(
                    f"final transcript matches eager; continuing with speculative aggregation: {aggregation!r}"
                )
                return aggregation

            logger.info(
                f"final differs from eager, re-running: "
                f"speculative={previous!r} final={aggregation!r}"
            )
            await self.push_frame(InterruptionFrame())
            await self.push_context_frame()
            return aggregation

        self._context.add_message(
            {"role": cast(Literal["user"], self.role), "content": aggregation}
        )
        await self.push_context_frame()
        return aggregation


# We store functions so objects (e.g. SileroVADAnalyzer) don't get
# instantiated. The function will be called when the desired transport gets
# selected.
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


# Count number of tokens used in model and truncate the content
def truncate_content(*, model: str, content: str) -> str:
    encoding = tiktoken.encoding_for_model(model)
    tokens = encoding.encode(content)

    max_tokens = 10000
    if len(tokens) > max_tokens:
        truncated_tokens = tokens[:max_tokens]
        return encoding.decode(truncated_tokens)
    return content


def create_system_instructions_for_model(*, model: str, article_content: str) -> str:
    article_content = truncate_content(model=model, content=article_content)
    return f"""You are an AI study partner.
Your task is to help the user understand and learn from this article. KEEP YOUR RESPONSES AS SHORT AS POSSIBLE.

Be CONVERSATIONAL. For example, avoid long lists since they can be confusing and unnatural.

Your answers will be read out EXACTLY AS WRITTEN. Be sure not to use abbreviations, markdown formatting, non-speech characters like (~^*), LaTex, emojis, etc.

The user will also speak their responses and their transcript will be given to you as user messages. There may be transcription errors, particularly around words that sound similarly.

The users may interrupt you, in which case your full response would not have been spoken and the user may not be aware of your entire response.

You have been given the following article content:

{article_content}
"""


# Main function to extract content from url


async def get_article_content(url: str, aiohttp_session: aiohttp.ClientSession) -> str:
    if "arxiv.org" in url:
        return await get_arxiv_content(url, aiohttp_session)
    else:
        return await get_wikipedia_content(url, aiohttp_session)


# Helper function to extract content from Wikipedia url using the Wikipedia API


async def get_wikipedia_content(url: str, aiohttp_session: aiohttp.ClientSession) -> str:
    # Extract the article title from the URL
    # Example: https://en.wikipedia.org/wiki/Python_(programming_language) -> Python_(programming_language)
    try:
        title = url.split("/wiki/")[-1]
        # Determine the language subdomain (default to 'en')
        if "wikipedia.org" in url:
            lang = url.split("://")[1].split(".")[0]
        else:
            lang = "en"

        # Use Wikipedia's API to get plain text content
        api_url = f"https://{lang}.wikipedia.org/w/api.php"

        async with aiohttp_session.get(
            api_url,
            params={
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "titles": title,
                "explaintext": 1,
                "exsectionformat": "plain",
            },
        ) as response:
            if response.status != 200:
                return "Failed to download Wikipedia article."

            data = await response.json()
            pages = data.get("query", {}).get("pages", {})

            for page_id, page_data in pages.items():
                if page_id == "-1":
                    return "Wikipedia article not found."
                extract = page_data.get("extract", "")
                if extract:
                    return extract
                else:
                    return "Failed to extract Wikipedia article content."

            return "Failed to extract Wikipedia article content."
    except Exception as e:
        logger.error(f"Error extracting Wikipedia content: {e}")
        return f"Failed to extract Wikipedia article: {str(e)}"


# Helper function to extract content from arXiv url


async def get_arxiv_content(url: str, aiohttp_session: aiohttp.ClientSession) -> str:
    if "/abs/" in url:
        url = url.replace("/abs/", "/pdf/")
    if not url.endswith(".pdf"):
        url += ".pdf"

    async with aiohttp_session.get(url) as response:
        if response.status != 200:
            return "Failed to download arXiv PDF."

        content = await response.read()
        pdf_file = io.BytesIO(content)
        pdf_reader = PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    cartesia_api_key = os.getenv("CARTESIA_API_KEY")
    if not cartesia_api_key:
        raise ValueError("CARTESIA_API_KEY is required")

    logger.info(f"Starting bot")

    url = input("Enter the URL of the article you would like to talk about: ")

    # Set up headers with User-Agent for all requests
    headers = {
        "User-Agent": "StudyPal/2.0 (Educational bot; https://github.com/pipecat-ai/pipecat-examples)"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        article_content = await get_article_content(url, session)

        stt = CartesiaTurnsSTTService(
            api_key=cartesia_api_key, settings=CartesiaTurnsSTTService.Settings(model="ink-2")
        )

        tts = CartesiaTTSService(
            api_key=cartesia_api_key,
            settings=CartesiaTTSService.Settings(
                voice="4d2fd738-3b3d-4368-957a-bb4805275bd9",
                model="sonic-latest",
            ),
        )

        llm_model = "gpt-5-mini"
        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            settings=OpenAILLMService.Settings(
                model=llm_model,
                system_instruction=create_system_instructions_for_model(
                    model=llm_model, article_content=article_content
                ),
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
                stt,
                user_aggregator,  # User responses
                llm,  # LLM
                tts,  # TTS
                transport.output(),  # Transport bot output
                assistant_aggregator,  # Assistant spoken responses
            ]
        )

        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(
                audio_out_sample_rate=44100,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        )

        @stt.event_handler("on_turn_eager_end")
        async def on_turn_eager_end(service: CartesiaTurnsSTTService, transcript: str) -> None:
            await worker.queue_frames([TurnEagerEndFrame(transcript=transcript)])

        @stt.event_handler("on_turn_resume")
        async def on_turn_resume(service: CartesiaTurnsSTTService) -> None:
            await worker.queue_frames([TurnResumeFrame()])

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport: BaseTransport, client) -> None:
            logger.info(f"Client connected")
            # Kick off the conversation.
            context.add_message(
                {
                    "role": "user",
                    "content": "Hello! I'm ready to discuss the article with you.",
                }
            )
            await worker.queue_frames([LLMRunFrame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport: BaseTransport, client) -> None:
            logger.info(f"Client disconnected")
            await worker.cancel()

        runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

        await runner.add_workers(worker)
        await runner.run()


async def bot(runner_args: RunnerArguments) -> None:
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
