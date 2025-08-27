#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import asyncio
import sys
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from bot import run_bot
from dotenv import load_dotenv
from fastapi import BackgroundTasks
from loguru import logger
from pipecat.transports.network.webrtc_connection import IceServer, SmallWebRTCConnection
from pipecat.utils.whatsapp.api import (
    WhatsAppApi,
    WhatsAppConnectCall,
    WhatsAppConnectCallValue,
    WhatsAppTerminateCall,
    WhatsAppTerminateCallValue,
    WhatsAppWebhookRequest,
)

# Load environment variables
load_dotenv(override=True)
import os
from typing import Dict

from fastapi import FastAPI, HTTPException, Request

# Store connections by pc_id
ongoing_calls_map: Dict[str, SmallWebRTCConnection] = {}
ice_servers = [
    IceServer(
        urls="stun:stun.l.google.com:19302",
    )
]

# WhatsApp - will be initialized in lifespan
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_WEBHOOK_VERIFICATION_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFICATION_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
whatsapp_api: WhatsAppApi = None


def filter_sdp_for_whatsapp(sdp: str) -> str:
    lines = sdp.splitlines()
    filtered = []
    for line in lines:
        if line.startswith("a=fingerprint:") and not line.startswith("a=fingerprint:sha-256"):
            continue  # drop sha-384 / sha-512
        filtered.append(line)
    return "\r\n".join(filtered) + "\r\n"


async def handle_connect_event(call: WhatsAppConnectCall, background_tasks: BackgroundTasks):
    """Handle a CONNECT event: pre-accept and accept the call."""
    logger.info(f"Incoming call from {call.from_}, call_id: {call.id}")

    pipecat_connection = SmallWebRTCConnection(ice_servers)
    await pipecat_connection.initialize(sdp=call.session.sdp, type=call.session.sdp_type)
    sdp_answer = pipecat_connection.get_answer().get("sdp")
    sdp_answer = filter_sdp_for_whatsapp(sdp_answer)
    background_tasks.add_task(run_bot, pipecat_connection)

    logger.info(f"SDP answer: {sdp_answer}")

    pre_accept_resp = await whatsapp_api.answer_call_to_whatsapp(
        call.id, "pre_accept", sdp_answer, call.from_
    )
    if not pre_accept_resp.get("success", False):
        logger.error(f"Failed to pre-accept call: {pre_accept_resp}")
        return {"status": "failed"}
    logger.info("Pre-accept response:", pre_accept_resp)

    accept_resp = await whatsapp_api.answer_call_to_whatsapp(
        call.id, "accept", sdp_answer, call.from_
    )
    if not accept_resp.get("success", False):
        logger.error(f"Failed to accept call: {accept_resp}")
        return {"status": "failed"}
    logger.info("Accept response:", accept_resp)

    # Storing the connection so we can disconnect later
    ongoing_calls_map[call.id] = pipecat_connection

    return {"status": "success", "message": "Call pre-accepted and accepted"}


async def handle_terminate_event(call: WhatsAppTerminateCall):
    """Handle a TERMINATE event: clean up resources and log call completion."""
    logger.info(f"Call terminated from {call.from_}, call_id: {call.id}")
    logger.info(f"Call status: {call.status}")
    if call.duration:
        logger.info(f"Call duration: {call.duration} seconds")

    if call.id in ongoing_calls_map:
        pipecat_connection = ongoing_calls_map[call.id]
        logger.info(f"Finishing peer connection: {call.id}")
        await pipecat_connection.disconnect()
        ongoing_calls_map.pop(call.id, None)

    return {"status": "success", "message": "Call termination handled"}


# ----------------------------
# Webhook Endpoint
# ----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global whatsapp_api
    # Create the session and initialize WhatsApp API
    async with aiohttp.ClientSession() as session:
        whatsapp_api = WhatsAppApi(
            whatsapp_token=WHATSAPP_TOKEN, phone_number_id=PHONE_NUMBER_ID, session=session
        )
        yield  # Run app
    # Clean up
    peers_to_disconnect = [pc.disconnect() for pc in ongoing_calls_map.values()]
    await asyncio.gather(*peers_to_disconnect)
    ongoing_calls_map.clear()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")

    if mode == "subscribe" and verify_token == WHATSAPP_WEBHOOK_VERIFICATION_TOKEN:
        return int(challenge)  # must return the same received challenge
    else:
        raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/")
async def whatsapp_call_webhook(body: WhatsAppWebhookRequest, background_tasks: BackgroundTasks):
    if body.object != "whatsapp_business_account":
        raise HTTPException(status_code=400, detail="Invalid object type")

    logger.info(f"Webhook received: {body}")

    for entry in body.entry:
        for change in entry.changes:
            # Handle connect events
            if isinstance(change.value, WhatsAppConnectCallValue):
                for call in change.value.calls:
                    if call.event == "connect":
                        return await handle_connect_event(call, background_tasks)

            # Handle terminate events
            elif isinstance(change.value, WhatsAppTerminateCallValue):
                for call in change.value.calls:
                    if call.event == "terminate":
                        return await handle_terminate_event(call)

    raise HTTPException(status_code=400, detail="No supported event found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC demo")
    parser.add_argument(
        "--host", default="localhost", help="Host for HTTP server (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=7860, help="Port for HTTP server (default: 7860)"
    )
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    logger.remove(0)
    if args.verbose:
        logger.add(sys.stderr, level="TRACE")
    else:
        logger.add(sys.stderr, level="DEBUG")

    uvicorn.run(app, host=args.host, port=args.port)
