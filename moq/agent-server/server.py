#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Run a MoQ direct-mode host: one process, many calls, no ``/start``.

Wires the bot in ``bot.py`` to the :class:`MOQDirectHost` in
``direct_host.py`` and runs it. Unlike a single ``-t moq`` pipecat bot (one
bot per ``/start`` request), this is a long-lived process that dials a relay
once and runs a fresh pipeline for every client that announces itself.

Usage:
    # Local dev: run a moq relay (e.g. `just relay` in the moq repo on
    # :4443), then point the host at it. Clients announce under request/*.
    uv run server.py --relay-url http://localhost:4443 --no-verify-ssl

    # Deployed: dial a relay with authenticated, namespaced prefixes.
    uv run server.py \\
        --relay-url https://relay.example.com \\
        --request-prefix demo/pipecat/request \\
        --response-prefix demo/pipecat/response

    # Platforms that start the process without arguments.
    uv run server.py --from-env
"""

import argparse
import asyncio
import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.transports.moq.transport import MOQParams

from bot import run_bot
from direct_host import (
    DEFAULT_PEER_WAIT_SECS,
    DEFAULT_RELAY_URL,
    DEFAULT_REQUEST_PREFIX,
    DEFAULT_RESPONSE_PREFIX,
    MOQDirectHost,
)

load_dotenv(override=True)


async def _run(args: argparse.Namespace) -> None:
    params = MOQParams(audio_in_enabled=True, audio_out_enabled=True)

    if args.from_env:
        host = MOQDirectHost.from_env(params, run_bot)
    else:
        host = MOQDirectHost(
            params,
            run_bot,
            relay_url=args.relay_url,
            request_prefix=args.request_prefix,
            response_prefix=args.response_prefix,
            verify_ssl=not args.no_verify_ssl,
            max_sessions=args.max_sessions,
            peer_wait_secs=args.peer_wait_secs,
            host_idle_secs=args.host_idle_secs or None,
        )

    logger.info("MoQ direct host ready; waiting for clients to announce")
    await host.run()


def main() -> None:
    """Entry point — run with ``uv run server.py``."""
    parser = argparse.ArgumentParser(description="MoQ direct-mode voice-agent host")
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Take all transport settings from MOQ_* variables (see direct_host.py).",
    )
    parser.add_argument("--relay-url", default=os.getenv("MOQ_RELAY_URL", DEFAULT_RELAY_URL))
    parser.add_argument("--request-prefix", default=DEFAULT_REQUEST_PREFIX)
    parser.add_argument("--response-prefix", default=DEFAULT_RESPONSE_PREFIX)
    parser.add_argument("--max-sessions", type=int, default=8)
    parser.add_argument(
        "--peer-wait-secs",
        type=float,
        default=DEFAULT_PEER_WAIT_SECS,
        help="Per-session wait for the announcing client's media.",
    )
    parser.add_argument(
        "--host-idle-secs",
        type=float,
        default=0,
        help="Exit after this long with no live calls; 0 runs until Ctrl-C.",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Skip TLS verification (self-signed relays; moot over a Unix socket).",
    )
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
