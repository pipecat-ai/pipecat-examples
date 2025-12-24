#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""An example server for Vonage to start WebSocket streaming to Pipecat Cloud."""

import base64
import json
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from starlette.responses import JSONResponse

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Vonage NCCO Server", description="Serves NCCO for Vonage WebSocket streaming")


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
        base_url = "wss://api.pipecat.daily.co/ws/vonage"
    else:
        base_url = f"wss://{host}/ws"

    # Add body data as query parameter
    if body_data:
        body_json = json.dumps(body_data)
        body_encoded = base64.b64encode(body_json.encode("utf-8")).decode("utf-8")
        query_params.append(f"body={body_encoded}")

    # Construct final URL
    if query_params:
        return f"{base_url}?{'&'.join(query_params)}"
    else:
        return base_url


@app.post("/answer")
async def answer_call(request: Request):
    """
    Returns NCCO (JSON) for Vonage to start WebSocket streaming with call information

    Agent and organization names are configured via environment variables:
    - AGENT_NAME: Your deployed agent name
    - ORGANIZATION_NAME: Your Pipecat Cloud organization

    For local development, set ENV=local in your .env file.
    For production, set ENV=production with AGENT_NAME and ORGANIZATION_NAME.

    Vonage sends call parameters as form data:
    - conversation_uuid, uuid, from, to

    Example webhook URL: https://your-domain.com/answer
    """
    # Vonage sends JSON (not form data) for webhook requests
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        form_data = await request.json()
    else:
        form_data = await request.form()

    # Extract parameters from form data
    conversation_uuid = form_data.get("conversation_uuid")
    uuid = form_data.get("uuid")
    from_number = form_data.get("from")
    to = form_data.get("to")

    # Create body data
    body_data = {}
    if from_number:
        body_data["from"] = from_number
    if to:
        body_data["to"] = to
    if uuid:
        body_data["call_uuid"] = uuid
    if conversation_uuid:
        body_data["conversation_uuid"] = conversation_uuid

    # Log call details
    if uuid:
        print(f"Vonage inbound call: {from_number} → {to}, UUID: {uuid}")

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

    # Use 16kHz for better AI/speech recognition quality
    sample_rate = 16000

    # Build NCCO with headers for production or query params for local
    if env == "production":
        # For production (Pipecat Cloud), use headers
        ncco = [
            {
                "action": "connect",
                "endpoint": [
                    {
                        "type": "websocket",
                        "uri": websocket_url,
                        "content-type": f"audio/l16;rate={sample_rate}",
                        "headers": {
                            "_pipecatCloudServiceHost": f"{os.getenv('AGENT_NAME')}.{os.getenv('ORGANIZATION_NAME')}"
                        },
                    }
                ],
            }
        ]
    else:
        # For local development, use query parameters
        ncco = [
            {
                "action": "connect",
                "endpoint": [
                    {
                        "type": "websocket",
                        "uri": websocket_url,
                        "content-type": f"audio/l16;rate={sample_rate}",
                    }
                ],
            }
        ]

    print(f"Generated NCCO: {json.dumps(ncco, indent=2)}")
    return JSONResponse(content=ncco)


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    body: str = Query(None),
    serviceHost: str = Query(None),
):
    """Handle WebSocket connections for inbound calls."""
    await websocket.accept()
    print("WebSocket connection accepted for inbound call")

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

        # Store body_data in websocket state so parse_telephony_websocket can access it
        # Note: Vonage doesn't include phone numbers in WebSocket messages, only in the
        # initial webhook. We pass this data through websocket state to make it available
        # to the bot via parse_telephony_websocket().
        websocket.state.vonage_call_data = body_data

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
