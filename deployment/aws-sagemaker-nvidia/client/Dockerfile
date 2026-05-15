FROM dailyco/pipecat-base:latest

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install dependencies using the lockfile
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy bot implementation flat into the working directory so that the `services`
# package is importable, then create the bot.py entry point Pipecat Cloud expects
COPY ./bot/ ./
RUN ln -s pipecat-bot-ws.py bot.py
