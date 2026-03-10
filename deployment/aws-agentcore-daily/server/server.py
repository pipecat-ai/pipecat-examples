#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import json
import os
import sys
import uuid

import boto3
import uvicorn
from botocore.response import StreamingBody
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

load_dotenv(override=True)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Bedrock client.
# boto3 picks up credentials (including AWS_SESSION_TOKEN) from the standard
# credential chain. For production, consider using a credential provider that
# automatically refreshes temporary credentials instead of env vars.
bedrock = boto3.client("bedrock-agentcore")

# You can find this inside .bedrock_agentcore.yaml
AGENT_RUNTIME_ARN = os.getenv("AGENT_RUNTIME_ARN")
DAILY_ROOM_URL = os.getenv("DAILY_ROOM_URL")


@app.post("/start")
async def start_agent(request: Request):
    """Invoke AgentCore Runtime and return the Daily room URL."""
    if not AGENT_RUNTIME_ARN:
        raise HTTPException(500, "AGENT_RUNTIME_ARN not configured")

    if not DAILY_ROOM_URL:
        raise HTTPException(500, "DAILY_ROOM_URL not configured")

    # Invoke the agent with the room URL so it knows where to join
    payload = {"room_url": DAILY_ROOM_URL}
    try:
        body = await request.json()
        if body:
            payload.update(body)
    except Exception:
        pass

    logger.info(f"Invoking agent runtime: {AGENT_RUNTIME_ARN}")

    response = bedrock.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        contentType="application/json",
        payload=json.dumps(payload),
        runtimeSessionId=str(uuid.uuid4()),
    )

    # Read the first status event to confirm agent started
    if "text/event-stream" in response.get("contentType", ""):
        streaming_body: StreamingBody = response["response"]
        for line in streaming_body.iter_lines(chunk_size=1):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                    try:
                        event = json.loads(line)
                        logger.info(f"Agent event: {event}")
                        if "status" in event:
                            break
                    except json.JSONDecodeError:
                        pass

    return {"room_url": DAILY_ROOM_URL, "status": "ok"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily AgentCore server")
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

    uvicorn.run(app, host=args.host, port=args.port)
