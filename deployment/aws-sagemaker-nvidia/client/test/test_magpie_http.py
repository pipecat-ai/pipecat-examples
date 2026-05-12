#!/usr/bin/env python3
"""
Test client for the Magpie TTS SageMaker endpoint.

Sends a synthesis request and saves the response as a WAV file.
Requires only aioboto3 (no ffmpeg — WAV conversion uses stdlib wave).

Usage:
    python client/test_http.py
    python client/test_http.py --text "Custom text to synthesize"
    python client/test_http.py --text "Hello" --output ./tmp/hello.wav
"""

import argparse
import asyncio
import json
import os
import wave
from pathlib import Path

import aioboto3

# ── .env loader ───────────────────────────────────────────────────────────────


def _load_env(path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ (no-op if missing)."""
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


# ── Main ──────────────────────────────────────────────────────────────────────


async def run(args: argparse.Namespace, region: str) -> None:
    body = json.dumps(
        {
            "text": args.text,
            "voice_name": args.voice,
            "language_code": args.language,
            "sample_rate_hz": args.sample_rate,
        }
    )

    session = aioboto3.Session(
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=region,
    )

    print("→ Invoking endpoint ...")
    try:
        async with session.client("sagemaker-runtime") as client:
            response = await client.invoke_endpoint(
                EndpointName=args.endpoint,
                ContentType="application/json",
                Accept="application/octet-stream",
                Body=body,
            )
            pcm_data = await response["Body"].read()
    except Exception as exc:
        print()
        print(f"ERROR: {exc}")
        print("  Check that the endpoint is InService: ./scripts/list_endpoints.sh")
        raise SystemExit(1)

    if not pcm_data:
        print()
        print("ERROR: Endpoint returned an empty response.")
        print("  Check the endpoint logs: ./scripts/logs_endpoint.sh")
        raise SystemExit(1)

    print("→ Saving WAV ...")
    _save_wav(pcm_data, args.sample_rate, args.output)

    print()
    print(f"✓ Audio saved to {args.output}")
    print()
    print("  To play:")
    print(f"    afplay {args.output}        # macOS")
    print(f"    ffplay {args.output}        # cross-platform")
    print()


def main() -> None:
    _load_env(Path(__file__).parent.parent.parent / ".env")

    parser = argparse.ArgumentParser(
        description="Test the Magpie TTS SageMaker endpoint",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--text",
        default="Hello! This is a test of the NVIDIA Magpie TTS endpoint deployed on AWS SageMaker.",
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
        default=int(os.environ.get("MAGPIE_SAMPLE_RATE_HZ", "24000")),
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("SAGEMAKER_MAGPIE_ENDPOINT_NAME", ""),
        help="SageMaker endpoint name (overrides SAGEMAKER_MAGPIE_ENDPOINT_NAME in .env)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./tmp/magpie-test.wav"),
    )
    args = parser.parse_args()

    if not args.endpoint:
        parser.error(
            "Endpoint name required. Set SAGEMAKER_MAGPIE_ENDPOINT_NAME in .env or pass --endpoint <name>."
        )

    region = os.environ.get("AWS_REGION", "us-west-2")

    print()
    print("━" * 60)
    print(" Testing SageMaker Endpoint")
    print()
    print(f" Endpoint   : {args.endpoint}")
    print(f" Region     : {region}")
    print(f" Voice      : {args.voice}")
    print(f" Language   : {args.language}")
    print(f" Sample rate: {args.sample_rate} Hz")
    print(f" Text       : {args.text}")
    print(f" Output     : {args.output}")
    print("━" * 60)
    print()

    asyncio.run(run(args, region))


if __name__ == "__main__":
    main()
