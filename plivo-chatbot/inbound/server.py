#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""An example server for Plivo to start WebSocket streaming to Pipecat Cloud."""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from starlette.responses import Response

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Plivo XML Server", description="Serves XML for Plivo WebSocket streaming")


def get_websocket_url(host: str):
    """Construct WebSocket URL based on environment variables."""
    env = os.getenv("ENV", "local").lower()

    if env == "production":
        # Use Pipecat Cloud URL with agent and org from environment variables
        agent_name = os.getenv("AGENT_NAME")
        org_name = os.getenv("ORGANIZATION_NAME")

        if not agent_name or not org_name:
            raise ValueError(
                "AGENT_NAME and ORGANIZATION_NAME must be set in environment variables for production"
            )

        # Build WebSocket URL with serviceHost parameter
        service_host = f"{agent_name}.{org_name}"
        return f"wss://api.pipecat.daily.co/ws/plivo?serviceHost={service_host}"
    else:
        # Use request host for local development
        return f"wss://{host}/ws"


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
    # Log call details (optional - useful for debugging)
    if CallUUID:
        print(f"Plivo call: {From} → {To}, UUID: {CallUUID}")

    # Validate environment configuration
    env = os.getenv("ENV", "local").lower()
    if env == "production":
        if not os.getenv("AGENT_NAME") or not os.getenv("ORGANIZATION_NAME"):
            raise HTTPException(
                status_code=500,
                detail="AGENT_NAME and ORGANIZATION_NAME must be set for production deployment",
            )

    # Get request host and dynamic WebSocket URL based on environment
    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Unable to determine server host")

    websocket_url = get_websocket_url(host)

    # Build extraHeaders for Plivo (comma-separated key=value pairs)
    extra_headers = []
    if From:
        extra_headers.append(f"from={From}")
    if To:
        extra_headers.append(f"to={To}")

    extra_headers_str = ",".join(extra_headers) if extra_headers else ""

    # Build XML with extraHeaders if we have call information
    if extra_headers_str:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000" extraHeaders="{extra_headers_str}">
    {websocket_url}
  </Stream>
</Response>"""
    else:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">
    {websocket_url}
  </Stream>
</Response>"""
    return Response(content=xml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connections for inbound calls."""
    await websocket.accept()
    print("WebSocket connection accepted for inbound call")

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


if __name__ == "__main__":
    # Run the server on port 7860
    # Use with ngrok: ngrok http 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)
