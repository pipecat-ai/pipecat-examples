#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Deepgram services for the eval harness, named by ``factory:`` in the scenarios.

The eval uses Deepgram for both sides of the test call: Flux TTS speaks the
caller's lines, and Nova-3 transcribes what the bot said so it can be checked.
An OpenAI model judges the replies.

Each scenario runs in its own short-lived harness process, so the HTTP sessions
opened here live for that one run.
"""

import os
from collections.abc import AsyncGenerator

import aiohttp
from pipecat.frames.frames import ErrorFrame, Frame
from pipecat.services.deepgram.stt import DeepgramSegmentedSTTService
from pipecat.services.deepgram.tts import DeepgramHttpTTSService
from pipecat.services.openai.llm import OpenAILLMService


class DeepgramFluxHttpTTSService(DeepgramHttpTTSService):
    """Deepgram Flux TTS over plain HTTP.

    The eval harness needs an HTTP TTS for the caller's voice. Pipecat's
    DeepgramHttpTTSService calls ``/v1/speak``, which only serves Aura voices.
    Flux voices (the Hindi ones included) are served on ``/v2/speak``.
    """

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        params = {
            "model": self._settings.voice,
            "encoding": "linear16",
            "sample_rate": self.sample_rate,
            "container": "none",
        }
        headers = {"Authorization": f"Token {self._api_key}"}
        try:
            async with self._session.post(
                f"{self._base_url}/v2/speak", headers=headers, json={"text": text}, params=params
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    yield ErrorFrame(f"Deepgram TTS HTTP {response.status}: {body}")
                    return
                async for frame in self._stream_audio_frames_from_iterator(
                    response.content.iter_chunked(self.chunk_size), context_id=context_id
                ):
                    yield frame
        except aiohttp.ClientError as e:
            yield ErrorFrame(f"Deepgram TTS request failed: {e}")


def caller_voice(config: dict):
    """The caller's voice. ``voice`` is a Flux voice such as ``flux-arjun-hi``."""
    return DeepgramFluxHttpTTSService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        aiohttp_session=aiohttp.ClientSession(),
        settings=DeepgramFluxHttpTTSService.Settings(voice=config["voice"]),
    )


def bot_transcriber(config: dict):
    """Transcribes the bot's speech. ``language`` is the language the bot speaks."""
    return DeepgramSegmentedSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        aiohttp_session=aiohttp.ClientSession(),
        settings=DeepgramSegmentedSTTService.Settings(
            model="nova-3", language=config.get("language", "hi")
        ),
    )


def judge(config: dict):
    """The LLM that judges the bot's replies."""
    return OpenAILLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAILLMService.Settings(model=config["model"]),
    )
