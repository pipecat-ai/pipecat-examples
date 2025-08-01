#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import os
import sys
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import re

import aiohttp
import numpy as np
from dotenv import load_dotenv
from loguru import logger
from PIL import Image  # For saving debug images

# OpenGL imports
try:
    import OpenGL.GL as gl
    from OpenGL.GL import *
    from OpenGL.GLU import *
except ImportError:
    logger.error("PyOpenGL not installed. Run: pip install PyOpenGL PyOpenGL_accelerate")
    sys.exit(1)

# GLFW import
try:
    import glfw
except ImportError:
    logger.error("glfw not installed. Run: pip install glfw")
    sys.exit(1)

# Live2D import - install with: pip install live2d-py
try:
    import live2d.v3 as live2d
except ImportError:
    logger.error("live2d-py not installed. Run: pip install live2d-py")
    sys.exit(1)

# Pipecat imports
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.examples.daily_runner import configure
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    OutputImageRawFrame,
    StartFrame,
    StartInterruptionFrame,
    TTSAudioRawFrame,
    TextFrame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor, FrameProcessorSetup
from pipecat.services.ai_service import AIService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

save_to_disk = False


# Define the new CharacterAnimationFrame
@dataclass
class CharacterAnimationFrame(Frame):
    """Frame containing character animation instructions"""

    expression: Optional[str] = None  # e.g., "F01.exp3.json"
    motion: Optional[str] = None  # e.g., "haru_g_m03.motion3.json"
    duration: Optional[float] = None  # Duration in seconds
    text: Optional[str] = None  # Associated text for timing


class AnimationExtractorProcessor(FrameProcessor):
    """
    Extracts animation instructions from LLM output and creates CharacterAnimationFrames.

    Expected format from LLM:
    [ANIM expression="Happy" motion="Greeting"]This is what I'm saying.[/ANIM]
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._animation_pattern = re.compile(
            r'\[ANIM\s+expression="([^"]+)"\s+motion="([^"]+)"\](.*?)\[/ANIM\]', re.DOTALL
        )
        self._collecting_response = False
        self._accumulated_text = ""
        self._pending_animations = []

        # Mapping from friendly names to actual file names
        self._expression_map = {
            "Happy": "F01.exp3.json",
            "Surprised": "F02.exp3.json",
            "Angry": "F03.exp3.json",
            "Sad": "F04.exp3.json",
            "Relaxed": "F05.exp3.json",
            "Worried": "F06.exp3.json",
            "Thinking": "F07.exp3.json",
            "Excited": "F08.exp3.json",
            "Neutral": None,  # No expression file means neutral
        }

        self._motion_map = {
            "Idle": "haru_g_idle.motion3.json",
            "Greeting": "haru_g_m01.motion3.json",
            "Nod": "haru_g_m02.motion3.json",
            "Shake": "haru_g_m03.motion3.json",
            "Thinking": "haru_g_m04.motion3.json",
            "Explaining": "haru_g_m05.motion3.json",
            "Surprise": "haru_g_m06.motion3.json",
            "Happy": "haru_g_m07.motion3.json",
            "Apologetic": "haru_g_m08.motion3.json",
            "Confident": "haru_g_m09.motion3.json",
            "Listening": "haru_g_m10.motion3.json",
            "Celebration": "haru_g_m11.motion3.json",
            "Pondering": "haru_g_m12.motion3.json",
            "Energetic": "haru_g_m13.motion3.json",
            "Casual": "haru_g_m14.motion3.json",
            "Professional": "haru_g_m15.motion3.json",
            "Encouragement": "haru_g_m16.motion3.json",
            "Concern": "haru_g_m17.motion3.json",
            "Relief": "haru_g_m18.motion3.json",
            "Curious": "haru_g_m19.motion3.json",
            "Understanding": "haru_g_m20.motion3.json",
        }

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._collecting_response = True
            self._accumulated_text = ""
            self._pending_animations = []
            await self.push_frame(frame, direction)

        elif isinstance(frame, TextFrame) and self._collecting_response:
            # Accumulate text
            self._accumulated_text += frame.text

            # Try to extract complete animation tags
            await self._process_accumulated_text(direction)

        elif isinstance(frame, LLMFullResponseEndFrame):
            # Process any remaining text
            if self._accumulated_text:
                await self._flush_remaining_text(direction)

            self._collecting_response = False
            self._accumulated_text = ""
            await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    async def _process_accumulated_text(self, direction: FrameDirection):
        """Process accumulated text to find complete animation tags"""
        # Check if we have any complete animation tags
        matches = list(self._animation_pattern.finditer(self._accumulated_text))

        if matches:
            last_end = 0

            for match in matches:
                # Push any text before this match
                if match.start() > last_end:
                    text_before = self._accumulated_text[last_end : match.start()]
                    if text_before.strip():
                        await self.push_frame(TextFrame(text=text_before), direction)

                # Extract animation info
                expression_name = match.group(1)
                motion_name = match.group(2)
                sentence = match.group(3).strip()

                # Map to actual files
                expression_file = self._expression_map.get(expression_name)
                motion_file = self._motion_map.get(motion_name, "haru_g_idle.motion3.json")

                logger.info(
                    f"Extracted animation: {expression_name}->{expression_file}, {motion_name}->{motion_file}"
                )

                # Push animation frame
                await self.push_frame(
                    CharacterAnimationFrame(
                        expression=expression_file, motion=motion_file, text=sentence
                    ),
                    direction,
                )

                # Push the cleaned sentence text
                if sentence:
                    await self.push_frame(TextFrame(text=sentence), direction)

                last_end = match.end()

            # Keep any remaining unmatched text for next time
            self._accumulated_text = self._accumulated_text[last_end:]
        else:
            # Check if we might be in the middle of a tag
            if "[ANIM" in self._accumulated_text or self._accumulated_text.count(
                "["
            ) > self._accumulated_text.count("]"):
                # We might be building up a tag, don't push anything yet
                pass
            else:
                # No tags in progress, push accumulated text
                if self._accumulated_text:
                    await self.push_frame(TextFrame(text=self._accumulated_text), direction)
                    self._accumulated_text = ""

    async def _flush_remaining_text(self, direction: FrameDirection):
        """Flush any remaining text at the end of the response"""
        if self._accumulated_text.strip():
            # Try one more time to extract animations
            cleaned_text, animations = self._extract_animations(self._accumulated_text)

            for anim in animations:
                await self.push_frame(
                    CharacterAnimationFrame(
                        expression=anim["expression"], motion=anim["motion"], text=anim["text"]
                    ),
                    direction,
                )

            if cleaned_text.strip():
                await self.push_frame(TextFrame(text=cleaned_text), direction)

    def _extract_animations(self, text: str) -> tuple[str, List[Dict[str, str]]]:
        """Extract animation tags and return cleaned text and animation list"""
        animations = []
        cleaned_text = text

        matches = list(self._animation_pattern.finditer(text))
        logger.debug(f"Found {len(matches)} animation tags in text: {text[:100]}...")

        for match in matches:
            expression_name = match.group(1)
            motion_name = match.group(2)
            sentence = match.group(3).strip()

            # Map friendly names to actual files
            expression_file = self._expression_map.get(expression_name)
            motion_file = self._motion_map.get(motion_name, "haru_g_idle.motion3.json")

            if expression_file is None and expression_name != "Neutral":
                logger.warning(f"Unknown expression: {expression_name}, using neutral")

            if motion_name not in self._motion_map:
                logger.warning(f"Unknown motion: {motion_name}, using idle")
                motion_file = "haru_g_idle.motion3.json"

            animations.append(
                {"expression": expression_file, "motion": motion_file, "text": sentence}
            )

            logger.info(
                f"Extracted animation: {expression_name}->{expression_file}, {motion_name}->{motion_file}"
            )

            # Replace the full match with just the sentence
            cleaned_text = cleaned_text.replace(match.group(0), sentence)

        return cleaned_text, animations


class SimpleLive2DRenderer:
    """
    Enhanced Live2D renderer with expression and motion support.
    """

    def __init__(self, width=640, height=480, model_path=None):
        self.width = width
        self.height = height
        self.model_path = model_path
        self.window = None
        self.model = None
        self._initialized = False
        self._current_expression = None
        self._current_motion = None
        self._motion_playing = False

        # We'll populate this after loading the model
        self._available_motions = {}
        self._available_expressions = []

    def initialize(self):
        """Initialize OpenGL context and load Live2D model"""
        if self._initialized:
            return

        # Initialize GLFW
        if not glfw.init():
            raise Exception("Failed to initialize GLFW")

        # Create hidden window (change to glfw.TRUE for debugging)
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.DOUBLEBUFFER, glfw.TRUE)

        # For macOS legacy OpenGL 2.1
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 2)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 1)

        self.window = glfw.create_window(self.width, self.height, "Live2D", None, None)
        if not self.window:
            glfw.terminate()
            raise Exception("Failed to create window")

        glfw.make_context_current(self.window)

        live2d.init()
        live2d.glewInit()

        # Set up OpenGL
        gl.glViewport(0, 0, self.width, self.height)

        # Set pixel alignment to 1 byte to avoid padding issues
        gl.glPixelStorei(gl.GL_PACK_ALIGNMENT, 1)

        # Load Live2D model
        self.model = live2d.LAppModel()
        self.model.LoadModelJson(self.model_path)
        self.model.Resize(self.width, self.height)

        # Disable auto blink and breath for manual control
        self.model.SetAutoBlinkEnable(True)
        self.model.SetAutoBreathEnable(True)

        # Start with a random idle motion
        try:

            def on_motion_finish():
                self._motion_playing = False
                logger.debug("Motion finished")

            self.model.StartRandomMotion("Idle", 3, onFinishMotionHandler=on_motion_finish)
            self._motion_playing = True
        except Exception as e:
            logger.warning(f"Could not start idle motion: {e}")

        self._initialized = True
        logger.info("Enhanced OpenGL renderer and Live2D model initialized")

    def render_frame(
        self, mouth_open: float, mouth_form: float, expression: str = None, motion: str = None
    ) -> np.ndarray:
        """Render a frame with Live2D model and return as numpy array"""
        if not self._initialized:
            self.initialize()

        # Make context current
        glfw.make_context_current(self.window)

        live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)  # Clear to transparent

        # Apply expression if provided and different from current
        if expression and expression != self._current_expression:
            try:
                # For now, we'll map expressions to random selection
                # In a full implementation, you'd need to extend the Live2D wrapper
                # to support SetExpression with a specific name
                expression_map = {
                    "F01.exp3.json": 0,  # Happy
                    "F02.exp3.json": 1,  # Surprised
                    "F03.exp3.json": 2,  # Angry
                    "F04.exp3.json": 3,  # Sad
                    "F05.exp3.json": 4,  # Relaxed
                    "F06.exp3.json": 5,  # Worried
                    "F07.exp3.json": 6,  # Thinking
                    "F08.exp3.json": 7,  # Excited
                }

                # Since the Python wrapper might not expose SetExpression(name),
                # we use SetRandomExpression as a workaround
                # You could extend the C++ wrapper to add this functionality
                self.model.SetRandomExpression()
                self._current_expression = expression
                logger.debug(f"Set expression (random): {expression}")
            except Exception as e:
                logger.debug(f"Could not set expression {expression}: {e}")

        # Apply motion if provided and different from current
        if motion and motion != self._current_motion and not self._motion_playing:
            try:

                def on_motion_start(group, index):
                    self._motion_playing = True
                    logger.debug(f"Motion started: {group}[{index}]")

                def on_motion_finish():
                    self._motion_playing = False
                    logger.debug("Motion finished")

                # Map motion names to groups
                motion_group_map = {
                    "haru_g_idle.motion3.json": "Idle",
                    "haru_g_m01.motion3.json": "TapBody",
                    "haru_g_m02.motion3.json": "TapBody",
                    "haru_g_m03.motion3.json": "TapBody",
                    "haru_g_m04.motion3.json": "TapBody",
                    "haru_g_m05.motion3.json": "TapBody",
                    "haru_g_m06.motion3.json": "TapBody",
                    "haru_g_m07.motion3.json": "TapBody",
                    "haru_g_m08.motion3.json": "TapBody",
                    "haru_g_m09.motion3.json": "TapBody",
                    "haru_g_m10.motion3.json": "TapBody",
                    "haru_g_m11.motion3.json": "TapBody",
                    "haru_g_m12.motion3.json": "TapBody",
                    "haru_g_m13.motion3.json": "TapBody",
                    "haru_g_m14.motion3.json": "TapBody",
                    "haru_g_m15.motion3.json": "Idle",
                    "haru_g_m16.motion3.json": "TapBody",
                    "haru_g_m17.motion3.json": "TapBody",
                    "haru_g_m18.motion3.json": "TapBody",
                    "haru_g_m19.motion3.json": "TapBody",
                    "haru_g_m20.motion3.json": "TapBody",
                }

                # Try to start motion based on group
                group = motion_group_map.get(motion, "TapBody")
                self.model.StartRandomMotion(
                    group,
                    3,  # priority
                    on_motion_start,
                    on_motion_finish,
                )
                self._current_motion = motion

            except Exception as e:
                logger.debug(f"Could not start motion {motion}: {e}")

        # Update Live2D model parameters for lip-sync
        self.model.SetParameterValue("ParamMouthOpenY", mouth_open)
        self.model.SetParameterValue("ParamMouthForm", mouth_form)

        # Update and draw the model
        self.model.Update()
        self.model.Draw()

        gl.glFlush()  # Ensure rendering is complete

        # Read pixels as RGB
        pixels = gl.glReadPixels(0, 0, self.width, self.height, gl.GL_RGB, gl.GL_UNSIGNED_BYTE)

        # Convert to numpy array and flip vertically
        image = np.frombuffer(pixels, dtype=np.uint8)
        image = image.reshape(self.height, self.width, 3)
        image = np.flipud(image)

        return image

    def cleanup(self):
        """Clean up resources"""
        if self.window:
            glfw.destroy_window(self.window)
        live2d.dispose()
        glfw.terminate()
        self._initialized = False


class AudioAnalyzer:
    """Analyzes audio for lip-sync parameters"""

    def __init__(self, sample_rate=24000):
        self.sample_rate = sample_rate

    def analyze_for_lipsync(self, audio_data) -> dict:
        """Analyze audio and return animation parameter values"""
        if audio_data is None or len(audio_data) == 0:
            return {"mouth_open": 0.0, "mouth_form": 0.0}

        try:
            # Convert bytes to numpy array if needed
            if isinstance(audio_data, bytes):
                audio_data = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            elif not isinstance(audio_data, np.ndarray):
                audio_data = np.array(audio_data, dtype=np.float32)

            # Ensure 1D
            if audio_data.ndim > 1:
                audio_data = audio_data.flatten()

            # Calculate RMS for mouth opening
            rms = np.sqrt(np.mean(audio_data**2))
            mouth_open = np.clip(rms * 5.0, 0.0, 1.0)

            # Simple frequency analysis for mouth shape
            mouth_form = 0.0
            if len(audio_data) >= 512:
                fft = np.abs(np.fft.rfft(audio_data[:512]))
                freqs = np.fft.rfftfreq(512, 1 / self.sample_rate)

                # Get spectral centroid
                if np.sum(fft) > 0:
                    centroid = np.sum(freqs * fft) / np.sum(fft)
                    mouth_form = np.clip((centroid - 500) / 2000, -1.0, 1.0)

            return {
                "mouth_open": float(mouth_open),
                "mouth_form": float(mouth_form),
            }

        except Exception as e:
            logger.error(f"Error analyzing audio: {e}")
            return {"mouth_open": 0.0, "mouth_form": 0.0}


class Live2DVideoService(AIService):
    """
    Enhanced Live2D Video Service with expression and motion support.
    """

    def __init__(
        self,
        *,
        model_path: str,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._model_path = model_path
        self._width = width
        self._height = height
        self._fps = fps
        self._frame_duration = 1.0 / fps

        # Renderer
        self._renderer = None
        self._use_opengl = True

        # Audio analyzer
        self._audio_analyzer = AudioAnalyzer()

        # Animation state
        self._mouth_open = 0.0
        self._mouth_form = 0.0
        self._target_mouth_open = 0.0
        self._target_mouth_form = 0.0
        self._last_update_time = 0.0

        # Current expression and motion
        self._current_expression = None
        self._current_motion = None
        self._motion_start_time = None
        self._motion_duration = 0.0

        # Animation queue
        self._animation_queue = []  # List of (expression, motion, text)

        # Lipsync queue for timing
        self._lipsync_queue = []  # List of (mouth_open, mouth_form, remaining_duration)

        # Rendering control
        self._render_task: Optional[asyncio.Task] = None
        self._video_queue = asyncio.Queue(maxsize=30)
        self._should_stop = False
        self._rendering_started = False
        self._video_push_task_handle = None

        # Frame counter
        self._frame_count = 0
        self._frames_pushed = 0

        logger.info(
            f"Enhanced Live2D Video Service initialized: {model_path} ({width}x{height}@{fps}fps)"
        )

    async def setup(self, setup: FrameProcessorSetup):
        """Setup the service"""
        await super().setup(setup)

        # Initialize renderer here (on main thread)
        try:
            self._renderer = SimpleLive2DRenderer(self._width, self._height, self._model_path)
            self._renderer.initialize()  # Call initialize on main thread
            self._use_opengl = True
            logger.info("Using OpenGL renderer - initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenGL/Live2D: {e}.")

    async def cleanup(self):
        """Clean up resources"""
        await super().cleanup()
        self._should_stop = True
        if self._render_task and not self._render_task.done():
            await self._render_task
        if hasattr(self._renderer, "cleanup"):
            self._renderer.cleanup()

    def can_generate_metrics(self) -> bool:
        return True

    async def start(self, frame: StartFrame):
        """Start the service"""
        await super().start(frame)

    async def stop(self, frame: EndFrame):
        """Stop the service"""
        await super().stop(frame)
        if self._video_push_task_handle:
            self._video_push_task_handle.cancel()
            try:
                await self._video_push_task_handle
            except asyncio.CancelledError:
                pass
        await self._stop_rendering()

    async def cancel(self, frame: CancelFrame):
        """Cancel the service"""
        await super().cancel(frame)
        if self._video_push_task_handle:
            self._video_push_task_handle.cancel()
            try:
                await self._video_push_task_handle
            except asyncio.CancelledError:
                pass
        await self._stop_rendering()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames including CharacterAnimationFrame"""
        await super().process_frame(frame, direction)

        if isinstance(frame, StartInterruptionFrame):
            # Clear queues on interruption
            while not self._video_queue.empty():
                await self._video_queue.get()
            self._animation_queue.clear()
            await self.push_frame(frame, direction)

        elif isinstance(frame, CharacterAnimationFrame):
            # Queue the animation
            await self._handle_animation_frame(frame)
            # Don't push this frame forward, it's consumed here

        elif isinstance(frame, TTSAudioRawFrame):
            # Analyze audio for lip-sync
            await self._handle_audio_frame(frame)
            await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    async def _handle_animation_frame(self, frame: CharacterAnimationFrame):
        """Handle incoming animation frame"""
        try:
            self._animation_queue.append(
                {
                    "expression": frame.expression,
                    "motion": frame.motion,
                    "text": frame.text,
                    "duration": frame.duration or 3.0,  # Default 3 seconds
                }
            )
            logger.debug(f"Queued animation: expression={frame.expression}, motion={frame.motion}")
        except Exception as e:
            logger.error(f"Error handling animation frame: {e}")

    async def _handle_audio_frame(self, frame: TTSAudioRawFrame):
        """Handle incoming audio frame and update lip-sync parameters"""
        try:
            lipsync_params = self._audio_analyzer.analyze_for_lipsync(frame.audio)
            # Calculate chunk duration (assuming s16 mono)
            chunk_duration = len(frame.audio) / (2 * 24000)  # Cartesia default sample_rate=24000
            self._lipsync_queue.append(
                (lipsync_params["mouth_open"], lipsync_params["mouth_form"], chunk_duration)
            )
            logger.debug(
                f"Queued lipsync params: mouth_open={lipsync_params['mouth_open']:.3f}, mouth_form={lipsync_params['mouth_form']:.3f}, duration={chunk_duration:.3f}s"
            )
        except Exception as e:
            logger.error(f"Error handling audio frame: {e}")

    async def _start_rendering(self):
        """Start the rendering task"""
        if not self._rendering_started:
            self._should_stop = False
            self._render_task = asyncio.create_task(self._render_loop())
            self._rendering_started = True
            logger.info("Live2D rendering started")

    async def _stop_rendering(self):
        """Stop the rendering task"""
        if self._rendering_started:
            self._should_stop = True
            if self._render_task:
                await self._render_task
            self._rendering_started = False
            logger.info("Live2D rendering stopped")

    def _update_animation(self):
        """Update current animation from queue"""
        current_time = time.time()

        # Check if current motion has expired
        if self._motion_start_time and self._motion_duration > 0:
            if current_time - self._motion_start_time > self._motion_duration:
                # Reset to idle
                self._current_motion = "haru_g_idle.motion3.json"
                self._current_expression = None
                self._motion_start_time = None
                self._motion_duration = 0
                logger.debug("Animation expired, returning to idle")

        # Apply next animation from queue if available
        if self._animation_queue and not self._motion_start_time:
            anim = self._animation_queue.pop(0)
            self._current_expression = anim["expression"]
            self._current_motion = anim["motion"]
            self._motion_start_time = current_time
            self._motion_duration = anim["duration"]
            logger.info(
                f"Starting animation: expression={self._current_expression}, motion={self._current_motion}"
            )

    async def _render_loop(self):
        """Enhanced rendering loop with animation support"""
        logger.info("Enhanced Live2D render loop started")
        try:
            while not self._should_stop:
                frame_start = time.time()

                # Update animations
                self._update_animation()

                # Consume from lipsync queue
                if self._lipsync_queue:
                    self._target_mouth_open, self._target_mouth_form, remaining = (
                        self._lipsync_queue[0]
                    )
                    remaining -= self._frame_duration
                    if remaining <= 0:
                        self._lipsync_queue.pop(0)
                        if self._lipsync_queue:
                            self._target_mouth_open, self._target_mouth_form = self._lipsync_queue[
                                0
                            ][:2]
                        else:
                            self._target_mouth_open = 0.0
                            self._target_mouth_form = 0.0
                    else:
                        self._lipsync_queue[0] = (
                            self._target_mouth_open,
                            self._target_mouth_form,
                            remaining,
                        )
                else:
                    self._target_mouth_open = 0.0
                    self._target_mouth_form = 0.0

                # Smooth animation
                smoothing = 0.5
                self._mouth_open += (self._target_mouth_open - self._mouth_open) * smoothing
                self._mouth_form += (self._target_mouth_form - self._mouth_form) * smoothing

                # Render frame with current animation
                image_data = self._renderer.render_frame(
                    self._mouth_open,
                    self._mouth_form,
                    self._current_expression,
                    self._current_motion,
                )

                # Save debug image (every 10th frame, to ./debug_frames/)
                if save_to_disk:
                    if self._frame_count % 10 == 0:
                        os.makedirs("./debug_frames", exist_ok=True)
                        img = Image.fromarray(image_data)
                        img.save(f"./debug_frames/frame_{self._frame_count:04d}.png")

                # Logging
                self._frame_count += 1
                if self._frame_count <= 3:
                    logger.info(f"Frame {self._frame_count}: rendered, shape={image_data.shape}")

                if self._frame_count % 300 == 0:
                    logger.info(
                        f"Rendered {self._frame_count} frames, current motion: {self._current_motion}"
                    )

                # Create output frame
                video_frame = OutputImageRawFrame(
                    image=image_data.tobytes(), size=(self._width, self._height), format="RGB"
                )

                # Queue frame (drop oldest if full)
                if self._video_queue.full():
                    await self._video_queue.get()
                await self._video_queue.put(video_frame)

                # Frame rate control
                elapsed = time.time() - frame_start
                sleep_time = max(0, self._frame_duration - elapsed)
                await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Error in render loop: {e}")
            import traceback

            logger.error(traceback.format_exc())

        logger.info("Enhanced Live2D render loop stopped")

    async def _video_push_task(self):
        """Consume video queue and push frames asynchronously"""
        logger.info("Video push task started")
        while not self._should_stop:
            try:
                video_frame = await self._video_queue.get()
                await self.push_frame(video_frame)
                self._frames_pushed += 1
                if self._frames_pushed % 30 == 0:
                    logger.debug(f"Pushed {self._frames_pushed} video frames")
            except Exception as e:
                logger.error(f"Error in video push task: {e}")
                await asyncio.sleep(0.1)
        logger.info("Video push task stopped")


async def main():
    async with aiohttp.ClientSession() as session:
        (room_url, token) = await configure(session)

        transport = DailyTransport(
            room_url,
            token,
            "Live2D Avatar Bot",
            DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                video_out_enabled=True,
                video_out_is_live=True,
                video_out_width=640,
                video_out_height=480,
                transcription_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )

        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",
        )

        llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o")

        model_path = os.getenv("LIVE2D_MODEL_PATH", "./models/Haru/Haru.model3.json")
        live2d_video = Live2DVideoService(model_path=model_path, width=640, height=480, fps=30)

        # Create the animation extractor
        animation_extractor = AnimationExtractorProcessor()

        # Enhanced system prompt with animation instructions
        messages = [
            {
                "role": "system",
                "content": """You are a helpful AI assistant with a Live2D avatar. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio and your avatar will lip-sync to match.

IMPORTANT: For each sentence or thought you express, you MUST wrap it with animation tags in this exact format:
[ANIM expression="EXPRESSION" motion="MOTION"]Your sentence here.[/ANIM]

Available expressions:
- Happy - for joy, smiling, positive emotions
- Surprised - for shock, amazement, unexpected things
- Angry - for frustration, annoyance
- Sad - for disappointment, sorrow
- Relaxed - for calm, content feelings
- Worried - for concern, anxiety
- Thinking - for pondering, considering
- Excited - for enthusiasm, high energy
- Neutral - for neutral expressions

Available motions:
- Idle - neutral standing pose
- Greeting - wave hello
- Nod - agreeing, yes
- Shake - disagreeing, no
- Thinking - hand to chin, pondering
- Explaining - gesturing while talking
- Surprise - surprise reaction
- Happy - joyful gesture
- Apologetic - humble, sorry gesture
- Confident - confident pose
- Listening - attentive pose
- Celebration - celebratory gesture
- Pondering - deep thought
- Energetic - high energy movement
- Casual - relaxed gesture
- Professional - formal stance
- Encouragement - supportive gesture
- Concern - worried gesture
- Relief - relieved gesture
- Curious - interested pose
- Understanding - comprehending nod

Examples:
- [ANIM expression="Happy" motion="Greeting"]Hello there, nice to meet you![/ANIM]
- [ANIM expression="Thinking" motion="Pondering"]Let me think about that for a moment...[/ANIM]
- [ANIM expression="Excited" motion="Celebration"]That's absolutely fantastic news![/ANIM]
- [ANIM expression="Worried" motion="Concern"]I'm a bit concerned about that issue.[/ANIM]

Remember: EVERY sentence must be wrapped in [ANIM] tags with appropriate expression and motion!""",
            },
        ]

        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)

        pipeline = Pipeline(
            [
                transport.input(),
                context_aggregator.user(),
                llm,
                animation_extractor,  # Extract animations before TTS
                tts,
                live2d_video,
                transport.output(),
                context_aggregator.assistant(),
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            await transport.capture_participant_transcription(participant["id"])

            # Start video rendering after joining
            await live2d_video._start_rendering()
            live2d_video._video_push_task_handle = asyncio.create_task(
                live2d_video._video_push_task()
            )

            messages.append(
                {
                    "role": "system",
                    "content": "Please introduce yourself to the user as an AI assistant with a Live2D avatar. Remember to use [ANIM] tags for each sentence with appropriate expressions and motions!",
                }
            )
            await task.queue_frames([context_aggregator.user().get_context_frame()])

        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            await task.cancel()

        runner = PipelineRunner()

        try:
            await runner.run(task)
        except KeyboardInterrupt:
            logger.info("Shutting down...")


if __name__ == "__main__":
    required_vars = ["CARTESIA_API_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        sys.exit(1)

    asyncio.run(main())
