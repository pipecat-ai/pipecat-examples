#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import os
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

# Configure CORS to allow requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/start")
async def start_bot(request: Request) -> Dict[Any, Any]:
    """
    Start endpoint that generates a signed WebSocket URL for connecting to the agent on AWS Bedrock AgentCore.

    Returns:
        Dict[Any, Any]: Contains the signed WebSocket URL for the client to connect
    """
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
        SigV4QueryAuth(credentials, "bedrock-agentcore", region).add_auth(aws_request)

        # Get the signed URL
        signed_url = aws_request.url

        return {"ws_url": signed_url}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate signed WebSocket URL: {str(e)}"
        )


if __name__ == "__main__":
    config = uvicorn.Config(app, host="0.0.0.0", port=7860)
    server = uvicorn.Server(config)
    server.run()
