#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from http import HTTPMethod
from typing import Any, Dict, List, Optional, TypedDict, Union

import boto3
import uvicorn
from botocore.response import StreamingBody
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from loguru import logger
from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI

load_dotenv(override=True)

app = FastAPI()

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


# In-memory store of active sessions: session_id -> session info
active_sessions: Dict[str, Dict[str, Any]] = {}

# Initialize Bedrock client
bedrock = boto3.client("bedrock-agentcore")

# You can find this inside .bedrock_agentcore.yaml
AGENT_RUNTIME_ARN = os.getenv("AGENT_RUNTIME_ARN")

# Mount the frontend at /
app.mount("/client", SmallWebRTCPrebuiltUI)


# Ice servers
class IceServer(TypedDict, total=False):
    urls: Union[str, List[str]]
    username: Optional[str]
    credential: Optional[str]


raw_urls = os.getenv("ICE_SERVER_URLS")
urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
ice_servers = [
    IceServer(
        urls=urls,
        username=os.getenv("ICE_SERVER_USERNAME"),
        credential=os.getenv("ICE_SERVER_CREDENTIAL"),
    )
]

logger.info(f"Ice servers configured: {len(ice_servers)} server(s) with URLs: {urls}")


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/client/")


async def post_offer(request: Request, session_id: str):
    """Handle WebRTC offer requests."""

    data = await request.json()
    request = {"type": "offer", "data": data}

    response = bedrock.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        contentType="application/json",
        payload=json.dumps(request),
        runtimeSessionId=session_id,
    )

    answer_sdp = None

    if "text/event-stream" in response.get("contentType", ""):
        # Handle streaming response
        streaming_body: StreamingBody = response["response"]
        for line in streaming_body.iter_lines(chunk_size=1):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                    print(f"Received line: {line}")
                    try:
                        event = json.loads(line)
                        print("Received event:", event)

                        # 4. Check for the 'answer' key
                        if "answer" in event:
                            payload = event["answer"]

                            if payload.get("type") == "answer":
                                answer_sdp = payload
                                print("WebRTC answer found. Stopping stream processing.")
                                # Break the line loop immediately
                                break

                    except json.JSONDecodeError:
                        print(f"Failed to parse extracted SSE payload as JSON: {line}")
                        pass

    if answer_sdp is None:
        raise HTTPException(500, "Did not find WebRTC answer in agent output")

    return answer_sdp


async def patch_offer(request: Request, session_id: str):
    """Handle WebRTC new ice candidate requests."""

    data = await request.json()
    request = {"type": "ice-candidates", "data": data}

    response = bedrock.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        contentType="application/json",
        payload=json.dumps(request),
        runtimeSessionId=session_id,
    )

    result = None

    if "text/event-stream" in response.get("contentType", ""):
        # Handle streaming response
        streaming_body: StreamingBody = response["response"]
        for line in streaming_body.iter_lines(chunk_size=1):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                    print(f"Received line: {line}")
                    try:
                        # Assume the first valid JSON line is the result
                        result = json.loads(line)
                        print("Received event:", result)
                        break
                    except json.JSONDecodeError:
                        print(f"Failed to parse extracted SSE payload as JSON: {line}")
                        pass

    if result is None:
        raise HTTPException(500, "Did not get ICE candidate ack from agent")

    return result


@app.post("/start")
async def rtvi_start(request: Request):
    """Mimic Pipecat Cloud's /start endpoint."""
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    class IceConfig(TypedDict):
        iceServers: List[IceServer]

    class StartBotResult(TypedDict, total=False):
        sessionId: str
        iceConfig: Optional[IceConfig]

    # Parse the request body
    try:
        request_data = await request.json()
        logger.debug(f"Received request: {request_data}")
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        request_data = {}

    # Store session info immediately in memory, replicate the behavior expected on Pipecat Cloud
    session_id = str(uuid.uuid4())
    active_sessions[session_id] = request_data

    result: StartBotResult = {"sessionId": session_id}
    if request_data.get("enableDefaultIceServers"):
        result["iceConfig"] = IceConfig(iceServers=ice_servers)

    return result


@app.api_route(
    "/sessions/{session_id}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_request(
    session_id: str, path: str, request: Request, background_tasks: BackgroundTasks
):
    """Mimic Pipecat Cloud's proxy."""
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    active_session = active_sessions.get(session_id)
    if active_session is None:
        return Response(content="Invalid or not-yet-ready session_id", status_code=404)

    if path.endswith("api/offer"):
        try:
            if request.method == HTTPMethod.POST.value:
                return await post_offer(request, session_id)
            elif request.method == HTTPMethod.PATCH.value:
                return await patch_offer(request, session_id)
        except Exception as e:
            logger.error(f"Failed to parse WebRTC request: {e}")
            return Response(content="Invalid WebRTC request", status_code=400)

    logger.info(f"Received request for path: {path}")
    return Response(status_code=200)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # Run app


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

    uvicorn.run(app, host=args.host, port=args.port)
