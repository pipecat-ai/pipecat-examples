#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import sys

import uvicorn
from bot import run_bot
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, HTTPException
from loguru import logger
from pipecat.transports.network.webrtc_connection import IceServer, SmallWebRTCConnection


# Load environment variables
load_dotenv(override=True)
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any
import httpx
import os

app = FastAPI()

# Environment variables
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_WEBHOOK_VERIFICATION_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFICATION_TOKEN")

PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
WHATSAPP_API_URL = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/calls"

ice_servers = [
    IceServer(
        urls="stun:stun.l.google.com:19302",
    )
]

# ----------------------------
# Pydantic Models for Webhook
# ----------------------------
class Session(BaseModel):
    sdp: str
    sdp_type: str


class Error(BaseModel):
    code: int
    message: str
    href: str
    error_data: Dict[str, Any]


class ConnectCall(BaseModel):
    id: str
    from_: str = Field(..., alias="from")
    to: str
    event: str  # "connect"
    timestamp: str
    direction: Optional[str]
    session: Session


class TerminateCall(BaseModel):
    id: str
    from_: str = Field(..., alias="from")
    to: str
    event: str  # "terminate"
    timestamp: str
    direction: Optional[str]
    biz_opaque_callback_data: Optional[str] = None
    status: Optional[str] = None  # "FAILED" or "COMPLETED"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[int] = None


class Profile(BaseModel):
    name: str


class Contact(BaseModel):
    profile: Profile
    wa_id: str


class Metadata(BaseModel):
    display_phone_number: str
    phone_number_id: str


class ConnectCallValue(BaseModel):
    messaging_product: str
    metadata: Metadata
    contacts: List[Contact]
    calls: List[ConnectCall]


class TerminateCallValue(BaseModel):
    messaging_product: str
    metadata: Metadata
    calls: List[TerminateCall]
    errors: Optional[List[Error]] = None


class Change(BaseModel):
    value: Union[ConnectCallValue, TerminateCallValue]
    field: str


class Entry(BaseModel):
    id: str
    changes: List[Change]


class WebhookRequest(BaseModel):
    object: str
    entry: List[Entry]


# ----------------------------
# Helper functions
# ----------------------------
async def answer_call_to_whatsapp(call_id: str, action:str, sdp:str, from_: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            WHATSAPP_API_URL,
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": from_,
                "action": action,
                "call_id": call_id,
                "session": {
                    "sdp": sdp,
                    "sdp_type": "answer"
                }
            },
        )
        return response

def filter_sdp_for_whatsapp(sdp: str) -> str:
    lines = sdp.splitlines()
    filtered = []
    for line in lines:
        if line.startswith("a=fingerprint:") and not line.startswith("a=fingerprint:sha-256"):
            continue  # drop sha-384 / sha-512
        filtered.append(line)
    return "\r\n".join(filtered) + "\r\n"

async def handle_connect_event(call: ConnectCall, background_tasks: BackgroundTasks):
    """Handle a CONNECT event: pre-accept and accept the call."""
    logger.info(f"Incoming call from {call.from_}, call_id: {call.id}")

    pipecat_connection = SmallWebRTCConnection(ice_servers)
    await pipecat_connection.initialize(sdp=call.session.sdp, type=call.session.sdp_type)
    sdp_answer = pipecat_connection.get_answer().get("sdp")
    sdp_answer = filter_sdp_for_whatsapp(sdp_answer)
    background_tasks.add_task(run_bot, pipecat_connection)

    logger.info(f"SDP answer: {sdp_answer}")

    pre_accept_resp = await answer_call_to_whatsapp(call.id, "pre_accept", sdp_answer, call.from_)
    if not pre_accept_resp.is_success:
        logger.error(f"Failed to pre-accept call: {pre_accept_resp.json()}")
        return {"status": "failed"}
    logger.info("Pre-accept response:", pre_accept_resp)
    accept_resp = await answer_call_to_whatsapp(call.id, "accept", sdp_answer, call.from_)
    if not accept_resp.is_success:
        logger.error(f"Failed to accept call: {accept_resp.json()}")
        return {"status": "failed"}
    logger.info("Accept response:", accept_resp)
    return {"status": "success", "message": "Call pre-accepted and accepted"}

async def handle_terminate_event(call: TerminateCall):
    """Handle a TERMINATE event: clean up resources and log call completion."""
    logger.info(f"Call terminated from {call.from_}, call_id: {call.id}")
    logger.info(f"Call status: {call.status}")
    if call.duration:
        logger.info(f"Call duration: {call.duration} seconds")
    
    # Here you can add any cleanup logic needed when a call terminates
    # For example, updating database records, sending notifications, etc.
    
    return {"status": "success", "message": "Call termination handled"}

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
        return int(challenge)  # must return challenge as integer
    else:
        raise HTTPException(status_code=403, detail="Verification failed")

@app.post("/")
async def whatsapp_call_webhook(body: WebhookRequest, background_tasks: BackgroundTasks):
    if body.object != "whatsapp_business_account":
        raise HTTPException(status_code=400, detail="Invalid object type")

    logger.info(f"Webhook received: {body}")

    for entry in body.entry:
        for change in entry.changes:
            # Handle connect events
            if isinstance(change.value, ConnectCallValue):
                for call in change.value.calls:
                    if call.event == "connect":
                        return await handle_connect_event(call, background_tasks)
            
            # Handle terminate events
            elif isinstance(change.value, TerminateCallValue):
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