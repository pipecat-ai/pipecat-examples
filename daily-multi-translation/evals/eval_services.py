#
# Copyright (c) 2024–2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Services the eval harness builds from a scenario's ``factory:`` keys."""

import os

from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService


def judge(config):
    """The LLM that decides each ``eval:`` criterion."""
    return OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(model=config["model"]),
    )


def transcriber(config):
    """Deepgram transcribes what the bot said, in the language the bot speaks."""
    return DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramSTTService.Settings(language=config["language"]),
    )
