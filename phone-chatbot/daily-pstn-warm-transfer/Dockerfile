FROM dailyco/pipecat-base:latest

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install the project's dependencies using the lockfile and settings
# Install the project's dependencies using pyproject.toml  
RUN --mount=type=cache,target=/root/.cache/uv \  
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \  
    uv sync --no-lock --no-install-project --no-dev 

# Copy the application code
COPY ./bot.py bot.py
COPY ./models.py models.py
COPY ./hold_music.wav hold_music.wav
