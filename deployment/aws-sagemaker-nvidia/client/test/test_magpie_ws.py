#!/usr/bin/env python3
"""
SageMaker bidirectional-stream test client for the Magpie TTS wrapper.

Uses SageMaker's HTTP/2 bidi stream API (InvokeEndpointWithBidirectionalStream)
to communicate with the wrapper's /invocations-bidirectional-stream endpoint,
which transparently proxies to NIM's realtime WebSocket.

The wrapper forwards NIM's JSON protocol verbatim, so this client sends
NIM events as UTF-8 text and receives NIM's JSON responses, decoding the
base64 audio from conversation.item.speech.data events into a WAV file.

Usage:
    python client/test_ws.py
    python client/test_ws.py --text "Custom text to synthesize"
    python client/test_ws.py --text "Hello" --output ./tmp/bidi-test.wav
"""

import argparse
import asyncio
import base64
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


def _save_wav(pcm_data: bytes, sample_rate: int, output: Path) -> None:
    """Wrap raw signed 16-bit mono PCM in a WAV container."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit = 2 bytes per sample
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


# ── Bidi stream client ────────────────────────────────────────────────────────


async def run(
    endpoint: str,
    region: str,
    text: str,
    voice: str,
    language: str,
    sample_rate: int,
    output: Path,
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

    stream_input = InvokeEndpointWithBidirectionalStreamInput(
        endpoint_name=endpoint,
    )

    print("Will invoke endpoint:", endpoint)

    stream = await client.invoke_endpoint_with_bidirectional_stream(stream_input)

    print("Waiting for stream be available...")
    output_future, output_stream = await stream.await_output()

    # ── Helper: send a NIM JSON event ─────────────────────────────────────────
    async def send_json(data: dict) -> None:
        payload = RequestPayloadPart(
            bytes_=json.dumps(data).encode("utf-8"),
            data_type="UTF8",
        )
        await stream.input_stream.send(RequestStreamEventPayloadPart(value=payload))

    # ── 1. Configure synthesis session ────────────────────────────────────────
    await send_json(
        {
            "type": "synthesize_session.update",
            "session": {
                "input_text_synthesis": {
                    "voice_name": voice,
                    "language_code": language,
                },
                "output_audio_params": {
                    "sample_rate_hz": sample_rate,
                },
            },
        }
    )

    print("Sending audio ...")

    # ── 2. Send text ──────────────────────────────────────────────────────────
    await send_json({"type": "input_text.append", "text": text})
    await send_json({"type": "input_text.commit"})
    await send_json({"type": "input_text.done"})

    print("→ Waiting for audio ...")

    # ── 3. Collect audio from NIM JSON events ──────────────────────────────────
    audio_chunks: list[bytes] = []

    while True:
        try:
            event = await asyncio.wait_for(output_stream.receive(), timeout=5.0)
        except asyncio.TimeoutError:
            print("WARNING: No audio received for 5 seconds — closing session.")
            break
        if event is None:
            break

        # ResponseStreamEvent.payload_part.bytes_ contains the raw bytes that
        # the wrapper forwarded from NIM (UTF-8 encoded JSON text).
        raw = getattr(event, "value", None)
        if raw is None:
            continue

        data = getattr(raw, "bytes_", None) or getattr(raw, "bytes", None)
        if not data:
            continue

        try:
            msg = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Binary frame (shouldn't happen with transparent proxy, but handle it)
            audio_chunks.append(data)
            continue

        event_type = msg.get("type", "")

        if event_type == "conversation.item.speech.data":
            chunk_b64 = msg.get("audio", "")
            if chunk_b64:
                audio_chunks.append(base64.b64decode(chunk_b64))
            if msg.get("is_last_chunk"):
                break

        elif event_type == "conversation.item.speech.completed":
            break

        elif event_type == "error":
            raise RuntimeError(f"NIM error: {msg}")

        # Other events (session.created, etc.) are silently ignored.

    # ── 4. Close the session ──────────────────────────────────────────────────
    # The wrapper intercepts this message and closes the NIM WebSocket cleanly.
    await send_json({"type": "session.end"})
    await stream.input_stream.close()

    if not audio_chunks:
        print()
        print("ERROR: No audio received.")
        raise SystemExit(1)

    pcm_data = b"".join(audio_chunks)
    print(f"→ Received {len(pcm_data):,} bytes of PCM — saving WAV ...")
    _save_wav(pcm_data, sample_rate, output)

    print()
    print(f"✓ Audio saved to {output}")
    print()
    print("  To play:")
    print(f"    afplay {output}        # macOS")
    print(f"    ffplay {output}        # cross-platform")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    _load_env(Path(__file__).parent.parent.parent / ".env")

    parser = argparse.ArgumentParser(
        description="SageMaker bidi-stream test client for Magpie TTS",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("SAGEMAKER_MAGPIE_ENDPOINT_NAME", ""),
        help="SageMaker endpoint name (overrides SAGEMAKER_MAGPIE_ENDPOINT_NAME in .env)",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-west-2"),
    )
    parser.add_argument(
        "--text",
        default="Hello! This is a bidirectional stream test of the NVIDIA Magpie TTS endpoint.",
    )
    parser.add_argument(
        "--voice",
        default=os.environ.get("MAGPIE_VOICE", "Magpie-Multilingual.EN-US.Aria"),
    )
    parser.add_argument(
        "--language",
        default=os.environ.get("MAGPIE_LANGUAGE_CODE", "en-US"),
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=int(os.environ.get("MAGPIE_SAMPLE_RATE_HZ", "22050")),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./tmp/magpie-bidi-test.wav"),
    )
    args = parser.parse_args()

    if not args.endpoint:
        parser.error(
            "Endpoint name required. Set SAGEMAKER_MAGPIE_ENDPOINT_NAME in .env or pass --endpoint <name>."
        )

    print()
    print("━" * 60)
    print(" Testing Magpie TTS — SageMaker Bidi Stream")
    print()
    print(f" Endpoint   : {args.endpoint}")
    print(f" Region     : {args.region}")
    print(f" Voice      : {args.voice}")
    print(f" Language   : {args.language}")
    print(f" Sample rate: {args.sample_rate} Hz")
    print(f" Text       : {args.text}")
    print(f" Output     : {args.output}")
    print("━" * 60)
    print()

    asyncio.run(
        run(
            endpoint=args.endpoint,
            region=args.region,
            text=args.text,
            voice=args.voice,
            language=args.language,
            sample_rate=args.sample_rate,
            output=args.output,
        )
    )


if __name__ == "__main__":
    main()
