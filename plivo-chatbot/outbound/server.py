#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""server.py

Webhook server to handle outbound call requests, initiate calls via Plivo API,
and handle subsequent WebSocket connections for Media Streams.
"""

import os
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
        agent_name = os.getenv("AGENT_NAME")
        org_name = os.getenv("ORGANIZATION_NAME")
        return f"wss://api.pipecat.daily.co/ws/plivo?serviceHost={agent_name}.{org_name}"
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

        # Extract custom data if provided
        custom_data = data.get("custom_data", {})
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

        # Add custom data as query parameters to answer URL
        answer_url = f"{protocol}://{host}/answer"
        if custom_data:
            import urllib.parse

            # Flatten the nested dict before URL encoding
            def flatten_for_url(data, prefix=""):
                """Flatten nested dict for URL parameters."""
                params = {}
                for key, value in data.items():
                    param_name = f"{prefix}_{key}" if prefix else key
                    if isinstance(value, dict):
                        params.update(flatten_for_url(value, param_name))
                    else:
                        params[param_name] = str(value)
                return params

            flattened_params = flatten_for_url(custom_data)
            query_params = urllib.parse.urlencode(flattened_params)
            answer_url = f"{answer_url}?{query_params}"

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
    From: str = Query(None, description="Caller's phone number"),
    To: str = Query(None, description="Called phone number"),
) -> HTMLResponse:
    """Return XML instructions for connecting call to WebSocket."""
    print("Serving answer XML for outbound call")

    # Log call details (optional - useful for debugging)
    if CallUUID:
        print(f"Plivo outbound call: {From} → {To}, UUID: {CallUUID}")

    try:
        # Get the server host to construct WebSocket URL
        host = request.headers.get("host")
        if not host:
            raise HTTPException(status_code=400, detail="Unable to determine server host")

        # Get dynamic WebSocket URL based on environment
        ws_url = get_websocket_url(host)

        # Build extraHeaders for Plivo (comma-separated key=value pairs)
        extra_headers = []

        # Always add from and to parameters
        if From:
            extra_headers.append(f"from={From}")
        if To:
            extra_headers.append(f"to={To}")

        # Add custom data from query parameters
        for key, value in request.query_params.items():
            if key not in ["CallUUID", "From", "To"]:  # Skip Plivo's built-in params
                extra_headers.append(f"{key}={value}")

        extra_headers_str = ",".join(extra_headers) if extra_headers else ""

        # Generate XML response for Plivo with extraHeaders if we have call information
        if extra_headers_str:
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000" extraHeaders="{extra_headers_str}">
        {ws_url}
    </Stream>
</Response>"""
        else:
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
async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connection from Plivo Media Streams."""
    await websocket.accept()
    print("WebSocket connection accepted for outbound call")

    try:
        # Import the bot function from the bot module
        from bot import bot
        from pipecat.runner.types import WebSocketRunnerArguments

        # Create runner arguments and run the bot
        runner_args = WebSocketRunnerArguments(websocket=websocket)
        runner_args.handle_sigint = False

        await bot(runner_args)

    except Exception as e:
        print(f"Error in WebSocket endpoint: {e}")
        await websocket.close()


# ----------------- Main ----------------- #


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
