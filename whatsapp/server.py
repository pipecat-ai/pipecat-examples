#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import asyncio
import signal
import sys
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from bot import run_bot
from dotenv import load_dotenv
from fastapi import BackgroundTasks
from loguru import logger
from pipecat.transports.network.webrtc_connection import IceServer, SmallWebRTCConnection
from pipecat.utils.whatsapp.api import (
    WhatsAppWebhookRequest,
)
from pipecat.utils.whatsapp.client import WhatsAppClient

# Load environment variables
load_dotenv(override=True)
import os
from typing import Dict

from fastapi import FastAPI, HTTPException, Request

# WhatsApp - will be initialized in lifespan
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_WEBHOOK_VERIFICATION_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFICATION_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
whatsapp_client: WhatsAppClient = None

# Global flag to handle shutdown
shutdown_event = asyncio.Event()


def signal_handler():
    """Handle SIGINT and SIGTERM signals"""
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_event.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global whatsapp_client
    # Create the session and initialize WhatsApp API
    async with aiohttp.ClientSession() as session:
        whatsapp_client = WhatsAppClient(
            whatsapp_token=WHATSAPP_TOKEN, phone_number_id=PHONE_NUMBER_ID, session=session
        )
        yield  # Run app
        # Clean up
        await whatsapp_client.terminate_all_calls()


app = FastAPI(lifespan=lifespan)


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
        return int(challenge)  # must return the same received challenge
    else:
        raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/")
async def whatsapp_call_webhook(body: WhatsAppWebhookRequest, background_tasks: BackgroundTasks):
    if body.object != "whatsapp_business_account":
        raise HTTPException(status_code=400, detail="Invalid object type")

    logger.info(f"Webhook received: {body}")
    # TODO need to handle in case of error
    result = await whatsapp_client.handle_webhook_request(body)
    if isinstance(result, SmallWebRTCConnection):
        background_tasks.add_task(run_bot, result)


async def run_server_with_signal_handling(host: str, port: int):
    """Run the server with proper signal handling"""
    # Set up signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Create server config
    config = uvicorn.Config(app, host=host, port=port, log_config=None)
    server = uvicorn.Server(config)

    # Start server in background
    server_task = asyncio.create_task(server.serve())

    logger.info(f"Server started on {host}:{port}...")
    # Wait for shutdown signal
    await shutdown_event.wait()

    # Initiate graceful shutdown
    logger.info("Shutting down server...")
    await whatsapp_client.terminate_all_calls()

    # Wait for server to finish
    await server_task


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

    # Use asyncio.run with the new signal handling function
    asyncio.run(run_server_with_signal_handling(args.host, args.port))
