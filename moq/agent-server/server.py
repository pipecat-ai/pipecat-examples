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

Every flag defaults from the matching ``MOQ_*`` variable (see
``env.example``), so a platform that starts the process without arguments
can configure it entirely from the environment.

Usage:
    # Local dev: run a moq relay (e.g. `just relay` in the moq repo on
    # :4443), then point the host at it. Clients announce under request/*.
    uv run server.py --relay-url http://localhost:4443 --no-verify-ssl

    # Deployed: dial a relay with authenticated, namespaced prefixes.
    uv run server.py \\
        --relay-url https://relay.example.com \\
        --request-prefix demo/pipecat/request \\
        --response-prefix demo/pipecat/response
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

# Exported variables win over .env, so a deploy recipe that exports
# MOQ_RELAY_URL isn't clobbered by a dev .env left in the checkout.
load_dotenv()


REQUIRED_API_KEYS = ("DEEPGRAM_API_KEY", "OPENAI_API_KEY", "CARTESIA_API_KEY")


def _env(name: str, default: str) -> str:
    """Read a variable, treating one that is set but empty as unset.

    ``KEY=`` is what a blank .env line or a platform's env UI produces, and
    ``float("")`` would otherwise crash the host.
    """
    return os.getenv(name) or default


def _env_flag(name: str) -> bool:
    return _env(name, "").strip().lower() in ("1", "true", "yes", "on")


async def _run(args: argparse.Namespace) -> None:
    missing = [name for name in REQUIRED_API_KEYS if not os.getenv(name)]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")

    params = MOQParams(audio_in_enabled=True, audio_out_enabled=True)

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
    parser = argparse.ArgumentParser(
        description="MoQ direct-mode voice-agent host",
        epilog="Each flag defaults from the MOQ_* variable named in its help.",
    )
    parser.add_argument(
        "--relay-url",
        default=_env("MOQ_RELAY_URL", DEFAULT_RELAY_URL),
        help="The MoQ relay to dial (MOQ_RELAY_URL).",
    )
    parser.add_argument(
        "--request-prefix",
        default=_env("MOQ_REQUEST_PREFIX", DEFAULT_REQUEST_PREFIX),
        help="Prefix clients announce their microphones under (MOQ_REQUEST_PREFIX).",
    )
    parser.add_argument(
        "--response-prefix",
        default=_env("MOQ_RESPONSE_PREFIX", DEFAULT_RESPONSE_PREFIX),
        help="Prefix the bot publishes its replies under (MOQ_RESPONSE_PREFIX).",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=int(_env("MOQ_MAX_SESSIONS", "8")),
        help="Concurrent pipelines; further clients wait (MOQ_MAX_SESSIONS).",
    )
    parser.add_argument(
        "--peer-wait-secs",
        type=float,
        default=float(_env("MOQ_PEER_WAIT_SECS", str(DEFAULT_PEER_WAIT_SECS))),
        help="Per-session wait for the announcing client's media (MOQ_PEER_WAIT_SECS).",
    )
    parser.add_argument(
        "--host-idle-secs",
        type=float,
        default=float(_env("MOQ_HOST_IDLE_SECS", "0")),
        help="Exit after this long with no live calls; 0 runs until Ctrl-C (MOQ_HOST_IDLE_SECS).",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        default=_env_flag("MOQ_TLS_INSECURE"),
        help="Skip TLS verification for self-signed relays (MOQ_TLS_INSECURE=1).",
    )
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
