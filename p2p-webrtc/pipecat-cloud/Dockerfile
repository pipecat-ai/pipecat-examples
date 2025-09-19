# TODO: replace for pipecat-base:latest, only for local testing
# I have built the local pipecat base image like this
# docker build -t dailyco/pipecat-base:pcc .
FROM dailyco/pipecat-base:pcc

# Install system dependencies required for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Only for local development with the local versions of Pipecat and Pipecat Cloud
# First you need to build both Pipecat and Pipecat Cloud
# python -m build
COPY ./pipecatcloud-0.2.4.tar.gz pipecatcloud-0.2.4.tar.gz
RUN uv pip install ./pipecatcloud-0.2.4.tar.gz
COPY ./pipecat_ai-0.0.86.dev38.tar.gz pipecat_ai-0.0.86.dev38.tar.gz
RUN uv pip install ./pipecat_ai-0.0.86.dev38.tar.gz
# COPY ./.env .env
# --------- end of local development

COPY ./bot.py bot.py
