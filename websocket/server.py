#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pipecat.runner.types import WebSocketRunnerArguments

# Load environment variables
load_dotenv(override=True)

from bot import bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles FastAPI startup and shutdown."""
    yield  # Run app


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


@app.websocket("/ws/generic")
async def websocket_endpoint(websocket: WebSocket):
    service_host = websocket.query_params.get("serviceHost")
    print(f"WebSocket connection received for service host path: {service_host}")
    await websocket.accept()
    print("WebSocket connection accepted")
    try:
        runner_args = WebSocketRunnerArguments(websocket=websocket)
        await bot(runner_args)
    except Exception as e:
        print(f"Exception in run_bot: {e}")


async def main():
    tasks = []
    try:
        config = uvicorn.Config(app, host="0.0.0.0", port=7860)
        server = uvicorn.Server(config)
        tasks.append(server.serve())

        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        print("Tasks cancelled (probably due to shutdown).")


if __name__ == "__main__":
    asyncio.run(main())
