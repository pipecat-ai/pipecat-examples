#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import json

import uvicorn
from bot import run_bot
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def health_check():
    """Health check endpoint - Exotel doesn't use XML webhooks"""
    return {
        "status": "Exotel bot ready",
        "websocket_url": "wss://your-ngrok-url.ngrok.io/ws",
        "note": "Configure this WebSocket URL in your Exotel App Bazaar Voicebot Applet",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection accepted")

    start_data = websocket.iter_text()

    # Read first message (usually "connected")
    first_message = await start_data.__anext__()
    print(f"First message: {first_message}", flush=True)

    # Read second message (usually "start" with call data)
    second_message = await start_data.__anext__()
    print(f"Second message: {second_message}", flush=True)

    try:
        call_data = json.loads(second_message)
        print(f"Parsed call data: {call_data}", flush=True)

        # Extract Exotel-specific data
        if call_data.get("event") == "start":
            start_data = call_data.get("start", {})
            stream_sid = start_data.get("stream_sid")
            call_sid = start_data.get("call_sid")
            custom_parameters = start_data.get("custom_parameters", {})

            print(f"Stream ID: {stream_sid}")
            print(f"Call SID: {call_sid}")
            print(f"Custom Parameters: {custom_parameters}")

            # Exotel uses 8kHz PCM format
            await run_bot(websocket, stream_sid, call_sid)
        else:
            print(f"Unexpected message format: {call_data}")

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
    except Exception as e:
        print(f"Error handling WebSocket: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
