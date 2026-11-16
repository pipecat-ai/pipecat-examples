"""Expressivity: a Pipecat bot that reads how each turn was said, from its voice and its words.

    transport input -> clips -> VAD -> user turns -> Deepgram STT -> PerceptionReader
        -> PerceptionConclusion -> transport output

The page plays a premade clip or opens its microphone. A clip enters the pipeline as the user's
audio, so both take the same road. Deepgram transcribes the speech, and one ``PerceptionReader``
reads each turn with two models that run here on the CPU: Pipecat Voice Reader hears the audio
(``tone``, ``arousal``, ``laughter``, ``speech_rate`` and ``sarcasm_voice``) and Pipecat Tone reads
the words (``emotion`` and ``sarcasm``). ``conclusion.py`` then weighs the two into one conclusion,
added to the same reading: the turn's ``feeling`` and its ``sarcasm_overall``.

There is no LLM or TTS. Pipecat's RTVI layer tells the page what it shows:

- ``user-started-speaking`` and ``user-stopped-speaking``: the user's turn.
- ``user-input``: what was said, with the reader's reading as its ``perception``.
- ``metrics``: how long each model took over its read, as its classifier's processing time.

The demo's own messages are for the clips. To the page (RTVI server messages):

- ``clips``, once the page is ready: the clips it can play.
- ``clip-started`` and ``clip-finished``, from the player (``clips.py``).

From the page (RTVI client messages):

- ``play-clip``: play the next premade clip, or the one named by ``{"clipId": ...}``.
- ``stop-clip``: stop the clip playing.

Run it locally with ``uv run bot.py`` (SmallWebRTC, no account needed), or over Daily with
``uv run bot.py -t daily``.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.expressive.processors.perception_reader import PerceptionReader
from pipecat.expressive.processors.tone_reader import PipecatToneSource
from pipecat.expressive.processors.voice_reader import PipecatVoiceSource
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.processors.frameworks.rtvi.models import ClientMessage
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.turns.user_start import VADUserTurnStartStrategy
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_processor import UserTurnProcessor
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from clips import SAMPLE_RATE, ClipPlayer, load_clips
from conclusion import PerceptionConclusion

load_dotenv(override=True)

#: Seconds of silence after which the VAD says the speech stopped, and a read starts. Long enough
#: that a breath mid-sentence doesn't split a turn in two.
VAD_STOP_SECS = 0.6
#: Seconds of silence played after a clip: the VAD's wait, and room for its read to start before the
#: next.
CLIP_SILENCE_SECS = VAD_STOP_SECS + 0.5


def microphone_filter() -> BaseAudioFilter | None:
    """Krisp's voice isolation for the microphone, on Pipecat Cloud only.

    Its SDK and model come with Pipecat Cloud's image, and the deployment turns it on
    (``krisp_viva`` in ``pcc-deploy.toml``). Pipecat's development runner sets ``ENV=local``, and
    there the microphone is heard as it is. A clip enters after the transport's input, so it is
    never filtered.
    """
    if os.environ.get("ENV") == "local":
        return None
    from pipecat.audio.filters.krisp_viva_filter import KrispVivaFilter

    return KrispVivaFilter()


# Lambdas defer building the parameters until the runner has picked the transport.
transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True, audio_in_filter=microphone_filter(), audio_out_enabled=True
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True, audio_in_filter=microphone_filter(), audio_out_enabled=True
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    # The premade clips, played in as the user's audio.
    clips = ClipPlayer(load_clips(), silence_secs=CLIP_SILENCE_SECS)

    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=VAD_STOP_SECS)))

    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])

    # One reader, two sources: Pipecat Tone reads each turn's words, and Pipecat Voice Reader hears
    # its audio. Both run here on the CPU, and their signals go in the turn's one reading. It goes
    # right after the STT, so RTVI sends the reading to the page with the turn's words.
    reader = PerceptionReader(sources=[PipecatToneSource(), PipecatVoiceSource()])

    # Neither model is right alone, so the two are weighed into one conclusion (conclusion.py).
    conclusion = PerceptionConclusion()

    # A turn here is one stretch of speech, the same stretch the reader hears: it starts and stops
    # with the VAD, without waiting for its words. It goes before the STT, so the page learns the
    # speech is over before its reading arrives. Nothing speaks, so there is nothing for a turn to
    # interrupt but the clip being played out.
    user_turns = UserTurnProcessor(
        user_turn_strategies=UserTurnStrategies(
            start=[VADUserTurnStartStrategy(enable_interruptions=False)],
            stop=[
                SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0, wait_for_transcript=False)
            ],
        )
    )

    pipeline = Pipeline(
        [
            transport.input(),  # The microphone
            clips,  # A premade clip, in the microphone's place
            vad,
            user_turns,
            stt,
            reader,  # How each turn was said: its words and its voice
            conclusion,  # What the two readings add up to
            transport.output(),  # The clip being played, to be heard
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
            # A classifier's processing time is how long its read took.
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        # Without its models the reader has nothing to show.
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi: RTVIProcessor):
        await rtvi.send_server_message(
            {"type": "clips", "clips": [clip.describe() for clip in clips.clips]}
        )

    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi: RTVIProcessor, message: ClientMessage):
        if message.type == "play-clip":
            clip_id = message.data.get("clipId") if isinstance(message.data, dict) else None
            if not await clips.play(clip_id):
                await rtvi.send_error_response(message, "There is no such clip to play")
        elif message.type == "stop-clip":
            clips.stop()
        else:
            await rtvi.send_error_response(message, f"Unknown message {message.type!r}")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Bot entry point, for Pipecat's development runner and Pipecat Cloud alike."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
