# ─────────────────────────────────────────────────────────────────────────────
# Nemotron ASR SageMaker Wrapper
#
# Extends the NVIDIA Nemotron ASR Streaming NIM image with a FastAPI layer that
# translates SageMaker's expected interface into NIM's actual API:
#
#   GET  /ping                              → NIM GET  /v1/health             (HTTP :9000)
#   POST /invocations                       → NIM WS   /v1/realtime?intent=transcription (:9000)
#   WS   /invocations-bidirectional-stream  → NIM WS   /v1/realtime?intent=transcription (:9000)
#
# The NIM server runs internally on port 9000 (its default).
# The FastAPI wrapper runs on port 8080, which SageMaker expects.
#
# Nemotron ASR Streaming requires the following environment variables at runtime:
#   NIM_TAGS_SELECTOR=mode=str
#   CONTAINER_ID=nemotron-asr-streaming
#
# Build with:
#   ./scripts/build_wrapper.sh nemotron-asr
# ─────────────────────────────────────────────────────────────────────────────

# NIM_IMAGE is the local image pulled by pull_nim.sh.
# Docker uses the local cache — it does not re-pull from NVIDIA's registry.
ARG NIM_IMAGE=nvcr.io/nim/nvidia/nemotron-asr-streaming:latest
FROM ${NIM_IMAGE}

# NIM's original entrypoint + cmd — detected by build_wrapper.sh via docker inspect
# and baked in here so entrypoint.sh knows how to start NIM without guessing.
ARG NIM_START_CMD=""
ENV NIM_START_CMD=${NIM_START_CMD}

# ── uv (fast Python package manager — no apt-get needed) ─────────────────────
# Copy the uv binary from its official image. Runs as root so we can write to
# /opt/wrapper and /usr/local/bin.
USER root
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── FastAPI wrapper dependencies ──────────────────────────────────────────────
WORKDIR /opt/wrapper
COPY sagemaker-wrapper/nemotron-asr/app/pyproject.toml /opt/wrapper/pyproject.toml
RUN uv sync --no-dev

# ── FastAPI wrapper app ───────────────────────────────────────────────────────
COPY sagemaker-wrapper/nemotron-asr/app/ /opt/wrapper/app/

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY sagemaker-wrapper/nemotron-asr/entrypoint.sh /opt/wrapper/entrypoint.sh
RUN chmod +x /opt/wrapper/entrypoint.sh

# SageMaker expects the container to listen on port 8080.
# The bidirectional-streaming label tells SageMaker to enable the HTTP/2 bidi
# stream sidecar, which proxies to ws://localhost:8080/invocations-bidirectional-stream.
LABEL com.amazonaws.sagemaker.capabilities.bidirectional-streaming=true
EXPOSE 8080

ENTRYPOINT ["/opt/wrapper/entrypoint.sh"]
