#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Orchestration script to start 1000 concurrent Pipecat Cloud agents.

This script:
1. Batch-creates 1000 Daily rooms in a single API call
2. Starts Pipecat Cloud agents for each room with rate limit handling
3. Logs progress and errors to agents.log
"""

import argparse
import asyncio
import os
import random
import sys
import time

import aiohttp
from dotenv import load_dotenv
from loguru import logger

load_dotenv(override=True)

# Configure logging to file and stderr
logger.remove(0)
logger.add(sys.stderr, level="INFO")
logger.add("agents.log", level="DEBUG")

DAILY_API_URL = "https://api.daily.co/v1"
PIPECAT_CLOUD_API_URL = "https://api.pipecat.daily.co/v1"

# Rate limit settings
MAX_CONCURRENT_REQUESTS = 30
BASE_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 30.0
MAX_RETRIES = 10


async def batch_create_rooms(
    session: aiohttp.ClientSession,
    num_rooms: int,
    room_prefix: str,
    daily_api_key: str,
) -> list[dict]:
    """Create multiple Daily rooms in a single batch API call.

    Args:
        session: aiohttp session
        num_rooms: Number of rooms to create
        room_prefix: Prefix for room names
        daily_api_key: Daily API key

    Returns:
        List of created room objects
    """
    # Room expiration: 3 minutes from now
    exp_time = int(time.time()) + 180

    rooms_config = [
        {
            "name": f"{room_prefix}-{i:04d}",
            "properties": {
                "exp": exp_time,
            },
        }
        for i in range(num_rooms)
    ]

    logger.info(f"Creating {num_rooms} rooms via batch API...")

    async with session.post(
        f"{DAILY_API_URL}/batch/rooms",
        headers={"Authorization": f"Bearer {daily_api_key}"},
        json={"rooms": rooms_config},
    ) as response:
        if response.status != 200:
            error_text = await response.text()
            raise Exception(f"Failed to create rooms: {response.status} - {error_text}")

        result = await response.json()
        logger.debug(f"Batch API response: {result}")

        # The batch API returns rooms in the "data" array
        rooms = result.get("data", [])
        logger.info(f"Successfully created {len(rooms)} rooms")
        return rooms


async def start_agent_with_retry(
    session: aiohttp.ClientSession,
    room_url: str,
    room_name: str,
    agent_name: str,
    pipecat_api_key: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Start a Pipecat Cloud agent with exponential backoff retry.

    Args:
        session: aiohttp session
        room_url: Daily room URL
        room_name: Room name for logging
        agent_name: Pipecat Cloud agent name
        pipecat_api_key: Pipecat Cloud API key
        semaphore: Semaphore for concurrency control

    Returns:
        Result dict with status and details
    """
    async with semaphore:
        retry_delay = BASE_RETRY_DELAY

        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(
                    f"{PIPECAT_CLOUD_API_URL}/public/{agent_name}/start",
                    headers={
                        "Authorization": f"Bearer {pipecat_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "createDailyRoom": False,
                        "transport": "daily",
                        "dailyRoomUrl": room_url,  # Top-level for Pipecat Cloud
                        "body": {
                            "dailyRoomUrl": room_url,  # Also in body for bot access
                        },
                    },
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Started agent for {room_name}")
                        return {"room": room_name, "status": "success", "result": result}

                    elif response.status == 429:
                        # Rate limited - retry with exponential backoff + jitter
                        jitter = random.uniform(0, retry_delay * 0.1)
                        wait_time = retry_delay + jitter
                        logger.warning(
                            f"Rate limited for {room_name}, "
                            f"retrying in {wait_time:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait_time)
                        retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)

                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to start agent for {room_name}: "
                            f"{response.status} - {error_text}"
                        )
                        return {
                            "room": room_name,
                            "status": "error",
                            "error": f"{response.status}: {error_text}",
                        }

            except Exception as e:
                logger.error(f"Exception starting agent for {room_name}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)

        return {"room": room_name, "status": "failed", "error": "Max retries exceeded"}


async def start_all_agents(
    rooms: list[dict],
    agent_name: str,
    pipecat_api_key: str,
) -> list[dict]:
    """Start agents for all rooms with concurrency control.

    Args:
        rooms: List of Daily room objects
        agent_name: Pipecat Cloud agent name
        pipecat_api_key: Pipecat Cloud API key

    Returns:
        List of results for each agent
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession() as session:
        tasks = [
            start_agent_with_retry(
                session=session,
                room_url=room["url"],
                room_name=room["name"],
                agent_name=agent_name,
                pipecat_api_key=pipecat_api_key,
                semaphore=semaphore,
            )
            for room in rooms
        ]

        logger.info(f"Starting {len(tasks)} agents (max {MAX_CONCURRENT_REQUESTS} concurrent)...")
        results = await asyncio.gather(*tasks)

    return results


def summarize_results(results: list[dict]) -> None:
    """Log a summary of the agent start results."""
    success = sum(1 for r in results if r["status"] == "success")
    errors = sum(1 for r in results if r["status"] == "error")
    failed = sum(1 for r in results if r["status"] == "failed")

    logger.info("=" * 50)
    logger.info("SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Total agents: {len(results)}")
    logger.info(f"Successful: {success}")
    logger.info(f"Errors: {errors}")
    logger.info(f"Failed (max retries): {failed}")

    if errors + failed > 0:
        logger.info("\nFailed rooms:")
        for r in results:
            if r["status"] != "success":
                logger.info(f"  - {r['room']}: {r.get('error', 'unknown')}")


async def verify_active_sessions(
    agent_name: str,
    pipecat_private_api_key: str,
    expected_count: int,
) -> dict:
    """Verify that agents are actually running by checking active sessions.

    Args:
        agent_name: Pipecat Cloud agent name
        pipecat_private_api_key: Pipecat Cloud Private API key (from Dashboard > Settings > API Keys > Private)
        expected_count: Expected number of active sessions

    Returns:
        Dict with verification results
    """
    logger.info("Verifying active sessions...")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{PIPECAT_CLOUD_API_URL}/agents/{agent_name}/sessions",
            headers={
                "Authorization": f"Bearer {pipecat_private_api_key}",
            },
            params={
                "status": "active",
                "limit": expected_count + 100,  # Get a bit more than expected
            },
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Failed to get sessions: {response.status} - {error_text}")
                return {"verified": False, "error": error_text}

            result = await response.json()
            logger.debug(f"Sessions API response: {result}")
            total_count = result.get("total_count", 0)
            sessions = result.get("sessions", [])

            logger.info("=" * 50)
            logger.info("VERIFICATION")
            logger.info("=" * 50)
            logger.info(f"Expected active sessions: {expected_count}")
            logger.info(f"Active sessions (total_count): {total_count}")

            if total_count >= expected_count:
                logger.info("✅ Verification PASSED - All agents are running!")
            else:
                logger.warning(
                    f"⚠️ Verification WARNING - Only {total_count}/{expected_count} agents running"
                )

            # Log some session details from the sample returned
            cold_starts = sum(1 for s in sessions if s.get("coldStart", False))
            warm_starts = len(sessions) - cold_starts
            logger.info(
                f"Sample of {len(sessions)} sessions - Cold starts: {cold_starts}, Warm starts: {warm_starts}"
            )

            return {
                "verified": total_count >= expected_count,
                "expected": expected_count,
                "active": total_count,
                "cold_starts": cold_starts,
                "warm_starts": warm_starts,
            }


async def main():
    parser = argparse.ArgumentParser(description="Start 1000 concurrent Pipecat Cloud agents")
    parser.add_argument(
        "--agent-name",
        type=str,
        required=True,
        help="Name of the deployed Pipecat Cloud agent",
    )
    parser.add_argument(
        "--num-agents",
        type=int,
        default=1000,
        help="Number of agents to start (default: 1000)",
    )
    parser.add_argument(
        "--room-prefix",
        type=str,
        default="concurrent-test",
        help="Prefix for room names (default: concurrent-test)",
    )
    args = parser.parse_args()

    daily_api_key = os.getenv("DAILY_API_KEY")
    pipecat_api_key = os.getenv("PIPECAT_CLOUD_API_KEY")
    pipecat_private_api_key = os.getenv("PIPECAT_CLOUD_PRIVATE_API_KEY")

    if not daily_api_key:
        raise ValueError("DAILY_API_KEY environment variable is required")
    if not pipecat_api_key:
        raise ValueError("PIPECAT_CLOUD_API_KEY environment variable is required")

    logger.info(f"Starting {args.num_agents} agents with prefix '{args.room_prefix}'")

    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        # Step 1: Batch create all rooms
        rooms = await batch_create_rooms(
            session=session,
            num_rooms=args.num_agents,
            room_prefix=args.room_prefix,
            daily_api_key=daily_api_key,
        )

    room_creation_time = time.time()
    logger.info(f"Room creation took {room_creation_time - start_time:.2f} seconds")

    # Step 2: Start agents for all rooms
    results = await start_all_agents(
        rooms=rooms,
        agent_name=args.agent_name,
        pipecat_api_key=pipecat_api_key,
    )

    agent_start_time = time.time()
    total_time = agent_start_time - start_time
    agent_only_time = agent_start_time - room_creation_time

    # Step 3: Summarize results
    summarize_results(results)
    logger.info(f"Agent startup took {agent_only_time:.2f} seconds")
    logger.info(f"Total time: {total_time:.2f} seconds")

    # Step 4: Verify active sessions (requires Private API key)
    success_count = sum(1 for r in results if r["status"] == "success")
    if success_count > 0 and pipecat_private_api_key:
        # Wait a moment for sessions to register
        logger.info("Waiting 5 seconds for sessions to register...")
        await asyncio.sleep(5)

        await verify_active_sessions(
            agent_name=args.agent_name,
            pipecat_private_api_key=pipecat_private_api_key,
            expected_count=success_count,
        )
    elif success_count > 0:
        logger.info("Skipping verification (PIPECAT_CLOUD_PRIVATE_API_KEY not set)")
    else:
        logger.error("No agents started successfully, skipping verification")


if __name__ == "__main__":
    asyncio.run(main())
