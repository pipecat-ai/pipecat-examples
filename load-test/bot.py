#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Load test bot that plays a video file on loop.

This bot is designed for load testing and doesn't require any external API services.
It plays the daily.y4m video file in a continuous loop.
"""

import asyncio
import os

import numpy as np
from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import Frame, OutputAudioRawFrame, OutputImageRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.runner.types import (
    DailyRunnerArguments,
    RunnerArguments,
    SmallWebRTCRunnerArguments,
)
from pipecat.transports.base_transport import BaseTransport, TransportParams

load_dotenv(override=True)


class Y4MVideoPlayer(FrameProcessor):
    """Plays a Y4M video file on loop."""

    def __init__(self, video_path: str, fps: int = 30):
        super().__init__()
        self._video_path = video_path
        self._fps = fps
        self._running = False
        self._task = None
        self._width = None
        self._height = None
        self._frame_data = []

    async def start(self, frame: Frame):
        """Start playing video."""
        await super().start(frame)
        # Load video file
        if not os.path.exists(self._video_path):
            logger.error(f"Video file not found: {self._video_path}")
            return

        self._load_y4m_file()
        if not self._frame_data:
            logger.error("No frames loaded from video file")
            return

        self._running = True
        self._task = asyncio.create_task(self._play_video())

    async def stop(self, frame: Frame):
        """Stop playing video."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await super().stop(frame)

    def _load_y4m_file(self):
        """Load Y4M video file and parse frames."""
        try:
            with open(self._video_path, "rb") as f:
                # Read Y4M header
                header = b""
                while True:
                    char = f.read(1)
                    if char == b"\n":
                        break
                    header += char

                # Parse header
                header_str = header.decode("ascii")
                parts = header_str.split()

                # Parse dimensions from header (e.g., "YUV4MPEG2 W640 H480 F30:1 Ip A0:0")
                for part in parts:
                    if part.startswith("W"):
                        self._width = int(part[1:])
                    elif part.startswith("H"):
                        self._height = int(part[1:])
                    elif part.startswith("F"):
                        # Parse framerate if needed
                        pass

                logger.info(f"Loaded Y4M video: {self._width}x{self._height}")

                # Read all frames
                while True:
                    # Read frame header
                    frame_header = f.read(6)  # "FRAME\n"
                    if len(frame_header) < 6 or not frame_header.startswith(b"FRAME"):
                        break

                    # Calculate frame size (YUV420 format)
                    y_size = self._width * self._height
                    uv_size = y_size // 4
                    frame_size = y_size + uv_size * 2

                    # Read frame data
                    frame_data = f.read(frame_size)
                    if len(frame_data) < frame_size:
                        break

                    self._frame_data.append(frame_data)

                logger.info(f"Loaded {len(self._frame_data)} frames from video")

        except Exception as e:
            logger.error(f"Error loading Y4M file: {e}")
            self._frame_data = []

    def _yuv420_to_rgb(self, yuv_data):
        """Convert YUV420 frame data to RGB."""
        try:
            y_size = self._width * self._height
            uv_size = y_size // 4

            # Extract Y, U, V planes
            y_plane = yuv_data[:y_size]
            u_plane = yuv_data[y_size : y_size + uv_size]
            v_plane = yuv_data[y_size + uv_size :]

            # Reshape planes
            y = np.frombuffer(y_plane, dtype=np.uint8).reshape(self._height, self._width)
            u = np.frombuffer(u_plane, dtype=np.uint8).reshape(self._height // 2, self._width // 2)
            v = np.frombuffer(v_plane, dtype=np.uint8).reshape(self._height // 2, self._width // 2)

            # Upsample U and V
            u = np.repeat(np.repeat(u, 2, axis=0), 2, axis=1)
            v = np.repeat(np.repeat(v, 2, axis=0), 2, axis=1)

            # YUV to RGB conversion
            r = np.clip(y + 1.402 * (v - 128), 0, 255).astype(np.uint8)
            g = np.clip(y - 0.344136 * (u - 128) - 0.714136 * (v - 128), 0, 255).astype(np.uint8)
            b = np.clip(y + 1.772 * (u - 128), 0, 255).astype(np.uint8)

            # Stack RGB channels
            rgb = np.dstack((r, g, b))

            return rgb.tobytes()

        except Exception as e:
            logger.error(f"Error converting YUV to RGB: {e}")
            # Return black frame
            black = np.zeros((self._height, self._width, 3), dtype=np.uint8)
            return black.tobytes()

    async def _play_video(self):
        """Play video frames in a loop."""
        if not self._frame_data:
            logger.error("No video frames loaded")
            return

        frame_index = 0
        while self._running:
            try:
                # Get current frame
                yuv_data = self._frame_data[frame_index]

                # Convert to RGB
                rgb_data = self._yuv420_to_rgb(yuv_data)

                # Create output frame
                output_frame = OutputImageRawFrame(
                    image=rgb_data, size=(self._width, self._height), format="RGB"
                )
                await self.push_frame(output_frame)

                # Move to next frame (loop)
                frame_index = (frame_index + 1) % len(self._frame_data)

                # Wait for next frame time
                await asyncio.sleep(1.0 / self._fps)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error playing video frame: {e}")
                await asyncio.sleep(1.0)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Main bot logic that plays video on loop."""
    logger.info("Starting load test bot")

    # Path to video file
    video_path = os.path.join(os.path.dirname(__file__), "daily.y4m")

    # Create video player
    video_player = Y4MVideoPlayer(video_path=video_path, fps=30)

    # Create pipeline
    pipeline = Pipeline([video_player, transport.output()])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected - starting video playback")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""

    transport = None

    if isinstance(runner_args, DailyRunnerArguments):
        from pipecat.transports.daily.transport import DailyParams, DailyTransport

        transport = DailyTransport(
            runner_args.room_url,
            runner_args.token,
            "LoadTestBot",
            params=DailyParams(
                audio_out_enabled=False,
                video_out_enabled=True,
                video_out_width=640,
                video_out_height=480,
            ),
        )

    elif isinstance(runner_args, SmallWebRTCRunnerArguments):
        from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

        transport = SmallWebRTCTransport(
            params=TransportParams(
                audio_out_enabled=False,
                video_out_enabled=True,
                video_out_width=640,
                video_out_height=480,
            ),
            webrtc_connection=runner_args.webrtc_connection,
        )
    else:
        logger.error(f"Unsupported runner arguments type: {type(runner_args)}")
        return

    if transport is None:
        logger.error("Failed to create transport")
        return

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
