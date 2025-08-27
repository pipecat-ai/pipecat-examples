#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import asyncio
import signal
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

# Global flag to handle shutdown
shutdown_event = asyncio.Event()


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

    logger.info(f"SDP answer: {sdp_answer}")

    pre_accept_resp = await whatsapp_api.answer_call_to_whatsapp(
        call.id, "pre_accept", sdp_answer, call.from_
    )
    if not pre_accept_resp.get("success", False):
        logger.error(f"Failed to pre-accept call: {pre_accept_resp}")
        await pipecat_connection.disconnect()
        return {"status": "failed"}

    logger.info("Pre-accept response:", pre_accept_resp)

    accept_resp = await whatsapp_api.answer_call_to_whatsapp(
        call.id, "accept", sdp_answer, call.from_
    )
    if not accept_resp.get("success", False):
        logger.error(f"Failed to accept call: {accept_resp}")
        await pipecat_connection.disconnect()
        return {"status": "failed"}

    logger.info("Accept response:", accept_resp)

    # Storing the connection so we can disconnect later
    ongoing_calls_map[call.id] = pipecat_connection

    @pipecat_connection.event_handler("closed")
    async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
        logger.info(f"Peer has disconnected: {webrtc_connection.pc_id}")

    background_tasks.add_task(run_bot, pipecat_connection)
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


async def terminate_all_calls():
    """Terminate all ongoing WhatsApp calls."""
    logger.info("Will terminate all ongoing WhatsApp calls")

    if not ongoing_calls_map:
        logger.info("No ongoing calls to terminate")
        return

    logger.info(f"Terminating {len(ongoing_calls_map)} ongoing calls")

    # Terminate each call via WhatsApp API
    termination_tasks = []
    for call_id, pipecat_connection in ongoing_calls_map.items():
        logger.info(f"Terminating call {call_id}")
        # Call WhatsApp API to terminate the call
        if whatsapp_api:
            termination_tasks.append(whatsapp_api.terminate_call_to_whatsapp(call_id))
        # Disconnect the pipecat connection
        termination_tasks.append(pipecat_connection.disconnect())

    # Execute all terminations concurrently
    await asyncio.gather(*termination_tasks, return_exceptions=True)

    # Clear the ongoing calls map
    ongoing_calls_map.clear()
    logger.info("All calls terminated successfully")


def signal_handler():
    """Handle SIGINT and SIGTERM signals"""
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_event.set()


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
        await terminate_all_calls()


app = FastAPI(lifespan=lifespan)


# ----------------------------
# Webhook Endpoint
# ----------------------------
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


async def run_server_with_signal_handling(host: str, port: int):
    """Run the server with proper signal handling"""
    # Set up signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    # Create server config
    config = uvicorn.Config(app, host=host, port=port, log_config=None)
    server = uvicorn.Server(config)
    
    # Start server in background
    server_task = asyncio.create_task(server.serve())

    logger.info(f"Server started on {host}:{port}...")
    # Wait for shutdown signal
    await shutdown_event.wait()
    
    # Initiate graceful shutdown
    logger.info("Shutting down server...")
    await terminate_all_calls()
    
    # Wait for server to finish
    await server_task


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

    # Use asyncio.run with the new signal handling function
    asyncio.run(run_server_with_signal_handling(args.host, args.port))