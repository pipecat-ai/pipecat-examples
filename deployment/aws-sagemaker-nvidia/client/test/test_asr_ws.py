#!/usr/bin/env python3
"""
SageMaker bidirectional-stream test client for the Nemotron ASR wrapper.

Uses SageMaker's HTTP/2 bidi stream API (InvokeEndpointWithBidirectionalStream)
to communicate with the wrapper's /invocations-bidirectional-stream endpoint,
which transparently proxies to NIM's realtime WebSocket.

The client streams audio as base64-encoded PCM16 chunks via
input_audio_buffer.append events and collects transcription results from
conversation.item.input_audio_transcription.completed events.

Falls back to ./tmp/magpie-test.pcm (Magpie TTS output) if no audio is provided.

Usage:
    python client/test/test_asr_ws.py
    python client/test/test_asr_ws.py --audio /path/to/audio.wav
    python client/test/test_asr_ws.py --audio /path/to/audio.pcm --language en-US
"""

import argparse
import asyncio
import base64
import io
import json
import os
import wave
from pathlib import Path

from aws_sdk_sagemaker_runtime_http2.client import SageMakerRuntimeHTTP2Client
from aws_sdk_sagemaker_runtime_http2.config import Config, HTTPAuthSchemeResolver
from aws_sdk_sagemaker_runtime_http2.models import (
    InvokeEndpointWithBidirectionalStreamInput,
    RequestPayloadPart,
    RequestStreamEventPayloadPart,
)
from smithy_aws_core.auth.sigv4 import SigV4AuthScheme
from smithy_aws_core.identity import EnvironmentCredentialsResolver

# ── .env loader ───────────────────────────────────────────────────────────────


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


# ── Audio helpers ─────────────────────────────────────────────────────────────


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _resolve_pcm(audio_arg: str | None, pcm_sample_rate: int) -> tuple[bytes, int, str]:
    """
    Resolve audio input to raw PCM16 bytes + sample rate.

    Priority:
      1. --audio argument (.wav read and extracted, .pcm used as-is)
      2. ./tmp/magpie-test.pcm (Magpie TTS output)
      3. Error

    Returns (pcm_bytes, sample_rate, description).
    """
    if audio_arg:
        path = Path(audio_arg)
        if not path.exists():
            raise SystemExit(f"ERROR: Audio file not found: {audio_arg}")
        if path.suffix.lower() == ".wav":
            with wave.open(str(path), "rb") as wf:
                sr = wf.getframerate()
                pcm = wf.readframes(wf.getnframes())
            return pcm, sr, str(path)
        data = path.read_bytes()
        return data, pcm_sample_rate, f"{path}  (PCM16, {pcm_sample_rate} Hz)"

    fallback = Path("./tmp/magpie-test.pcm")
    if fallback.exists():
        magpie_sr = int(os.environ.get("MAGPIE_SAMPLE_RATE_HZ", "22050"))
        return fallback.read_bytes(), magpie_sr, f"./tmp/magpie-test.pcm  ({magpie_sr} Hz)"

    raise SystemExit(
        "ERROR: No audio file provided and ./tmp/magpie-test.pcm not found.\n"
        "  Provide an audio file:  --audio /path/to/audio.wav"
    )


# ── Bidi stream client ────────────────────────────────────────────────────────

# Audio is sent in 40 ms chunks.
CHUNK_MS = 40


async def run(
    endpoint: str,
    region: str,
    language: str,
    pcm_bytes: bytes,
    sample_rate: int,
) -> None:
    bidi_endpoint = f"https://runtime.sagemaker.{region}.amazonaws.com:8443"
    print(f"→ Connecting to SageMaker bidi stream ({bidi_endpoint}) ...")

    config = Config(
        endpoint_uri=bidi_endpoint,
        region=region,
        aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        auth_scheme_resolver=HTTPAuthSchemeResolver(),
        auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="sagemaker")},
    )
    client = SageMakerRuntimeHTTP2Client(config=config)

    stream_input = InvokeEndpointWithBidirectionalStreamInput(endpoint_name=endpoint)
    stream = await client.invoke_endpoint_with_bidirectional_stream(stream_input)

    print("→ Waiting for stream ...")
    output_future, output_stream = await stream.await_output()

    async def send_json(data: dict) -> None:
        payload = RequestPayloadPart(
            bytes_=json.dumps(data).encode("utf-8"),
            data_type="UTF8",
        )
        await stream.input_stream.send(RequestStreamEventPayloadPart(value=payload))

    # ── 1. Configure transcription session ────────────────────────────────────
    # "model": "nemotron-asr-streaming" selects the Nemotron ASR Streaming model on NIM.
    await send_json(
        {
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_params": {
                    "sample_rate_hz": sample_rate,
                    "num_channels": 1,
                },
                "input_audio_transcription": {
                    "language": language,
                    "model": "cache-aware-parakeet-rnnt-en-US-asr-streaming-sortformer",
                },
            },
        }
    )

    # ── 2. Stream audio in chunks ─────────────────────────────────────────────
    # Commit after every chunk (matches NVIDIA reference client pattern).
    bytes_per_sample = 2  # PCM16
    chunk_samples = int(sample_rate * CHUNK_MS / 1000)
    chunk_bytes = chunk_samples * bytes_per_sample

    print(f"→ Sending audio ({len(pcm_bytes):,} bytes, {CHUNK_MS} ms chunks) ...")
    for offset in range(0, len(pcm_bytes), chunk_bytes):
        chunk = pcm_bytes[offset : offset + chunk_bytes]
        await send_json(
            {"type": "input_audio_buffer.append", "audio": base64.b64encode(chunk).decode()}
        )
        await send_json({"type": "input_audio_buffer.commit"})

    await send_json({"type": "input_audio_buffer.done"})

    # ── 3. Collect transcription events ───────────────────────────────────────
    print("→ Waiting for transcript ...")
    transcript = ""

    while True:
        try:
            event = await asyncio.wait_for(output_stream.receive(), timeout=10.0)
        except asyncio.TimeoutError:
            print("WARNING: No response for 10 seconds — closing session.")
            break
        if event is None:
            break

        raw = getattr(event, "value", None)
        if raw is None:
            continue
        data = getattr(raw, "bytes_", None) or getattr(raw, "bytes", None)
        if not data:
            continue

        try:
            msg = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        event_type = msg.get("type", "")

        if event_type == "conversation.item.input_audio_transcription.delta":
            print(f"  delta: {msg.get('delta', '')}", flush=True)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = msg.get("transcript", "")
            break

        elif event_type == "conversation.item.input_audio_transcription.failed":
            print(f"\nERROR: Transcription failed: {msg}")
            raise SystemExit(1)

        elif event_type == "error":
            raise RuntimeError(f"NIM error: {msg}")

    await stream.input_stream.close()

    if not transcript:
        print()
        print("ERROR: No transcript received.")
        raise SystemExit(1)

    print()
    print(f"✓ Transcript: {transcript}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    _load_env(Path(__file__).parent.parent.parent / ".env")

    parser = argparse.ArgumentParser(
        description="SageMaker bidi-stream test client for Nemotron ASR",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--audio",
        default=None,
        help="Path to audio file (.wav or raw PCM16). Falls back to ./tmp/magpie-test.pcm if omitted.",
    )
    parser.add_argument(
        "--language",
        default=os.environ.get("NEMOTRON_ASR_LANGUAGE_CODE", "en-US"),
        help="BCP-47 language code",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=int(os.environ.get("NEMOTRON_ASR_SAMPLE_RATE_HZ", "16000")),
        help="Sample rate in Hz — only used when input is raw PCM (not WAV)",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("SAGEMAKER_ASR_ENDPOINT_NAME", ""),
        help="SageMaker endpoint name (overrides SAGEMAKER_ASR_ENDPOINT_NAME in .env)",
    )
    args = parser.parse_args()

    if not args.endpoint:
        parser.error(
            "Endpoint name required. Set SAGEMAKER_ASR_ENDPOINT_NAME in .env or pass --endpoint <name>."
        )

    region = os.environ.get("AWS_REGION", "us-west-2")
    pcm_bytes, sample_rate, audio_desc = _resolve_pcm(args.audio, args.sample_rate)

    print()
    print("━" * 60)
    print(" Testing SageMaker Endpoint  [nemotron-asr — bidi-stream]")
    print()
    print(f" Endpoint   : {args.endpoint}")
    print(f" Region     : {region}")
    print(f" Language   : {args.language}")
    print(f" Audio      : {audio_desc}")
    print("━" * 60)
    print()

    asyncio.run(run(args.endpoint, region, args.language, pcm_bytes, sample_rate))


if __name__ == "__main__":
    main()
