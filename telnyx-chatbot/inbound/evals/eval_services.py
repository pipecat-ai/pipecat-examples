#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Services the eval harness uses, named by `factory:` in the scenario files.

These are the harness's own services, separate from the bot's: the voice that
speaks the user's lines, the STT that transcribes the bot's audio for the
judge, and the judge LLM.
"""

import os

import aiohttp
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramHttpTTSService
from pipecat.services.openai.llm import OpenAILLMService


def voice(config):
    """The user's voice: Deepgram Aura over HTTP."""
    return DeepgramHttpTTSService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        aiohttp_session=aiohttp.ClientSession(),
        settings=DeepgramHttpTTSService.Settings(voice=config["voice"]),
    )


def transcriber(config):
    """Transcribes the bot's audio so the judge can read it."""
    return DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])


def judge(config):
    """The LLM that judges each `eval:` expectation."""
    return OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(model=config["model"]),
    )
