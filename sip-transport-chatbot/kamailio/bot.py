#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Voice bot that registers through a self-hosted Kamailio registrar.

The bot sends its REGISTER to a Kamailio instance you run yourself and
answers whatever calls in — a softphone registered to the same Kamailio,
or a call routed from your own PBX. Only signaling flows through
Kamailio; RTP stays direct between the caller and the bot.

Where other SIP examples register against a Daily-provisioned account,
this one is the self-hosted path: the bundled ``kamailio.cfg`` runs on
the official docker image with no auth (lab), so the whole setup needs
no external service or API key — the greeting uses local Kokoro TTS.

Copy ``env.example`` to ``.env``, then, from this directory::

    uv run python bot.py

See ``README.md`` for the Kamailio docker command and the full walkthrough.
"""

import asyncio
import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.transports.sip.connection import SIPConnection
from pipecat.transports.sip.transport import SIPParams, SIPTransport
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

# The bot's AOR: sip:<user>@<domain>. The registrar below is where
# REGISTERs are sent; it is often a different host than the AOR domain.
SIP_USER = os.getenv("SIP_USER", "5001")
SIP_DOMAIN = os.getenv("SIP_DOMAIN", "kamailio.lab")  # AOR domain (realm)
SIP_PASSWORD = os.getenv("SIP_PASSWORD", "bot-password")
SIP_TRANSPORT = os.getenv("SIP_TRANSPORT", "udp")
# Outbound registrar/proxy (host:port). Empty = register at SIP_DOMAIN.
KAMAILIO_REGISTRAR = os.getenv("KAMAILIO_REGISTRAR", "192.0.2.10:5060")

connection_kwargs = dict(
    user=SIP_USER,
    domain=SIP_DOMAIN,
    password=SIP_PASSWORD,
    transport=SIP_TRANSPORT,
    dtmf_mode="rtpevent",
    audio_codecs=("PCMU", "PCMA"),
    # Re-REGISTER before NAT UDP flow timeouts expire; replaces a stale
    # binding after restart (RFC 5626 +sip.instance, lowercase UUID).
    reg_interval=25,
    # Change per deployment: two bots sharing one AOR must not share an
    # instance_id, or each registration replaces the other's binding.
    instance_id="90c6bfb4-13f1-4b29-a8a4-f00a57dbc8d1",
)
if KAMAILIO_REGISTRAR:
    connection_kwargs["registrar"] = KAMAILIO_REGISTRAR

connection = SIPConnection(**connection_kwargs)

transport = SIPTransport(
    connection,
    SIPParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
)

tts = KokoroTTSService(
    # First run downloads the model (~350MB) to the local Kokoro cache.
    settings=KokoroTTSService.Settings(voice="af_heart"),
)

worker = PipelineWorker(
    Pipeline([transport.input(), tts, transport.output()]),
    # A SIP bot spends most of its life waiting for a call; keep the
    # pipeline up instead of timing out after the default idle period.
    idle_timeout_secs=None,
)


async def main():
    # Handlers must be registered before the runner starts: the transport
    # sets up (and fires on_dialin_ready) when the worker starts.
    @transport.event_handler("on_dialin_ready")
    async def on_dialin_ready(transport, address):
        logger.info(f"Registered to SIP server, AOR = {address}")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        await worker.queue_frames([TTSSpeakFrame("Hello from your SIP bot!"), EndFrame()])

    runner = WorkerRunner(handle_sigint=True)
    await runner.add_workers(worker)
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
