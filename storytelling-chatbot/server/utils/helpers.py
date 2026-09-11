#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Helpers that load the bundled images and sound effects as output frames."""

import os
import wave

from PIL import Image
from pipecat.frames.frames import OutputAudioRawFrame, OutputImageRawFrame

script_dir = os.path.dirname(__file__)


def load_images(image_files: list[str]) -> dict[str, OutputImageRawFrame]:
    """Load PNGs from the assets folder as RGB image frames keyed by file stem."""
    images = {}
    for file in image_files:
        full_path = os.path.join(script_dir, "../assets", file)
        filename = os.path.splitext(os.path.basename(full_path))[0]
        with Image.open(full_path) as img:
            rgb = img.convert("RGB")
            images[filename] = OutputImageRawFrame(
                image=rgb.tobytes(), size=rgb.size, format=rgb.mode
            )
    return images


def load_sounds(sound_files: list[str]) -> dict[str, OutputAudioRawFrame]:
    """Load WAVs from the assets folder as audio frames keyed by file stem."""
    sounds = {}
    for file in sound_files:
        full_path = os.path.join(script_dir, "../assets", file)
        filename = os.path.splitext(os.path.basename(full_path))[0]
        with wave.open(full_path) as audio_file:
            sounds[filename] = OutputAudioRawFrame(
                audio=audio_file.readframes(-1),
                sample_rate=audio_file.getframerate(),
                num_channels=audio_file.getnchannels(),
            )
    return sounds
