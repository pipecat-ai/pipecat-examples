#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

# Load environment variables from .env file
load_dotenv()

# In-memory store for body data by call SID
call_body_data = {}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_websocket_url(host: str) -> str:
    """Get the appropriate WebSocket URL based on environment."""
    env = os.getenv("ENV", "local").lower()

    if env == "production":
        return "wss://api.pipecat.daily.co/ws/twilio"
    else:
        return f"wss://{host}/ws"


def generate_twiml(host: str, body_data: dict = None) -> str:
    """Generate TwiML response with WebSocket streaming using Twilio SDK."""
    websocket_url = get_websocket_url(host)

    # Create TwiML response
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=websocket_url)

    # Add Pipecat Cloud service host for production
    env = os.getenv("ENV", "local").lower()
    if env == "production":
        agent_name = os.getenv("AGENT_NAME")
        org_name = os.getenv("ORGANIZATION_NAME")
        service_host = f"{agent_name}.{org_name}"
        stream.parameter(name="_pipecatCloudServiceHost", value=service_host)

    # Add body parameter (if provided)
    if body_data:
        # Pass each key-value pair as separate parameters instead of JSON string
        for key, value in body_data.items():
            stream.parameter(name=key, value=value)

    connect.append(stream)
    response.append(connect)
    response.pause(length=20)

    return str(response)


@app.post("/")
async def start_call(request: Request):
    """Handle Twilio webhook and return TwiML with WebSocket streaming."""
    print("POST TwiML")

    # Parse form data from Twilio webhook
    form_data = await request.form()

    # Extract call information
    call_sid = form_data.get("CallSid", "")
    from_number = form_data.get("From", "")
    to_number = form_data.get("To", "")

    # Extract body data from query parameters and add phone numbers
    body_data = {}
    for key, value in request.query_params.items():
        body_data[key] = value

    # Always include phone numbers in body data
    body_data["from"] = from_number
    body_data["to"] = to_number

    # Log call details
    if call_sid:
        print(f"Twilio inbound call SID: {call_sid}")
        if body_data:
            print(f"Body data: {body_data}")

    # Validate environment configuration for production
    env = os.getenv("ENV", "local").lower()
    if env == "production":
        if not os.getenv("AGENT_NAME") or not os.getenv("ORGANIZATION_NAME"):
            raise HTTPException(
                status_code=500,
                detail="AGENT_NAME and ORGANIZATION_NAME must be set for production deployment",
            )

    # Get request host and construct WebSocket URL
    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="Unable to determine server host")

    # Generate TwiML response (body_data always contains phone numbers)
    twiml_content = generate_twiml(host, body_data)

    return HTMLResponse(content=twiml_content, media_type="application/xml")


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

        # Only pass testing argument for local development
        env = os.getenv("ENV", "local").lower()
        if env == "local":
            await bot(runner_args, app.state.testing)
        else:
            await bot(runner_args)

    except Exception as e:
        print(f"Error in WebSocket endpoint: {e}")
        await websocket.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipecat Twilio Chatbot Server")
    parser.add_argument(
        "-t", "--test", action="store_true", default=False, help="set the server in testing mode"
    )
    args, _ = parser.parse_known_args()

    app.state.testing = args.test

    uvicorn.run(app, host="0.0.0.0", port=7860)
