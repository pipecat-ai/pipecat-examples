#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, Dict
from urllib.parse import quote

import uvicorn
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles FastAPI startup and shutdown."""
    yield


# Initialize FastAPI app with lifespan manager
app = FastAPI(lifespan=lifespan)

# Configure CORS — set ALLOWED_ORIGINS env var to a comma-separated list of origins in production
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _RateLimiter:
    """Simple in-memory rate limiter for demonstration purposes."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if len(self._requests[key]) >= self.max_requests:
            return False
        self._requests[key].append(now)
        return True


_rate_limiter = _RateLimiter()


@app.post("/start")
async def start_bot(request: Request) -> Dict[Any, Any]:
    """
    Start endpoint that generates a signed WebSocket URL for connecting to the agent on AWS Bedrock AgentCore.

    Returns:
        Dict[Any, Any]: Contains the signed WebSocket URL for the client to connect
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    # Check if LOCAL_AGENT mode is enabled
    if os.getenv("LOCAL_AGENT") == "1":
        return {"ws_url": "ws://localhost:8080/ws"}

    # Get required environment variables
    access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    agent_runtime_arn = os.getenv("AGENT_RUNTIME_ARN")
    region = os.getenv("AWS_REGION")

    if not access_key_id or not secret_access_key or not agent_runtime_arn or not region:
        raise HTTPException(
            status_code=500,
            detail="Missing required environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AGENT_RUNTIME_ARN, or AWS_REGION",
        )

    try:
        # Construct the WebSocket URL
        ws_url = f"wss://bedrock-agentcore.{region}.amazonaws.com/runtimes/{quote(agent_runtime_arn, safe='')}/ws"

        # Create AWS credentials
        credentials = Credentials(access_key_id, secret_access_key)

        # Create an AWS request for signing
        aws_request = AWSRequest(method="GET", url=ws_url)

        # Sign the request using SigV4QueryAuth (adds signature to query string)
        url_expiry_seconds = int(os.getenv("SIGNED_URL_EXPIRY_SECONDS", "300"))
        SigV4QueryAuth(credentials, "bedrock-agentcore", region, expires=url_expiry_seconds).add_auth(aws_request)

        # Get the signed URL
        signed_url = aws_request.url

        return {"ws_url": signed_url}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate signed WebSocket URL: {str(e)}"
        )


if __name__ == "__main__":
    host = os.getenv("HOST", "localhost")
    port = int(os.getenv("PORT", "7860"))
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    server.run()
