#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Modal deployment for the Twilio webhook server.

This file deploys server.py to Modal with a public HTTPS endpoint.
Run with: modal deploy modal_server.py

The deployed URL will be printed and can be used as the Twilio webhook URL.
"""

import modal

app = modal.App("daily-twilio-webhook")

# Create the image with all required dependencies and copy local files
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "fastapi",
        "uvicorn",
        "aiohttp",
        "python-dotenv",
        "loguru",
        "twilio",
        "pydantic",
        "pipecat-ai",
        "pipecatcloud",
        "python-multipart",
    )
    .add_local_file("server.py", "/root/server.py")
    .add_local_file("server_utils.py", "/root/server_utils.py")
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("daily-twilio-secrets")],
)
@modal.asgi_app()
def fastapi_app():
    """Return the FastAPI app for Modal to serve."""
    import os
    import sys

    # Add mounted files to path
    sys.path.insert(0, "/root")

    # Set production environment
    os.environ["ENV"] = "production"

    from server import app

    return app
