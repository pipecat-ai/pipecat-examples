#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""server.py

Webhook server to handle outbound call requests, initiate calls via Telnyx API,
and handle subsequent WebSocket connections for Media Streams.
"""

import base64
import json
import os
import urllib.parse
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

load_dotenv(override=True)


# ----------------- HELPERS ----------------- #


async def make_telnyx_call(
    session: aiohttp.ClientSession, to_number: str, from_number: str, texml_url: str
):
    """Make an outbound call using Telnyx's TeXML API."""
    api_key = os.getenv("TELNYX_API_KEY")
    account_sid = os.getenv("TELNYX_ACCOUNT_SID")
    application_sid = os.getenv("TELNYX_APPLICATION_SID")  # This is your TeXML Application ID

    if not api_key:
        raise ValueError("Missing Telnyx API key (TELNYX_API_KEY)")

    if not account_sid:
        raise ValueError(
            "Missing Telnyx Account SID (TELNYX_ACCOUNT_SID) - required for TeXML calls"
        )

    if not application_sid:
        raise ValueError(
            "Missing Telnyx TeXML Application SID (TELNYX_APPLICATION_SID) - required for TeXML calls"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    data = {
        "ApplicationSid": application_sid,
        "To": to_number,
        "From": from_number,
        "Url": texml_url,
    }

    url = f"https://api.telnyx.com/v2/texml/Accounts/{account_sid}/Calls"

    async with session.post(url, headers=headers, json=data) as response:
        if response.status != 200:
            error_text = await response.text()
            raise Exception(f"Telnyx API error ({response.status}): {error_text}")

        result = await response.json()
        return result


def get_websocket_url(host: str):
    """Construct base WebSocket URL (without query parameters)."""
    env = os.getenv("ENV", "local").lower()

    if env == "production":
        print("If deployed in a region other than us-west (default), update websocket url!")

        ws_url = "wss://api.pipecat.daily.co/ws/telnyx"
        # uncomment appropriate region url:
        # ws_url = wss://us-east.api.pipecat.daily.co/ws/telnyx
        # ws_url = wss://eu-central.api.pipecat.daily.co/ws/telnyx
        # ws_url = wss://ap-south.api.pipecat.daily.co/ws/telnyx

        return ws_url
    else:
        return f"wss://{host}/ws"


# ----------------- API ----------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session for Telnyx API calls
    app.state.session = aiohttp.ClientSession()
    yield
    # Close session when shutting down
    await app.state.session.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/start")
async def initiate_outbound_call(request: Request) -> JSONResponse:
    """Handle outbound call request and initiate call via Telnyx."""
    print("Received outbound call request")

    try:
        data = await request.json()

        # Validate request data
        if not data.get("phone_number"):
            raise HTTPException(
                status_code=400, detail="Missing 'phone_number' in the request body"
            )

        # Extract the phone number to dial
        phone_number = str(data["phone_number"])
        print(f"Processing outbound call to {phone_number}")

        # Extract body data if provided (for custom data injection)
        body = data.get("body", {})

        # Get server URL for TeXML webhook
        host = request.headers.get("host")
        if not host:
            raise HTTPException(status_code=400, detail="Unable to determine server host")

        # Use https for production, http for localhost
        protocol = (
            "https"
            if not host.startswith("localhost") and not host.startswith("127.0.0.1")
            else "http"
        )

        # Add body as base64-encoded parameter to TeXML URL
        texml_url = f"{protocol}://{host}/answer"
        if body:
            # Encode body as base64 JSON
            body_json = json.dumps(body)
            body_b64 = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")

            # URL encode the base64 string to handle special characters like +, /, =
            encoded_body = urllib.parse.quote(body_b64, safe="")
            texml_url = f"{texml_url}?body={encoded_body}"
            print(f"TeXML URL with body param: {texml_url}")
            print(f"Encoded body length: {len(body_b64)}")

        # Initiate outbound call via Telnyx
        try:
            call_result = await make_telnyx_call(
                session=request.app.state.session,
                to_number=phone_number,
                from_number=os.getenv("TELNYX_PHONE_NUMBER"),
                texml_url=texml_url,
            )

            # Extract call ID from response
            if "data" in call_result:
                call_sid = call_result["data"].get("call_control_id") or call_result["data"].get(
                    "sid"
                )
            else:
                call_sid = call_result.get("sid") or call_result.get("call_control_id")

            if not call_sid:
                call_sid = "unknown"

        except Exception as e:
            print(f"Error initiating Telnyx call: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

    return JSONResponse(
        {
            "call_control_id": call_sid,
            "status": "call_initiated",
            "phone_number": phone_number,
        }
    )


@app.post("/answer")
async def get_answer_xml(request: Request) -> HTMLResponse:
    """Return TeXML instructions for connecting call to WebSocket."""
    print("Serving TeXML for outbound call")

    try:
        # Get the server host to construct WebSocket URL
        host = request.headers.get("host")
        if not host:
            raise HTTPException(status_code=400, detail="Unable to determine server host")

        # Get dynamic WebSocket URL based on environment
        ws_url = get_websocket_url(host)

        # Add query parameters to WebSocket URL
        query_parts = []

        # Add serviceHost for production environments
        env = os.getenv("ENV", "local").lower()
        if env == "production":
            agent_name = os.getenv("AGENT_NAME")
            org_name = os.getenv("ORGANIZATION_NAME")
            if agent_name and org_name:
                query_parts.append(f"serviceHost={agent_name}.{org_name}")

        # Add body parameter if present
        if request.query_params and "body" in request.query_params:
            body_param = request.query_params["body"]
            query_parts.append(f"body={body_param}")
            print(f"Added body param to WebSocket URL")

        # Construct WebSocket URL with proper &amp; encoding for multiple params
        if query_parts:
            query_string = "&amp;".join(query_parts)
            ws_url = f"{ws_url}?{query_string}"
            print(f"WebSocket URL with query params: {ws_url}")

        # Generate TeXML response
        texml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" bidirectionalMode="rtp"></Stream>
    </Connect>
    <Pause length="40"/>
</Response>'''

        return HTMLResponse(content=texml_content, media_type="application/xml")

    except Exception as e:
        print(f"Error generating TeXML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate TeXML: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connection from Telnyx Media Streams."""
    await websocket.accept()
    print("WebSocket connection accepted for outbound call")

    print(f"Received query params - body: {body}, serviceHost: {serviceHost}")

    # Decode body parameter if provided
    body_data = {}
    if body:
        try:
            # URL decode first, then base64 decode
            url_decoded = urllib.parse.unquote(body)
            decoded_json = base64.b64decode(url_decoded).decode("utf-8")
            body_data = json.loads(decoded_json)
            print(f"Decoded body data: {body_data}")
        except Exception as e:
            print(f"Error decoding body parameter: {e}")
    else:
        print("No body parameter received")

    try:
        # Import the bot function from the bot module
        from bot import bot
        from pipecat.runner.types import WebSocketRunnerArguments

        # Create runner arguments with body data
        runner_args = WebSocketRunnerArguments(websocket=websocket, body=body_data)

        await bot(runner_args)

    except Exception as e:
        print(f"Error in WebSocket endpoint: {e}")
        await websocket.close()


# ----------------- Main ----------------- #


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
