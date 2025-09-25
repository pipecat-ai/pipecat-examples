#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""An example server for Plivo to start WebSocket streaming to Pipecat Cloud."""

import base64
import json
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from starlette.responses import Response

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Plivo XML Server", description="Serves XML for Plivo WebSocket streaming")


def get_websocket_url(host: str, body_data: dict = None):
    """Construct WebSocket URL based on environment variables with query parameters."""
    env = os.getenv("ENV", "local").lower()

    # Build query parameters
    query_params = []

    if env == "production":
        agent_name = os.getenv("AGENT_NAME")
        org_name = os.getenv("ORGANIZATION_NAME")

        if not agent_name or not org_name:
            raise ValueError(
                "AGENT_NAME and ORGANIZATION_NAME must be set in environment variables for production"
            )

        service_host = f"{agent_name}.{org_name}"
        query_params.append(f"serviceHost={service_host}")
        base_url = "wss://api.pipecat.daily.co/ws/plivo"
    else:
        base_url = f"wss://{host}/ws"

    # Add body data as query parameter
    if body_data:
        body_json = json.dumps(body_data)
        body_encoded = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")
        query_params.append(f"body={body_encoded}")

    # Construct final URL
    if query_params:
        return f"{base_url}?{'&amp;'.join(query_params)}"
    else:
        return base_url


@app.get("/")
async def start_call(
    request: Request,
    # Optional Plivo parameters that are automatically passed by Plivo
    CallUUID: str = Query(None, description="Plivo call UUID"),
    From: str = Query(None, description="Caller's phone number"),
    To: str = Query(None, description="Called phone number"),
):
    """
    Returns XML for Plivo to start WebSocket streaming with call information

    Agent and organization names are configured via environment variables:
    - AGENT_NAME: Your deployed agent name
    - ORGANIZATION_NAME: Your Pipecat Cloud organization

    For local development, set ENV=local in your .env file.
    For production, set ENV=production with AGENT_NAME and ORGANIZATION_NAME.

    Optional parameters (automatically passed by Plivo):
    - CallUUID, From, To

    Example webhook URL: https://your-domain.com/
    """
    print("GET Plivo XML")

    # Create body data with phone numbers only
    body_data = {}

    # Always include phone numbers if available
    if From:
        body_data["from"] = From
    if To:
        body_data["to"] = To

    # Log call details
    if CallUUID:
        print(f"Plivo inbound call: {From} → {To}, UUID: {CallUUID}")
        if body_data:
            print(f"Body data: {body_data}")

    # Validate environment configuration
    env = os.getenv("ENV", "local").lower()
    if env == "production":
        if not os.getenv("AGENT_NAME") or not os.getenv("ORGANIZATION_NAME"):
            raise HTTPException(
                status_code=500,
                detail="AGENT_NAME and ORGANIZATION_NAME must be set for production deployment",
            )

    # Get request host and construct WebSocket URL with body data
    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Unable to determine server host")

    websocket_url = get_websocket_url(host, body_data if body_data else None)

    # Build XML without extraHeaders (using query parameters instead)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">
    {websocket_url}
  </Stream>
</Response>"""
    print(f"Generated XML: {xml}")
    return Response(content=xml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connections for inbound calls."""
    await websocket.accept()
    print("WebSocket connection accepted for inbound call")

    print(f"Received query params - body: {body}, serviceHost: {serviceHost}")

    # Decode body parameter if provided
    body_data = {}
    if body:
        try:
            # Base64 decode the JSON (it was base64-encoded in the webhook handler)
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


if __name__ == "__main__":
    # Run the server on port 7860
    # Use with ngrok: ngrok http 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)
