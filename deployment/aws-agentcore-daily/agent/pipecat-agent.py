#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import ipaddress
import json
import os
import select
import socket
import threading
import urllib.request
from urllib.parse import urlparse

from bedrock_agentcore import BedrockAgentCoreApp
from daily import Daily
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.services.aws.llm import AWSBedrockLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

app = BedrockAgentCoreApp()

load_dotenv(override=True)


# =============================================================================
# ICE relay workaround for IPv6-only container environments
# =============================================================================
#
# AgentCore runs containers in an IPv6-only network. Normal Python code that
# needs to talk to IPv4 services (like TURN servers) works transparently —
# DNS64 synthesizes IPv6 addresses and NAT64 translates the packets — so
# Python never even knows it's talking to an IPv4 server.
#
# Daily's libwebrtc, however, doesn't seem to play nicely with the
# environment's DNS64 + NAT64, so it can't reach the TURN servers it needs
# for audio/video. This workaround essentially implements our own DNS64 + NAT64
# translation for Daily's TURN servers specifically:
#
#   1. We resolve TURN hostnames using Python's DNS (which goes through DNS64
#      and works fine).
#
#   2. For each TURN server, we start a local UDP relay on the container's
#      IPv6 address that forwards packets to the real IPv4 TURN server.
#
#   3. We tell libwebrtc (via set_ice_config) to connect to our local relays
#      instead of the original TURN hostnames. From its perspective, the TURN
#      server is at a reachable IPv6 address — no DNS lookup needed.
#
# On a normal network (e.g. local development), the workaround is skipped.
# =============================================================================


def _get_ipv6_address():
    """Get the container's global-scope IPv6 address, or None.

    A global IPv6 address indicates an IPv6-only environment where the
    workaround is needed. Returns None on normal dual-stack networks.
    """
    # Primary: read from /proc/net/if_inet6 (works even without a default IPv6 route)
    try:
        with open("/proc/net/if_inet6") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 6:
                    addr_hex, _idx, _prefix_len, scope, _flags, _ifname = parts[:6]
                    if scope == "00":  # Global scope
                        addr = ":".join(addr_hex[i : i + 4] for i in range(0, 32, 4))
                        return str(ipaddress.IPv6Address(addr))
    except Exception as e:
        logger.debug(f"Could not read /proc/net/if_inet6: {e}")

    # Fallback: dummy-connect trick (requires a default IPv6 route)
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.connect(("2001:db8::1", 80))
        addr = s.getsockname()[0]
        s.close()
        return addr
    except Exception:
        return None


def _start_udp_relay(ipv6_bind_addr, ipv4_target_addr, ipv4_target_port):
    """Start a UDP relay: listens on an IPv6 address, forwards to an IPv4 target.

    This is the packet-translation half of the workaround. libwebrtc sends
    IPv6 UDP packets to our relay, and we re-send them as IPv4 packets to the
    real TURN server (and vice versa for responses).

    Returns the port number the relay is listening on.
    """
    v6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    v6.bind((ipv6_bind_addr, 0))
    relay_port = v6.getsockname()[1]

    def relay_loop():
        client_v4_sockets = {}  # client_addr -> v4_socket
        v4_to_client = {}  # id(v4_socket) -> client_addr

        while True:
            try:
                all_sockets = [v6] + list(client_v4_sockets.values())
                readable, _, _ = select.select(all_sockets, [], [], 120)
                for sock in readable:
                    if sock is v6:
                        data, client_addr = v6.recvfrom(65535)
                        if client_addr not in client_v4_sockets:
                            v4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            client_v4_sockets[client_addr] = v4
                            v4_to_client[id(v4)] = client_addr
                        client_v4_sockets[client_addr].sendto(
                            data, (ipv4_target_addr, ipv4_target_port)
                        )
                    else:
                        data, _ = sock.recvfrom(65535)
                        client_addr = v4_to_client.get(id(sock))
                        if client_addr:
                            v6.sendto(data, client_addr)
            except Exception as e:
                logger.error(f"UDP relay error: {e}")

    threading.Thread(target=relay_loop, daemon=True).start()
    logger.info(
        f"UDP relay started: [{ipv6_bind_addr}]:{relay_port}"
        f" -> {ipv4_target_addr}:{ipv4_target_port}"
    )
    return relay_port


def _fetch_daily_ice_servers(room_url):
    """Fetch TURN/STUN server list and credentials from Daily for the given room.

    We use Python's HTTP stack (which works fine via DNS64 + NAT64) to get the
    server list that libwebrtc would normally discover on its own.
    """
    parsed = urlparse(room_url)
    host_parts = parsed.hostname.split(".")
    if len(host_parts) >= 3 and host_parts[-2] == "daily" and host_parts[-1] == "co":
        domain = host_parts[0]
    else:
        logger.error(f"Could not extract Daily domain from room URL: {room_url}")
        return None

    room = parsed.path.lstrip("/")
    if not room:
        logger.error(f"Could not extract room name from room URL: {room_url}")
        return None

    ice_url = f"https://gs.daily.co/rooms/ice/{domain}/{room}"
    try:
        req = urllib.request.Request(ice_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        ice_servers = data.get("iceConfig", {}).get("iceServers", [])
        logger.info(f"Fetched {len(ice_servers)} ICE server entries from Daily")
        return ice_servers
    except Exception as e:
        logger.error(f"Failed to fetch ICE config from {ice_url}: {e}")
        return None


def _parse_ice_url(url):
    """Parse a TURN/STUN URL into (scheme, host, port, query_string).

    E.g. "turn:hostname:3478?transport=udp" -> ("turn", "hostname", 3478, "transport=udp")
    """
    query = ""
    if "?" in url:
        url, query = url.split("?", 1)

    parts = url.split(":")
    if len(parts) == 3:
        return parts[0], parts[1], int(parts[2]), query
    elif len(parts) == 2:
        scheme, host = parts
        default_port = 5349 if scheme in ("turns", "stuns") else 3478
        return scheme, host, default_port, query
    return None


def _is_udp_transport(scheme, query):
    """Check whether an ICE URL uses UDP transport (the only kind we relay)."""
    if scheme in ("turns", "stuns"):
        return False
    if "transport=tcp" in query:
        return False
    return True


def setup_ice_relay_workaround(room_url):
    """Set up local IPv6-to-IPv4 relays for TURN servers that libwebrtc can't reach.

    Returns an ice_config dict for CallClient.set_ice_config() that points
    libwebrtc at our local relays, or None if the workaround isn't needed.
    """
    ipv6_addr = _get_ipv6_address()
    if not ipv6_addr:
        logger.info("No global IPv6 address found; ICE relay workaround not needed")
        return None

    logger.info(
        f"IPv6-only environment detected (address: {ipv6_addr}), setting up ICE relay workaround"
    )

    ice_servers = _fetch_daily_ice_servers(room_url)
    if not ice_servers:
        return None

    # Reuse relays when multiple ICE entries point to the same server.
    relay_cache = {}  # (ipv4_addr, port) -> relay_port

    modified_servers = []
    for server in ice_servers:
        modified_urls = []
        for url in server.get("urls", []):
            parsed = _parse_ice_url(url)
            if not parsed:
                logger.warning(f"Could not parse ICE URL, skipping: {url}")
                continue

            scheme, host, port, query = parsed

            if not _is_udp_transport(scheme, query):
                logger.debug(f"Skipping non-UDP ICE URL: {url}")
                continue

            # Resolve the hostname ourselves using Python's DNS (works via DNS64).
            try:
                results = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)
                ipv4_addr = results[0][4][0]
            except Exception as e:
                logger.warning(f"Could not resolve {host} to IPv4, skipping: {e}")
                continue

            # Start a relay (or reuse one for the same target).
            cache_key = (ipv4_addr, port)
            if cache_key not in relay_cache:
                relay_port = _start_udp_relay(ipv6_addr, ipv4_addr, port)
                relay_cache[cache_key] = relay_port
            relay_port = relay_cache[cache_key]

            # Rewrite the URL to point to our local IPv6 relay.
            new_url = f"{scheme}:[{ipv6_addr}]:{relay_port}"
            if query:
                new_url += f"?{query}"
            modified_urls.append(new_url)

        if modified_urls:
            modified_servers.append(
                {
                    "urls": modified_urls,
                    "username": server.get("username", ""),
                    "credential": server.get("credential", ""),
                }
            )

    if not modified_servers:
        logger.warning("No UDP TURN/STUN servers could be relayed")
        return None

    logger.info(
        f"ICE relay workaround ready: {len(relay_cache)} relay(s)"
        f" for {len(modified_servers)} ICE server entry/entries"
    )

    # "replace" so libwebrtc only uses our relays (no DNS lookups for originals).
    return {
        "placement": "replace",
        "iceServers": modified_servers,
    }


# =============================================================================
# Bot pipeline
# =============================================================================


async def run_bot(transport: DailyTransport):
    logger.info("Starting bot")

    yield {"status": "initializing bot"}

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    # Automatically uses AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_REGION env vars.
    llm = AWSBedrockLLMService(
        model="us.amazon.nova-2-lite-v1:0",
        params=AWSBedrockLLMService.InputParams(temperature=0.8),
    )

    messages = [
        {
            "role": "system",
            "content": "You are a helpful LLM in a WebRTC call. Your goal is to demonstrate your capabilities in a succinct way. Your output will be spoken aloud, so avoid special characters that can't easily be spoken, such as emojis or bullet points. Respond to what the user said in a creative and helpful way.",
        },
        {"role": "user", "content": "Say hello and briefly introduce yourself."},
    ]

    context = LLMContext(messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # Kick off the conversation.
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await task.cancel()

    @transport.event_handler("on_call_state_updated")
    async def on_call_state_updated(transport, state):
        logger.info(f"Call state updated: {state}")
        if state == "left":
            await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=True)

    task_id = app.add_async_task("voice_agent")

    await runner.run(task)

    app.complete_async_task(task_id)

    yield {"status": "completed"}


# =============================================================================
# Entry points
# =============================================================================


@app.entrypoint
async def agentcore_bot(payload, context):
    """Bot entry point for running on Amazon Bedrock AgentCore Runtime."""
    logger.info(f"Received trigger payload: {payload}")

    room_url = payload.get("room_url")
    if not room_url:
        logger.error("No room_url in trigger payload")
        yield {"status": "error", "message": "room_url not provided in payload"}
        return

    # Set up local relays before creating the transport, so they're ready
    # when libwebrtc starts connecting.
    ice_config = setup_ice_relay_workaround(room_url)

    transport = DailyTransport(
        room_url,
        None,
        "Pipecat Bot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    # Point libwebrtc at our local relays instead of the real TURN hostnames.
    if ice_config:
        transport._client._client.set_ice_config(ice_config)

    async for result in run_bot(transport):
        yield result


# Used for local development
async def bot(runner_args: RunnerArguments):
    """Bot entry point for running locally."""
    room_url = os.getenv("DAILY_ROOM_URL")
    if not room_url:
        raise ValueError("DAILY_ROOM_URL environment variable is not set")

    transport = DailyTransport(
        room_url,
        None,
        "Pipecat Bot",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    async for result in run_bot(transport):
        pass  # Consume the stream


if __name__ == "__main__":
    # NOTE: ideally we shouldn't have to branch for local dev vs AgentCore, but
    # local AgentCore container-based dev doesn't seem to be working, or at
    # least not for this project.
    if os.getenv("PIPECAT_LOCAL_DEV") == "1":
        # Running locally
        from pipecat.runner.run import main

        main()
    else:
        # Running on AgentCore Runtime
        app.run()
