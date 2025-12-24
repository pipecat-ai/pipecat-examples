# SPDX-License-Identifier: BSD-2-Clause
"""Example: Vonage serializer + custom WS transport + OpenAI STT/LLM/TTS."""

from __future__ import annotations

import asyncio
import os
import time

import jwt
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.serializers.vonage import VonageFrameSerializer
from pipecat.services.openai import OpenAILLMService, OpenAISTTService, OpenAITTSService
from pipecat.transports.network.websocket_server import WebsocketServerParams
from pipecat.transports.vonage.audio_connector import VonageAudioConnectorTransport

# ---- Constants ---------------------------------------------------------------

WS_HOST: str = "0.0.0.0"
WS_PORT: int = 8005
SESSION_TIMEOUT_SECONDS: int = 60 * 3  # 3 minutes
AUDIO_OUT_SAMPLE_RATE: int = 24_000

SYSTEM_INSTRUCTION: str = (
    "You are OpenAI Chatbot, a friendly, helpful robot. "
    "Your output will be converted to audio, so avoid special characters. "
    "Respond to the user in a creative, helpful way. Keep responses brief—"
    "one or two sentences."
)

# Load environment variables from .env
load_dotenv()


def generate_opentok_jwt(api_key: str | None, api_secret: str | None) -> str | None:
    """Generate OpenTok JWT for X-OPENTOK-AUTH, or None if missing creds."""
    if not api_key or not api_secret:
        logger.warning(
            "Vonage example: VONAGE_API_KEY or VONAGE_API_SECRET missing; "
            "hang-up via OpenTok REST will be disabled."
        )
        return None

    now = int(time.time())
    payload = {
        "iss": api_key,
        "ist": "project",
        "iat": now,
        "exp": now + 300,  # 5 minutes
    }
    return jwt.encode(payload, api_secret, algorithm="HS256")


async def run_bot_websocket_server() -> None:
    # Vonage / OpenTok config for hang-up via force-disconnect REST API
    project_id = os.getenv("VONAGE_API_KEY")
    api_secret = os.getenv("VONAGE_API_SECRET")
    session_id = os.getenv("VONAGE_SESSION_ID")

    opentok_jwt = generate_opentok_jwt(project_id, api_secret)

    # The VonageFrameSerializer uses these values to implement hang-up via:
    # DELETE /v2/project/{project_id}/session/{session_id}/connection/{connection_id}
    # NOTE: connection_id is NOT set here; it will be injected at runtime via set_connection_id().
    serializer = VonageFrameSerializer(
        VonageFrameSerializer.InputParams(
            auto_hang_up=True,
            send_clear_audio_event=True,
            project_id=project_id,
            session_id=session_id,
            jwt=opentok_jwt,
        )
    )

    ws_transport = VonageAudioConnectorTransport(
        host=WS_HOST,
        port=WS_PORT,
        params=WebsocketServerParams(
            serializer=serializer,
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=True,
            vad_analyzer=SileroVADAnalyzer(),
            session_timeout=SESSION_TIMEOUT_SECONDS,
        ),
    )

    stt = OpenAISTTService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-transcribe",
        prompt=("Expect words based on questions across technology, science, and culture."),
    )

    tts = OpenAITTSService(
        api_key=os.getenv("OPENAI_API_KEY"),
        voice="coral",
        instructions="There may be literal '\\n' characters; ignore them when speaking.",
    )

    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"))

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            ws_transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            ws_transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_out_sample_rate=AUDIO_OUT_SAMPLE_RATE,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @ws_transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client) -> None:
        logger.info("Client connected")
        messages.append({"role": "system", "content": "Please introduce yourself to the user."})
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @ws_transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client) -> None:
        logger.info("Client disconnected")

        # Read the latest connectionId written by connect_and_stream.py
        load_dotenv(override=True)
        conn_id = os.getenv("VONAGE_CONNECTION_ID")
        if conn_id:
            logger.info(f"Setting serializer connection_id from env: {conn_id}")
            serializer.set_connection_id(conn_id)
        else:
            logger.warning(
                "VONAGE_CONNECTION_ID is not set in env. "
                "Vonage hang-up via force-disconnect API will be skipped."
            )

        await task.cancel()  # This will inject a CancelFrame → serializer triggers hang-up.

    @ws_transport.event_handler("on_websocket_ready")
    async def on_websocket_ready(_client) -> None:
        logger.info("Server WebSocket ready")

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


if __name__ == "__main__":
    asyncio.run(run_bot_websocket_server())
