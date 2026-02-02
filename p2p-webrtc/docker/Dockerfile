# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

# Upgrade pip and install build tooling
RUN pip install --upgrade pip setuptools wheel

# Install the project and its dependencies
RUN pip install --no-cache-dir .

# Copy the current directory contents into the container
COPY . .

# Expose the desired port
EXPOSE 7860

# Run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
