# ─────────────────────────────────────────────────────────────────────────────
# Magpie TTS SageMaker Wrapper
#
# Extends the NVIDIA Magpie TTS NIM image with a FastAPI layer that translates
# SageMaker's expected interface into NIM's actual API:
#
#   GET  /ping                              → NIM GET  /v1/health/ready        (HTTP :9000)
#   POST /invocations                       → NIM POST /v1/audio/synthesize_online (HTTP :9000, streaming)
#   WS   /invocations-bidirectional-stream  → NIM WS   /v1/realtime?intent=synthesize (:9000)
#
# The NIM server runs internally on port 9000 (its default).
# The FastAPI wrapper runs on port 8080, which SageMaker expects.
#
# Build with:
#   ./scripts/build_wrapper.sh
# ─────────────────────────────────────────────────────────────────────────────

# NIM_IMAGE is the local image pulled by pull_nim.sh.
# Docker uses the local cache — it does not re-pull from NVIDIA's registry.
ARG NIM_IMAGE=nvcr.io/nim/nvidia/magpie-tts-multilingual:latest
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
COPY sagemaker-wrapper/magpie/app/pyproject.toml /opt/wrapper/pyproject.toml
RUN uv sync --no-dev

# ── FastAPI wrapper app ───────────────────────────────────────────────────────
COPY sagemaker-wrapper/magpie/app/ /opt/wrapper/app/

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY sagemaker-wrapper/magpie/entrypoint.sh /opt/wrapper/entrypoint.sh
RUN chmod +x /opt/wrapper/entrypoint.sh

# SageMaker expects the container to listen on port 8080.
# The bidirectional-streaming label tells SageMaker to enable the HTTP/2 bidi
# stream sidecar, which proxies to ws://localhost:8080/invocations-bidirectional-stream.
LABEL com.amazonaws.sagemaker.capabilities.bidirectional-streaming=true
EXPOSE 8080

ENTRYPOINT ["/opt/wrapper/entrypoint.sh"]
