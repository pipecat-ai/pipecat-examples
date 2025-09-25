#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""server.py

Webhook server to handle outbound call requests, initiate calls via Plivo API,
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


async def make_plivo_call(
    session: aiohttp.ClientSession, to_number: str, from_number: str, answer_url: str
):
    """Make an outbound call using Plivo's REST API."""
    auth_id = os.getenv("PLIVO_AUTH_ID")
    auth_token = os.getenv("PLIVO_AUTH_TOKEN")

    if not auth_id:
        raise ValueError("Missing Plivo Auth ID (PLIVO_AUTH_ID)")

    if not auth_token:
        raise ValueError("Missing Plivo Auth Token (PLIVO_AUTH_TOKEN)")

    headers = {
        "Content-Type": "application/json",
    }

    data = {
        "to": to_number,
        "from": from_number,
        "answer_url": answer_url,
        "answer_method": "GET",
    }

    url = f"https://api.plivo.com/v1/Account/{auth_id}/Call/"

    # Use HTTP Basic Auth
    auth = aiohttp.BasicAuth(auth_id, auth_token)

    async with session.post(url, headers=headers, json=data, auth=auth) as response:
        if response.status != 201:
            error_text = await response.text()
            raise Exception(f"Plivo API error ({response.status}): {error_text}")

        result = await response.json()
        return result


def get_websocket_url(host: str):
    """Construct WebSocket URL based on environment variables."""
    env = os.getenv("ENV", "local").lower()

    if env == "production":
        return "wss://api.pipecat.daily.co/ws/plivo"
    else:
        return f"wss://{host}/ws"


# ----------------- API ----------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session for Plivo API calls
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
    """Handle outbound call request and initiate call via Plivo."""
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

        # Extract body data if provided
        body_data = data.get("body", {})
        print(f"Processing outbound call to {phone_number}")

        # Get server URL for answer URL
        host = request.headers.get("host")
        if not host:
            raise HTTPException(status_code=400, detail="Unable to determine server host")

        # Use https for production, http for localhost
        protocol = (
            "https"
            if not host.startswith("localhost") and not host.startswith("127.0.0.1")
            else "http"
        )

        # Add body data as query parameters to answer URL
        answer_url = f"{protocol}://{host}/answer"
        if body_data:
            body_json = json.dumps(body_data)
            body_encoded = urllib.parse.quote(body_json)
            answer_url = f"{answer_url}?body_data={body_encoded}"

        # Initiate outbound call via Plivo
        try:
            call_result = await make_plivo_call(
                session=request.app.state.session,
                to_number=phone_number,
                from_number=os.getenv("PLIVO_PHONE_NUMBER"),
                answer_url=answer_url,
            )

            # Extract call UUID from Plivo response
            call_uuid = (
                call_result.get("request_uuid") or call_result.get("message_uuid") or "unknown"
            )

        except Exception as e:
            print(f"Error initiating Plivo call: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

    return JSONResponse(
        {
            "call_uuid": call_uuid,
            "status": "call_initiated",
            "phone_number": phone_number,
        }
    )


@app.get("/answer")
async def get_answer_xml(
    request: Request,
    CallUUID: str = Query(None, description="Plivo call UUID"),
    body_data: str = Query(None, description="JSON encoded body data"),
) -> HTMLResponse:
    """Return XML instructions for connecting call to WebSocket."""
    print("Serving answer XML for outbound call")

    # Parse body data from query parameter
    parsed_body_data = {}
    if body_data:
        try:
            parsed_body_data = json.loads(body_data)
        except json.JSONDecodeError:
            print(f"Failed to parse body data: {body_data}")

    # Log call details
    if CallUUID:
        print(f"Plivo outbound call UUID: {CallUUID}")
        if parsed_body_data:
            print(f"Body data: {parsed_body_data}")

    try:
        # Get the server host to construct WebSocket URL
        host = request.headers.get("host")
        if not host:
            raise HTTPException(status_code=400, detail="Unable to determine server host")

        # Get base WebSocket URL
        base_ws_url = get_websocket_url(host)

        # Add query parameters to WebSocket URL
        query_params = []

        # Add serviceHost for production
        env = os.getenv("ENV", "local").lower()
        if env == "production":
            agent_name = os.getenv("AGENT_NAME")
            org_name = os.getenv("ORGANIZATION_NAME")
            service_host = f"{agent_name}.{org_name}"
            query_params.append(f"serviceHost={service_host}")

        # Add body data if available
        if parsed_body_data:
            body_json = json.dumps(parsed_body_data)
            body_encoded = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")
            query_params.append(f"body={body_encoded}")

        # Construct final WebSocket URL
        if query_params:
            ws_url = f"{base_ws_url}?{'&amp;'.join(query_params)}"
        else:
            ws_url = base_ws_url

        # Generate XML response for Plivo
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">
        {ws_url}
    </Stream>
</Response>"""

        return HTMLResponse(content=xml_content, media_type="application/xml")

    except Exception as e:
        print(f"Error generating answer XML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate XML: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connection from Plivo Media Streams."""
    await websocket.accept()
    print("WebSocket connection accepted for outbound call")

    print(f"Received query params - body: {body}, serviceHost: {serviceHost}")

    # Decode body parameter if provided
    body_data = {}
    if body:
        try:
            # Base64 decode the JSON (it was base64-encoded in the answer endpoint)
            decoded_json = base64.b64decode(body).decode("utf-8")
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

        # Create runner arguments and run the bot
        runner_args = WebSocketRunnerArguments(websocket=websocket)
        runner_args.handle_sigint = False

        # TODO: When WebSocketRunnerArguments supports body, add it here:
        # runner_args = WebSocketRunnerArguments(websocket=websocket, body=body_data)

        await bot(runner_args)

    except Exception as e:
        print(f"Error in WebSocket endpoint: {e}")
        await websocket.close()


# ----------------- Main ----------------- #


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
