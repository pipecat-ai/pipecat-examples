#!/usr/bin/env python3
#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Start multiple load test agents using the Pipecat Cloud API.

This script starts multiple agents that join a specified Daily room.
Each agent generates video using GStreamer's videotestsrc.

Required environment variables:
- PIPECAT_API_KEY: Pipecat Cloud public API key
- DAILY_ROOM_URL: Daily room URL to join (e.g., https://yourdomain.daily.co/yourroom)
- DAILY_API_KEY: Daily API key (for generating meeting tokens)
"""

import argparse
import asyncio
import os
import time
from typing import Any, List, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

load_dotenv(override=True)

PIPECAT_CLOUD_API_URL = "https://api.pipecat.daily.co/v1"
DAILY_API_URL = "https://api.daily.co/v1"
AGENT_NAME = "load-test"
DEFAULT_NUM_AGENTS = 5


class RateLimitError(Exception):
    """Raised when an API returns a rate limit response (429)."""

    pass


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda retry_state: logger.warning(
        f"Rate limited, retrying... (attempt {retry_state.attempt_number}/5)"
    ),
)
async def get_daily_token(client: httpx.AsyncClient, daily_api_key: str, room_url: str) -> str:
    """Generate a Daily meeting token for joining the room."""
    # Extract room name from URL
    room_name = urlparse(room_url).path.lstrip("/")

    # Token expires in 1 hour
    expiry = int(time.time()) + 3600

    response = await client.post(
        f"{DAILY_API_URL}/meeting-tokens",
        headers={
            "Authorization": f"Bearer {daily_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "properties": {
                "room_name": room_name,
                "exp": expiry,
                "is_owner": False,
            }
        },
    )

    if response.status_code == 200:
        return response.json()["token"]
    elif response.status_code == 429:
        raise RateLimitError(f"Daily API rate limited: {response.text}")
    else:
        raise Exception(f"Failed to create Daily token: {response.status_code} - {response.text}")


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    stop=stop_after_attempt(5),
    before_sleep=lambda retry_state: logger.warning(
        f"Rate limited, retrying... (attempt {retry_state.attempt_number}/5)"
    ),
)
async def start_agent(
    client: httpx.AsyncClient,
    pipecat_api_key: str,
    daily_api_key: str,
    room_url: str,
    agent_num: int,
) -> Optional[dict[str, Any]]:
    """Start a single agent and have it join the room."""
    print(f"Starting agent {agent_num}...")

    # Generate a Daily token for this agent
    try:
        token = await get_daily_token(client, daily_api_key, room_url)
    except Exception as e:
        print(f"Agent {agent_num} failed to get token: {e}")
        return None

    # Start the agent with room_url, token, and bot_name in the body
    bot_name = f"LoadTestBot-{agent_num}"
    response = await client.post(
        f"{PIPECAT_CLOUD_API_URL}/public/{AGENT_NAME}/start",
        headers={
            "Authorization": f"Bearer {pipecat_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "createDailyRoom": False,
            "body": {
                "room_url": room_url,
                "token": token,
                "bot_name": bot_name,
            },
        },
    )

    if response.status_code == 200:
        data = response.json()
        print(f"Agent {agent_num} started: session={data.get('sessionId', 'unknown')}")
        return data
    elif response.status_code == 429:
        raise RateLimitError(f"Pipecat API rate limited for agent {agent_num}: {response.text}")
    else:
        print(f"Agent {agent_num} failed: {response.status_code} - {response.text}")
        return None


async def main(num_agents: int) -> None:
    pipecat_api_key = os.getenv("PIPECAT_API_KEY") or os.getenv("PIPECAT_CLOUD_API_KEY")
    daily_api_key = os.getenv("DAILY_API_KEY")
    room_url = os.getenv("DAILY_ROOM_URL")

    logger.debug(
        f"Environment: PIPECAT_API_KEY={'set' if pipecat_api_key else 'not set'}, "
        f"DAILY_API_KEY={'set' if daily_api_key else 'not set'}, "
        f"DAILY_ROOM_URL={'set' if room_url else 'not set'}"
    )

    if not pipecat_api_key:
        print("Error: PIPECAT_API_KEY environment variable is required")
        return

    if not daily_api_key:
        print(
            "Error: DAILY_API_KEY environment variable is required (for generating meeting tokens)"
        )
        return

    if not room_url:
        print("Error: DAILY_ROOM_URL environment variable is required")
        return

    print(f"Starting {num_agents} agents to join room: {room_url}")
    print("-" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [
            start_agent(client, pipecat_api_key, daily_api_key, room_url, i + 1)
            for i in range(num_agents)
        ]
        results = await asyncio.gather(*tasks)

    successful = sum(1 for r in results if r is not None)
    print("-" * 60)
    print(f"Started {successful}/{num_agents} agents successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start multiple load test agents")
    parser.add_argument(
        "-n",
        "--num-agents",
        type=int,
        default=DEFAULT_NUM_AGENTS,
        help=f"Number of agents to start (default: {DEFAULT_NUM_AGENTS})",
    )
    args = parser.parse_args()
    asyncio.run(main(args.num_agents))
