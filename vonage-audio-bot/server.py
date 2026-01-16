"""
vonage_server.py

HTTP endpoint to trigger Vonage Audio Connector -> WebSocket connection
and a WebSocket endpoint to receive/send media frames via Pipecat.

Run:
  uvicorn vonage_server:app --host 0.0.0.0 --port 8005

Env required:
  VONAGE_API_KEY
  VONAGE_API_SECRET
  VONAGE_SESSION_ID
  VONAGE_AUDIO_WS_URI          (public wss://.../ws OR omit and let server build)
Optional:
  OPENTOK_API_URL              (default https://api.opentok.com)
  VONAGE_AUDIO_RATE            (default 16000)
  ENV                          (local/production - optional)
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from opentok import Client as OpenTokClient  # Opentok Video SDK
from vonage import Auth, HttpClientOptions, Vonage
from vonage_video import AudioConnectorOptions, TokenOptions

load_dotenv(override=True)


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise HTTPException(status_code=500, detail=f"Missing env var: {name}")
    return val


async def connect_audio_connector(
    *,
    api_key: str,
    api_secret: str,
    session_id: str,
    ws_uri: str,
    audio_rate: int,
    api_base: str,
    application_id: str,
    private_key: str,
) -> Any:
    """
    Calls Vonage (OpenTok) Audio Connector connect API.
    OpenTok SDK is synchronous, so run in a thread executor.
    """
    logger.info(
        f"Calling Vonage Audio Connector connect: session_id={session_id}, ws_uri={ws_uri}, audioRate={audio_rate}"
    )

    def _call_opentok_connect() -> Any:
        try:
            ot = OpenTokClient(api_key, api_secret, api_url=api_base)
        except TypeError:
            ot = OpenTokClient(api_key, api_secret)

        token = ot.generate_token(session_id)
        ws_opts = {
            "uri": ws_uri,
            "audioRate": audio_rate,
            "bidirectional": True,
        }
        resp = ot.connect_audio_to_websocket(session_id, token, ws_opts)
        return resp

    def _call_vonage_connect() -> Any:
        # Create an Auth instance
        logger.info("CREATING AUTH")
        auth = Auth(
            application_id=application_id,
            private_key=private_key,
        )

        options = HttpClientOptions(video_host="video." + api_base, timeout=30)

        # Create a Vonage instance
        vng = Vonage(auth=auth, http_client_options=options)

        token_options = TokenOptions(session_id=session_id, role="publisher")
        client_token = vng.video.generate_client_token(token_options)
        ws_opts = {
            "uri": ws_uri,
            "audioRate": audio_rate,
            "bidirectional": True,
        }

        audio_connector_options = AudioConnectorOptions(
            session_id=session_id, token=client_token, websocket=ws_opts
        )
        return vng.video.start_audio_connector(audio_connector_options)

    loop = asyncio.get_running_loop()
    # Choose which connector to call based on the flag
    if application_id:
        return await loop.run_in_executor(None, _call_vonage_connect)
    else:
        return await loop.run_in_executor(None, _call_opentok_connect)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # place for shared resources if needed later
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/connect")
async def connect(request: Request) -> JSONResponse:
    """
    Trigger Vonage Audio Connector to connect to our WebSocket.
    You can call this from curl or from your UI/client.
    """
    application_id = os.getenv("VONAGE_APPLICATION_ID")
    private_key = os.getenv("VONAGE_PRIVATE_KEY")

    api_key = os.getenv("OPENTOK_API_KEY")
    api_secret = os.getenv("OPENTOK_API_SECRET")

    # Determine API base and set the flag indicating application-based auth
    if application_id and private_key:
        # Vonage application auth path uses Vonage Video API host
        api_base = os.getenv("API_URL", "api.vonage.com")
        use_application_auth = True
    elif api_key and api_secret:
        # OpenTok key/secret path uses OpenTok API URL
        api_base = os.getenv("API_URL", "https://api.opentok.com")
        use_application_auth = False
    else:
        raise HTTPException(
            status_code=500,
            detail="Missing Vonage auth env vars: either VONAGE_APPLICATION_ID and VONAGE_PRIVATE_KEY, or VONAGE_API_KEY and VONAGE_API_SECRET",
        )

    session_id = _require_env("VONAGE_SESSION_ID")
    audio_rate = int(os.getenv("VONAGE_AUDIO_RATE", "16000"))
    ws_uri = os.getenv("WS_URI")

    try:
        resp = await connect_audio_connector(
            api_key=api_key,
            api_secret=api_secret,
            session_id=session_id,
            ws_uri=ws_uri,
            audio_rate=audio_rate,
            api_base=api_base,
            application_id=application_id,
            private_key=private_key,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect Audio Connector: {e}")

    return JSONResponse(
        {
            "status": "connect_triggered",
            "session_id": session_id,
            "ws_uri": ws_uri,
            "audio_rate": audio_rate,
            "opentok_api_url": api_base,
            "response_repr": repr(resp),
        }
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Vonage Audio Connector will connect here and start sending frames.
    We accept the connection, then pass it into your Pipecat bot
    using WebSocketRunnerArguments.
    """
    await websocket.accept()
    logger.info("Vonage WebSocket connected to /ws")

    try:
        # Import your bot (must be in bot.py with: async def bot(runner_args): ...)
        from bot import bot
        from pipecat.runner.types import WebSocketRunnerArguments

        # You can pass custom injected data via runner_args.body if you want.
        runner_args = WebSocketRunnerArguments(websocket=websocket, body={})

        await bot(runner_args)

    except Exception as e:
        logger.exception(f"Error while running Pipecat bot on Vonage websocket: {e}")
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)
