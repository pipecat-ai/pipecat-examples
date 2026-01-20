#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Load test bot that generates video and audio frames on loop.

This bot is designed for load testing and doesn't require any external API services.
It generates numbered/colored video frames and audio beeps programmatically.
"""

import asyncio
import io
import wave

import numpy as np
from dotenv import load_dotenv
from loguru import logger
from PIL import Image, ImageDraw, ImageFont
from pipecat.frames.frames import Frame, OutputAudioRawFrame, OutputImageRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import (
    DailyRunnerArguments,
    RunnerArguments,
    SmallWebRTCRunnerArguments,
)
from pipecat.transports.base_transport import BaseTransport, TransportParams

load_dotenv(override=True)


class FrameGeneratorProcessor(FrameProcessor):
    """Generates video frames with numbers and colors continuously."""

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30):
        super().__init__()
        self._width = width
        self._height = height
        self._fps = fps
        self._frame_count = 0
        self._running = False
        self._task = None

    async def start(self, frame: Frame):
        """Start generating frames."""
        await super().start(frame)
        self._running = True
        self._task = asyncio.create_task(self._generate_frames())

    async def stop(self, frame: Frame):
        """Stop generating frames."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await super().stop(frame)

    async def _generate_frames(self):
        """Generate frames continuously."""
        colors = [
            (255, 0, 0),  # Red
            (0, 255, 0),  # Green
            (0, 0, 255),  # Blue
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
        ]

        while self._running:
            try:
                # Create image with colored background
                color = colors[self._frame_count % len(colors)]
                img = Image.new("RGB", (self._width, self._height), color=color)
                draw = ImageDraw.Draw(img)

                # Draw frame number
                try:
                    # Try to use a default font, fall back to basic if not available
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 100
                    )
                except Exception:
                    font = ImageFont.load_default()

                text = str(self._frame_count)
                # Get text bounding box for centering
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (self._width - text_width) // 2
                y = (self._height - text_height) // 2

                # Draw text with black outline for visibility
                outline_color = (0, 0, 0)
                for adj_x in [-2, 0, 2]:
                    for adj_y in [-2, 0, 2]:
                        draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)
                draw.text((x, y), text, font=font, fill=(255, 255, 255))

                # Create frame
                frame = OutputImageRawFrame(
                    image=img.tobytes(), size=(self._width, self._height), format="RGB"
                )
                await self.push_frame(frame)

                self._frame_count += 1

                # Wait for next frame (30 fps)
                await asyncio.sleep(1.0 / self._fps)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error generating frame: {e}")
                await asyncio.sleep(1.0)


class AudioGeneratorProcessor(FrameProcessor):
    """Generates audio beeps continuously."""

    def __init__(self, sample_rate: int = 16000, beep_interval: float = 2.0):
        super().__init__()
        self._sample_rate = sample_rate
        self._beep_interval = beep_interval
        self._running = False
        self._task = None

    async def start(self, frame: Frame):
        """Start generating audio."""
        await super().start(frame)
        self._running = True
        self._task = asyncio.create_task(self._generate_audio())

    async def stop(self, frame: Frame):
        """Stop generating audio."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await super().stop(frame)

    def _generate_beep(self, duration: float = 0.2, frequency: float = 440.0):
        """Generate a beep sound using numpy.

        Args:
            duration: Duration of the beep in seconds
            frequency: Frequency of the beep in Hz (default: A4 = 440 Hz)

        Returns:
            bytes: WAV audio data
        """
        # Generate time array
        t = np.linspace(0, duration, int(self._sample_rate * duration))

        # Generate sine wave
        audio_signal = np.sin(2 * np.pi * frequency * t)

        # Apply fade in/out to avoid clicks
        fade_samples = int(0.01 * self._sample_rate)  # 10ms fade
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        audio_signal[:fade_samples] *= fade_in
        audio_signal[-fade_samples:] *= fade_out

        # Convert to 16-bit PCM
        audio_signal = (audio_signal * 32767).astype(np.int16)

        return audio_signal.tobytes()

    async def _generate_audio(self):
        """Generate beeps continuously."""
        while self._running:
            try:
                # Generate beep
                beep_audio = self._generate_beep()

                # Create audio frame
                frame = OutputAudioRawFrame(
                    audio=beep_audio, sample_rate=self._sample_rate, num_channels=1
                )
                await self.push_frame(frame)

                # Wait before next beep
                await asyncio.sleep(self._beep_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error generating audio: {e}")
                await asyncio.sleep(1.0)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Main bot logic that generates frames on loop."""
    logger.info("Starting load test bot")

    # Create frame generators
    video_generator = FrameGeneratorProcessor(width=640, height=480, fps=30)
    audio_generator = AudioGeneratorProcessor(sample_rate=16000, beep_interval=2.0)

    # Create pipeline
    pipeline = Pipeline([video_generator, audio_generator, transport.output()])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_out_sample_rate=16000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected - starting frame generation")

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
                audio_out_enabled=True,
                video_out_enabled=True,
                video_out_width=640,
                video_out_height=480,
            ),
        )

    elif isinstance(runner_args, SmallWebRTCRunnerArguments):
        from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

        transport = SmallWebRTCTransport(
            params=TransportParams(
                audio_out_enabled=True,
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
