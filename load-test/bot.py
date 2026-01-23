#
# Copyright (c) 2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Load test bot that plays a video file on loop.

This bot is designed for load testing and doesn't require any external API services.
It plays the daily.y4m video file in a continuous loop using GStreamer.

Pass room_url and token in body to join an existing Daily room.
"""

import asyncio
import os

from loguru import logger
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.gstreamer.pipeline_source import GStreamerPipelineSource
from pipecat.runner.types import RunnerArguments
from pipecat.transports.daily.transport import DailyParams, DailyTransport


async def bot(runner_args: RunnerArguments):
    """Main bot entry point for Pipecat Cloud.

    Args:
        runner_args: Runner arguments with body containing:
            - room_url: Daily room URL to join
            - token: Daily meeting token
            - bot_name: (optional) Display name for the bot, defaults to "LoadTestBot"
    """
    body: dict[str, str] = runner_args.body or {}
    # Check body first, then fall back to environment variables
    room_url = str(body.get("room_url") or os.getenv("DAILY_ROOM_URL", ""))
    token = str(body.get("token") or os.getenv("DAILY_TOKEN", ""))
    bot_name = str(body.get("bot_name", "LoadTestBot"))

    logger.info(f"Runner args body: {body}")

    if not room_url:
        logger.error("No room_url in body. Pass room_url and token in body.")
        return

    if not token:
        logger.error("No token in body. Pass room_url and token in body.")
        return

    logger.info(f"Joining room: {room_url}")
    logger.info("Starting load test bot with Y4M video playback")

    transport = DailyTransport(
        room_url,
        token,
        bot_name,
        params=DailyParams(
            audio_out_enabled=False,
            video_out_enabled=True,
            video_out_is_live=True,
            video_out_width=640,
            video_out_height=480,
        ),
    )

    # Path to video file
    video_path = os.path.join(os.path.dirname(__file__), "daily.y4m")

    # Create GStreamer pipeline to play Y4M video on loop
    # multifilesrc with loop=-1 loops the file indefinitely
    gst = GStreamerPipelineSource(
        pipeline=f'multifilesrc location="{video_path}" loop=-1 ! decodebin ! videoconvert ! videoscale ! capsfilter caps="video/x-raw,width=640,height=480,framerate=30/1"',
        out_params=GStreamerPipelineSource.OutputParams(
            video_width=640,
            video_height=480,
            clock_sync=True,
        ),
    )

    # Create pipeline
    pipeline = Pipeline([gst, transport.output()])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType, reportUnusedFunction]
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType, reportUnusedFunction]
        logger.info("Client disconnected")
        # Remove this line if you want the bot to stay in the room after disconnect
        await task.cancel()

    async def auto_leave_timeout():
        """Automatically leave the room after 10 minutes."""
        await asyncio.sleep(10 * 60)  # 10 minutes
        logger.info("Auto-leave timeout reached (10 minutes). Leaving room.")
        await task.cancel()

    # Start the auto-leave timer
    asyncio.create_task(auto_leave_timeout())

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
