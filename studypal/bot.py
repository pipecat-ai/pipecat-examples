#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#


import io
import os

import aiohttp
import tiktoken
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pypdf import PdfReader

load_dotenv(override=True)

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
def truncate_content(content, model_name):
    encoding = tiktoken.encoding_for_model(model_name)
    tokens = encoding.encode(content)

    max_tokens = 10000
    if len(tokens) > max_tokens:
        truncated_tokens = tokens[:max_tokens]
        return encoding.decode(truncated_tokens)
    return content


# Main function to extract content from url


async def get_article_content(url: str, aiohttp_session: aiohttp.ClientSession):
    if "arxiv.org" in url:
        return await get_arxiv_content(url, aiohttp_session)
    else:
        return await get_wikipedia_content(url, aiohttp_session)


# Helper function to extract content from Wikipedia url using the Wikipedia API


async def get_wikipedia_content(url: str, aiohttp_session: aiohttp.ClientSession):
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
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "titles": title,
            "explaintext": 1,
            "exsectionformat": "plain",
        }

        async with aiohttp_session.get(api_url, params=params) as response:
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


async def get_arxiv_content(url: str, aiohttp_session: aiohttp.ClientSession):
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


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    url = input("Enter the URL of the article you would like to talk about: ")

    # Set up headers with User-Agent for all requests
    headers = {
        "User-Agent": "StudyPal/1.0 (Educational bot; https://github.com/pipecat-ai/pipecat-examples)"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        article_content = await get_article_content(url, session)
        article_content = truncate_content(article_content, model_name="gpt-4o-mini")

        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id=os.getenv("CARTESIA_VOICE_ID", "4d2fd738-3b3d-4368-957a-bb4805275bd9"),
            # British Narration Lady: 4d2fd738-3b3d-4368-957a-bb4805275bd9
        )

        llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini")

        messages = [
            {
                "role": "system",
                "content": f"""You are an AI study partner. You have been given the following article content:

    {article_content}

    Your task is to help the user understand and learn from this article in 2 sentences. THESE RESPONSES SHOULD BE ONLY MAX 2 SENTENCES. THIS INSTRUCTION IS VERY IMPORTANT. RESPONSES SHOULDN'T BE LONG.
    """,
            },
        ]

        context = LLMContext(messages)
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )

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

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_out_sample_rate=44100,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        )

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info(f"Client connected")
            # Kick off the conversation.
            messages.append(
                {
                    "role": "system",
                    "content": "Hello! I'm ready to discuss the article with you. What would you like to learn about?",
                }
            )
            await task.queue_frames([LLMRunFrame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info(f"Client disconnected")
            await task.cancel()

        runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

        await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
