#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""server.py

Webhook server to handle outbound call requests, initiate calls via Twilio API,
and handle subsequent WebSocket connections for Media Streams.
"""

import argparse
import base64
import os
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

load_dotenv(override=True)

# In-memory store for body data by call SID
call_body_data = {}

# ----------------- HELPERS ----------------- #


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
        import json

        stream.parameter(name="body", value=json.dumps(body_data))

    connect.append(stream)
    response.append(connect)
    response.pause(length=20)

    return str(response)


async def make_twilio_call(
    session: aiohttp.ClientSession, to_number: str, from_number: str, twiml_url: str
):
    """Make an outbound call using Twilio's REST API."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    if not account_sid or not auth_token:
        raise ValueError("Missing Twilio credentials")

    # Create basic auth header
    auth_string = f"{account_sid}:{auth_token}"
    auth_bytes = auth_string.encode("ascii")
    auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {"To": to_number, "From": from_number, "Url": twiml_url, "Method": "POST"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"

    async with session.post(url, headers=headers, data=data) as response:
        if response.status != 201:
            error_text = await response.text()
            raise Exception(f"Twilio API error ({response.status}): {error_text}")

        result = await response.json()
        return result


# ----------------- API ----------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create aiohttp session for Twilio API calls
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
    """Handle outbound call request and initiate call via Twilio."""
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

        # Extract body data if provided
        body_data = data.get("body", {})

        # Get server URL for TwiML webhook
        host = request.headers.get("host")
        if not host:
            raise HTTPException(status_code=400, detail="Unable to determine server host")

        # Use https for production, http for localhost
        protocol = (
            "https"
            if not host.startswith("localhost") and not host.startswith("127.0.0.1")
            else "http"
        )

        # Simple TwiML URL without query parameters
        twiml_url = f"{protocol}://{host}/twiml"

        # Initiate outbound call via Twilio
        try:
            call_result = await make_twilio_call(
                session=request.app.state.session,
                to_number=phone_number,
                from_number=os.getenv("TWILIO_PHONE_NUMBER"),
                twiml_url=twiml_url,
            )
            call_sid = call_result["sid"]

            # Store body data for this call
            if body_data:
                call_body_data[call_sid] = body_data

        except Exception as e:
            print(f"Error initiating Twilio call: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

    return JSONResponse(
        {"call_sid": call_sid, "status": "call_initiated", "phone_number": phone_number}
    )


@app.post("/twiml")
async def get_twiml(request: Request) -> HTMLResponse:
    """Return TwiML instructions for connecting call to WebSocket."""
    print("Serving TwiML for outbound call")

    # Parse form data from Twilio webhook
    form_data = await request.form()

    # Extract call information
    call_sid = form_data.get("CallSid", "")

    # Retrieve body data for this call
    body_data = call_body_data.get(call_sid, {})

    # Clean up stored data for this call
    if call_sid and body_data:
        # Clean up the stored data
        del call_body_data[call_sid]

    # Validate environment configuration for production
    env = os.getenv("ENV", "local").lower()
    if env == "production":
        if not os.getenv("AGENT_NAME") or not os.getenv("ORGANIZATION_NAME"):
            raise HTTPException(
                status_code=500,
                detail="AGENT_NAME and ORGANIZATION_NAME must be set for production deployment",
            )

    try:
        # Get the server host to construct WebSocket URL
        host = request.headers.get("host")
        if not host:
            raise HTTPException(status_code=400, detail="Unable to determine server host")

        # Generate TwiML with body data parameter
        twiml_content = generate_twiml(host, body_data)

        return HTMLResponse(content=twiml_content, media_type="application/xml")

    except Exception as e:
        print(f"Error generating TwiML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate TwiML: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connection from Twilio Media Streams."""
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
    parser = argparse.ArgumentParser(description="Pipecat Twilio Outbound Chatbot Server")
    parser.add_argument(
        "-t", "--test", action="store_true", default=False, help="set the server in testing mode"
    )
    args, _ = parser.parse_known_args()

    app.state.testing = args.test

    # Run the server
    port = int(os.getenv("PORT", "7860"))
    print(f"Starting Twilio outbound chatbot server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
