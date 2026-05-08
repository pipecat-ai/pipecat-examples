#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Verify per-turn audio URLs on `pipecat.conversation.turn` trace spans.

Pulls turn spans from a local Phoenix server for a given conversation_id (or
the latest one), reads `audio.user.url` / `audio.bot.url`, and probes each
URL to confirm the WAV is reachable and non-trivial in size.

Usage:
    uv run python verify_turn_audio.py
    uv run python verify_turn_audio.py <conversation_id>

Requires Phoenix server reachable at PHOENIX_COLLECTOR_ENDPOINT (default
http://localhost:6006). Pulled in by `uv sync --group phoenix`. Start it in
a separate tab with `uv run phoenix serve`.

Note: presigned S3 GET URLs are signed for the GET method only — HEAD returns
SignatureDoesNotMatch — so we probe size via a 1-byte Range request.
"""

import argparse
import os
import sys
import urllib.error
import urllib.request

import pandas as pd
from dotenv import load_dotenv
from phoenix.client import Client as PhoenixClient

# Load the example's .env so AWS_BUCKET_NAME / AWS_S3_PREFIX are available when
# we need to print the expected S3 key for a span that's missing a URL.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

TURN_SPAN_NAME = "pipecat.conversation.turn"
MIN_WAV_BYTES = 1000  # WAV header alone is 44 B; below ~1 KB is effectively empty

PHOENIX_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
PROJECT_NAME = os.getenv("PHOENIX_PROJECT_NAME") or os.getenv("ARIZE_PROJECT_NAME") or "default"


def probe_wav(url: str) -> tuple[int, int]:
    """Return (status, total_bytes) for a presigned-GET S3 URL.

    Uses a 1-byte Range request so we read just the first byte but still get the
    full object size from the `Content-Range` response header.
    """
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                return resp.status, int(content_range.rsplit("/", 1)[-1])
            return resp.status, int(resp.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception:
        return -1, 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "conversation_id", nargs="?", help="conversation_id to verify; defaults to latest"
    )
    args = parser.parse_args(argv[1:])

    client = PhoenixClient(base_url=PHOENIX_ENDPOINT)
    df = client.spans.get_spans_dataframe(project_identifier=PROJECT_NAME)
    if df is None or df.empty:
        print(f"No spans in project {PROJECT_NAME!r} at {PHOENIX_ENDPOINT}")
        return 1

    turn_df = df[df["name"] == TURN_SPAN_NAME].copy()
    if turn_df.empty:
        print(f"No {TURN_SPAN_NAME!r} spans in project {PROJECT_NAME!r}")
        return 1

    sid_col = "attributes.session.id"
    if sid_col not in turn_df.columns:
        print(f"Expected column {sid_col!r} not found. Available 'session' columns:")
        print("  " + "\n  ".join(c for c in turn_df.columns if "session" in c.lower()))
        return 1

    conversation_id = args.conversation_id
    if conversation_id is None:
        # Show recent ones, then verify the latest.
        recent = (
            turn_df.groupby(sid_col)
            .agg(turns=("start_time", "size"), latest=("start_time", "max"))
            .sort_values("latest", ascending=False)
            .head(10)
        )
        print("No conversation_id passed. Recent conversations:\n")
        print(f"  {'turns':>5}  {'latest':<26}  conversation_id")
        for sid, row in recent.iterrows():
            ts = row["latest"]
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S %Z") if hasattr(ts, "strftime") else str(ts)
            print(f"  {int(row['turns']):>5}  {ts_str:<26}  {sid}")
        print(
            "\nPass a specific conversation_id to verify it:\n"
            f"  uv run python {os.path.basename(sys.argv[0])} <conversation_id>\n"
            "\nDefaulting to the latest (top of the list).\n"
        )
        conversation_id = recent.index[0]

    conv = turn_df[turn_df[sid_col] == conversation_id].copy()
    if conv.empty:
        print(f"No turn spans for conversation_id {conversation_id!r}")
        return 1

    # Phoenix groups custom dotted attributes (e.g. `audio.user.url`,
    # `conversation.turn_number`) into a dict-valued column under the top-level
    # key (`attributes.audio`, `attributes.conversation`) rather than flattening
    # them into separate columns. Read them as nested dicts.
    def _dict_attr(row, col):
        obj = row.get(col)
        return obj if isinstance(obj, dict) else {}

    def _turn_number(row):
        n = _dict_attr(row, "attributes.conversation").get("turn_number")
        return int(n) if n is not None else None

    # Sort by turn_number (extracted from the nested conversation dict).
    conv["_turn_number"] = conv.apply(_turn_number, axis=1)
    conv = conv.sort_values("_turn_number", na_position="last")

    print(f"\nConversation: {conversation_id}")
    print(f"Turns: {len(conv)}\n")
    print(f"{'turn':>4}  {'user':>10}  {'bot':>10}  {'user.wav':>12}  {'bot.wav':>12}")
    print("-" * 56)

    bad_urls = []  # (turn_number, role, url, status_or_marker)
    ok_urls = []  # (turn_number, role, url, size_bytes)
    bad_count = 0
    for _, row in conv.iterrows():
        n_raw = row.get("_turn_number")
        n = int(n_raw) if pd.notna(n_raw) else "?"
        audio = _dict_attr(row, "attributes.audio")
        u_url = (audio.get("user") or {}).get("url")
        b_url = (audio.get("bot") or {}).get("url")

        if u_url:
            u_status, u_len = probe_wav(u_url)
            u_ok = u_status in (200, 206) and u_len > MIN_WAV_BYTES
            u_mark = "OK" if u_ok else f"BAD({u_status})"
            u_size = f"{u_len:,}"
            if u_ok:
                ok_urls.append((n, "user", u_url, u_len))
            else:
                bad_urls.append((n, "user", u_url, u_mark))
        else:
            u_ok, u_mark, u_size = False, "MISSING", "—"
            bad_urls.append((n, "user", None, u_mark))

        if b_url:
            b_status, b_len = probe_wav(b_url)
            b_ok = b_status in (200, 206) and b_len > MIN_WAV_BYTES
            b_mark = "OK" if b_ok else f"BAD({b_status})"
            b_size = f"{b_len:,}"
            if b_ok:
                ok_urls.append((n, "bot", b_url, b_len))
            else:
                bad_urls.append((n, "bot", b_url, b_mark))
        else:
            b_ok, b_mark, b_size = False, "MISSING", "—"
            bad_urls.append((n, "bot", None, b_mark))

        print(f"{n:>4}  {u_mark:>10}  {b_mark:>10}  {u_size:>12}  {b_size:>12}")
        if not (u_ok and b_ok):
            bad_count += 1

    print(f"\n{len(conv) - bad_count}/{len(conv)} turns OK")

    if bad_urls:
        bucket = os.getenv("AWS_BUCKET_NAME", "<bucket>")
        prefix = (os.getenv("AWS_S3_PREFIX") or "pipecat-turn-audio").rstrip("/")
        print("\nBad URLs (open to inspect what's actually there):")
        for turn_number, role, url, marker in bad_urls:
            print(f"  Turn {turn_number} {role} ({marker}):")
            if url:
                print(f"    {url}")
            else:
                # No URL on the span — print the expected S3 key so the user can
                # check whether the WAV exists in the bucket directly. If it
                # does, the upload happened but the span attribute didn't get
                # set (audio-handler / observer bug). If it doesn't, the audio
                # buffer never fired for this turn.
                turn_str = (
                    f"{turn_number:04d}" if isinstance(turn_number, int) else str(turn_number)
                )
                key = f"{prefix}/{conversation_id}/turn-{turn_str}/{role}.wav"
                print(f"    no URL on span — expected: s3://{bucket}/{key}")
                print(f"    check with: aws s3 ls s3://{bucket}/{key}")

    if ok_urls:
        print("\nOK URLs (paste in browser to play):")
        for turn_number, role, url, size in ok_urls:
            print(f"  Turn {turn_number} {role} ({size:,} B):")
            print(f"    {url}")

    return 0 if bad_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
