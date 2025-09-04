#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""WhatsApp WebRTC Bot Server

A FastAPI server that handles WhatsApp webhook events and manages WebRTC connections
for real-time communication with WhatsApp users. The server integrates with WhatsApp's
Business API to receive incoming calls and messages, then establishes WebRTC connections
to enable audio/video communication through a bot.

Key features:
- WhatsApp webhook verification and message handling
- WebRTC connection management with ICE server support
- Graceful shutdown handling with signal management
- Background task processing for bot instances
- Connection cleanup and resource management

Environment Variables Required:
- WHATSAPP_TOKEN: WhatsApp Business API access token
- WHATSAPP_WEBHOOK_VERIFICATION_TOKEN: Token for webhook verification
- WHATSAPP_PHONE_NUMBER_ID: WhatsApp Business phone number ID

Usage:
    python server.py --host 0.0.0.0 --port 8080 --verbose
"""

import argparse
import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from loguru import logger
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.whatsapp.api import WhatsAppWebhookRequest
from pipecat.transports.whatsapp.client import WhatsAppClient

from bot import run_bot

# Load environment variables first
load_dotenv(override=True)
import os

# Global configuration - loaded from environment variables
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_WEBHOOK_VERIFICATION_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFICATION_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

# Validate required environment variables
if not all([WHATSAPP_TOKEN, WHATSAPP_WEBHOOK_VERIFICATION_TOKEN, WHATSAPP_PHONE_NUMBER_ID]):
    missing_vars = [
        var
        for var, val in [
            ("WHATSAPP_TOKEN", WHATSAPP_TOKEN),
            ("WHATSAPP_WEBHOOK_VERIFICATION_TOKEN", WHATSAPP_WEBHOOK_VERIFICATION_TOKEN),
            ("WHATSAPP_PHONE_NUMBER_ID", WHATSAPP_PHONE_NUMBER_ID),
        ]
        if not val
    ]
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Global state
whatsapp_client: Optional[WhatsAppClient] = None
shutdown_event = asyncio.Event()


def signal_handler() -> None:
    """Handle shutdown signals (SIGINT, SIGTERM) gracefully.

    Sets the shutdown event to initiate graceful server shutdown.
    This allows the server to complete ongoing requests and cleanup resources.
    """
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_event.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan and resources.

    Sets up the WhatsApp client with an HTTP session on startup
    and ensures proper cleanup on shutdown.

    Args:
        app: The FastAPI application instance

    Yields:
        None: Control back to the application during runtime
    """
    global whatsapp_client

    # Initialize WhatsApp client with persistent HTTP session
    async with aiohttp.ClientSession() as session:
        whatsapp_client = WhatsAppClient(
            whatsapp_token=WHATSAPP_TOKEN, phone_number_id=WHATSAPP_PHONE_NUMBER_ID, session=session
        )
        logger.info("WhatsApp client initialized successfully")

        try:
            yield  # Run the application
        finally:
            # Cleanup all active calls on shutdown
            logger.info("Cleaning up WhatsApp client resources...")
            if whatsapp_client:
                await whatsapp_client.terminate_all_calls()
            logger.info("Cleanup completed")


# Initialize FastAPI app with lifespan management
app = FastAPI(
    title="WhatsApp WebRTC Bot Server",
    description="Handles WhatsApp webhooks and manages WebRTC connections for bot communication",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get(
    "/",
    summary="Verify WhatsApp webhook",
    description="Handles WhatsApp webhook verification requests from Meta",
)
async def verify_webhook(request: Request):
    """Verify WhatsApp webhook endpoint.

    This endpoint is called by Meta's WhatsApp Business API to verify
    the webhook URL during setup. It validates the verification token
    and returns the challenge parameter if successful.

    Args:
        request: FastAPI request object containing query parameters

    Returns:
        dict: Verification response or challenge string

    Raises:
        HTTPException: 403 if verification token is invalid
    """
    params = dict(request.query_params)
    logger.debug(f"Webhook verification request received with params: {list(params.keys())}")

    try:
        result = await whatsapp_client.handle_verify_webhook_request(
            params=params, expected_verification_token=WHATSAPP_WEBHOOK_VERIFICATION_TOKEN
        )
        logger.info("Webhook verification successful")
        return result
    except ValueError as e:
        logger.warning(f"Webhook verification failed: {e}")
        raise HTTPException(status_code=403, detail="Verification failed")


@app.post(
    "/",
    summary="Handle WhatsApp webhook events",
    description="Processes incoming WhatsApp messages and call events",
)
async def whatsapp_webhook(body: WhatsAppWebhookRequest, background_tasks: BackgroundTasks):
    """Handle incoming WhatsApp webhook events.

    Processes WhatsApp Business API webhook requests including:
    - Incoming messages
    - Call requests and status updates
    - User interactions

    For call events, establishes WebRTC connections and spawns bot instances
    in the background to handle real-time communication.

    Args:
        body: Parsed WhatsApp webhook request body
        background_tasks: FastAPI background tasks manager

    Returns:
        dict: Success response with processing status

    Raises:
        HTTPException:
            400 for invalid request format or object type
            500 for internal processing errors
    """
    # Validate webhook object type
    if body.object != "whatsapp_business_account":
        logger.warning(f"Invalid webhook object type: {body.object}")
        raise HTTPException(status_code=400, detail="Invalid object type")

    logger.info(f"Processing WhatsApp webhook: {body.dict()}")

    async def connection_callback(connection: SmallWebRTCConnection):
        """Handle new WebRTC connections from WhatsApp calls.

        Called when a WebRTC connection is established for a WhatsApp call.
        Spawns a bot instance to handle the conversation.

        Args:
            connection: The established WebRTC connection
        """
        try:
            logger.info(f"Starting bot for WebRTC connection: {connection.pc_id}")
            background_tasks.add_task(run_bot, connection)
            logger.debug(f"Bot task queued successfully for connection: {connection.pc_id}")
        except Exception as e:
            logger.error(f"Failed to start bot for connection {connection.pc_id}: {e}")
            # Attempt to cleanup the connection on error
            try:
                await connection.disconnect()
                logger.debug(f"Connection {connection.pc_id} disconnected after error")
            except Exception as disconnect_error:
                logger.error(f"Failed to disconnect connection after error: {disconnect_error}")

    try:
        # Process the webhook request
        result = await whatsapp_client.handle_webhook_request(body, connection_callback)
        logger.debug(f"Webhook processed successfully: {result}")
        return {"status": "success", "message": "Webhook processed successfully"}

    except ValueError as ve:
        logger.warning(f"Invalid webhook request format: {ve}")
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(ve)}")
    except Exception as e:
        logger.error(f"Internal error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error processing webhook")


async def run_server_with_signal_handling(host: str, port: int) -> None:
    """Run the FastAPI server with proper signal handling.

    Sets up signal handlers for graceful shutdown and manages the server lifecycle.
    Handles SIGINT (Ctrl+C) and SIGTERM signals to ensure proper cleanup.

    Args:
        host: The host address to bind the server to
        port: The port number to listen on
    """
    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Configure and create the server
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,
    )
    server = uvicorn.Server(config)

    # Start server in background task
    server_task = asyncio.create_task(server.serve())
    logger.info(f"WhatsApp WebRTC server started on {host}:{port}")
    logger.info("Press Ctrl+C to stop the server")

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Initiate graceful shutdown
    logger.info("Shutting down server.")

    # Cleanup WhatsApp client resources
    if whatsapp_client:
        await whatsapp_client.terminate_all_calls()

    # Stop the server
    server.should_exit = True
    await server_task
    logger.info("Server shutdown completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WhatsApp WebRTC Bot Server - Handles WhatsApp webhooks and WebRTC connections"
    )
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

    # Validate configuration
    logger.info("Starting WhatsApp WebRTC Bot Server...")
    logger.debug(f"Configuration: host={args.host}, port={args.port}, verbose={args.verbose}")

    # Run the server
    try:
        asyncio.run(run_server_with_signal_handling(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
