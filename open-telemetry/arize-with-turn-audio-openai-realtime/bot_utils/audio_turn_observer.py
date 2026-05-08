#
# Copyright (c) 2024-2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Turn-tracking observers tuned for OpenAI Realtime.

Pipecat's default `OpenInferenceObserver` (via `TurnTrackingObserver`) defines
a turn as `(user-utterance, bot-reply)` and uses VAD-driven
`UserStartedSpeakingFrame` / `BotStoppedSpeakingFrame` to mark boundaries.
That model breaks against OpenAI's Realtime API:

1. **Interruption broadcast at end-of-response.** When OpenAI Realtime
   finishes generating a bot response, `OpenAIRealtimeLLMService` calls
   `broadcast_interruption`, which propagates a `UserStartedSpeakingFrame`
   even though no user has actually spoken. The default observer reads
   that as "user interrupting bot", ends the current turn, and starts a
   new one. Result: every audio attribute lands on a turn span that's
   off by one.

2. **Premature turn 1 from `StartFrame` + service-frame auto-start.**
   `TurnTrackingObserver` auto-starts turn 1 on `StartFrame`, before the
   bot has produced any audio.

This module provides two observer classes that fix both issues. They share
the same boundary mechanism — turn ENDS when the bot starts speaking
*again* after having spoken in the current turn — but pair user/bot audio
into turns in two different ways:

### `AudioTurnObserver` (recommended; matches Pipecat convention)

Each turn = `(user audio + bot audio)`, in chronological order.

- For user-speaks-first: turn 1 = (user 1 + bot 1), turn 2 = (user 2 + bot 2), …
- For bot-speaks-first: turn 1 = (— + bot 1), turn 2 = (user 1 + bot 2), …

### `BotFirstTurnObserver` (alternate)

Each turn = `(bot audio + user response to that bot)`. Best for
bot-speaks-first conversations anchored to bot utterances.

### Pre-padding (only on interruption)

Both observers maintain a rolling buffer of the last
`_pre_pad_seconds_on_interrupt` seconds of input audio at all times.
That buffer is prepended to the per-turn user buffer **only when the
upcoming `BotStoppedSpeakingFrame` is the result of an interruption** —
i.e. the user cut off the bot mid-utterance, so user speech started
during the bot's audio and would otherwise be clipped.

When the user instead waits politely for the bot to finish, the
`BotStoppedSpeakingFrame` is a "natural stop" (no preceding
`InterruptionFrame`), and recording flips on with an empty buffer.
User speech is captured cleanly from when they actually start speaking.

Detection: `FrameProcessor.broadcast_interruption()` (called by
`OpenAIRealtimeLLMService` when the user interrupts) emits a
`InterruptionFrame` downstream. We track its arrival between
`BotStartedSpeakingFrame` and `BotStoppedSpeakingFrame` to flag the
upcoming bot-stop as interrupted.

### Silent-buffer suppression by byte threshold

A buffer is uploaded only if its byte count exceeds a threshold that
accounts for whether pre-pad was prepended. Without pre-pad: threshold
= `_min_user_audio_bytes` (~250ms). With pre-pad: threshold =
pre_pad_bytes + `_min_user_audio_bytes` (so a buffer containing only
pre-pad and no real speech is filtered out).

### Trailing user audio after the last bot reply

If the conversation ends after a bot reply with the user still speaking
(no further bot reply to anchor a new turn), `AudioTurnObserver`
opens a half-turn at end-of-pipeline and attaches the trailing user
audio to it — rather than overwriting the previous turn's user URL.
`BotFirstTurnObserver` does not need this.

### Why user audio lives in the observer, not an `AudioBufferProcessor`

A sibling `AudioBufferProcessor` sees frames *after* the observer has
already advanced the turn (observers are notified before the next
processor in the pipeline), so user audio would attach to the wrong
turn span.

Bot audio is still captured by an external `AudioBufferProcessor`
because turn boundaries are next-bot-start (not bot-stop), so the bot
audio handler reads `_turn_count` while the turn is still active.

### Wiring

```python
oi_observer.__class__ = AudioTurnObserver
oi_observer.audio_uploader = AudioTurnUploader(...)
```

These observers are tuned for OpenAI Realtime's specific frame patterns.
Other speech-to-speech services emit different signals and need their
own observer tuning.
"""

from openinference.instrumentation.pipecat._observer import OpenInferenceObserver
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    InputAudioRawFrame,
    InterruptionFrame,
)
from pipecat.observers.base_observer import FramePushed


class _AudioTurnObserverBase(OpenInferenceObserver):
    """Shared base class for the two turn-pairing strategies.

    Subclasses parameterize via two class attributes:
    - ``_initial_user_audio_recording``: whether to start recording user
      audio before the first bot utterance.
    - ``_flush_before_end_start``: whether to flush user audio onto the
      OLD turn (True, bot-first) or the NEW turn (False, user-first).
    """

    # Set externally after the __class__ swap, e.g.
    #   oi_observer.audio_uploader = AudioTurnUploader(...)
    audio_uploader = None

    # Strategy parameters (override in subclasses).
    _initial_user_audio_recording: bool = False
    _flush_before_end_start: bool = True

    # When the user interrupts the bot mid-utterance, prepend this many
    # seconds of audio that was captured BEFORE bot-stop (rolling buffer)
    # so the user's overlapping speech isn't clipped. Only applied on
    # interrupted bot-stops; natural stops record from the bot-stop boundary
    # forward (no pre-pad clutter). 3.0s is a reasonable default — long
    # enough to capture multi-word interrupting utterances; tune higher if
    # users tend to ramble before interrupting.
    _pre_pad_seconds_on_interrupt: float = 3.0

    # Skip flush if buffer has fewer bytes than this. Belt-and-suspenders
    # against very brief flickers / mic noise.
    _min_user_audio_bytes: int = 8000

    def _ensure_user_audio_state(self) -> None:
        """Lazy-init user audio state.

        We can't override ``__init__`` cleanly because this class is installed
        via ``__class__`` swap on an already-constructed
        ``OpenInferenceObserver`` instance.
        """
        if not hasattr(self, "_user_audio_buffer"):
            self._user_audio_buffer = bytearray()
            # Always-accumulating rolling buffer trimmed to the last
            # _pre_pad_seconds_on_interrupt of audio. Prepended to the
            # per-turn buffer ONLY on interrupted bot-stops.
            self._user_audio_rolling = bytearray()
            self._user_audio_sample_rate = 16000
            self._user_audio_num_channels = 1
            self._user_audio_recording = self._initial_user_audio_recording
            # True when the per-turn buffer was seeded with pre-pad bytes.
            # Used by `_flush_user_audio` to compute a higher byte threshold
            # so that a buffer containing ONLY pre-pad (no real speech) gets
            # filtered out.
            self._buffer_has_pre_pad = False
            # Set when InterruptionFrame arrives during a bot-speaking
            # window. Reset on the next BotStartedSpeakingFrame. Used at
            # BotStoppedSpeakingFrame to decide whether to prepend pre-pad.
            self._interruption_pending = False

    async def on_push_frame(self, data: FramePushed) -> None:
        self._ensure_user_audio_state()

        if data.frame.id not in self._processed_frames:
            self._processed_frames.add(data.frame.id)
            self._frame_history.append(data.frame.id)
            if len(self._processed_frames) > len(self._frame_history):
                self._processed_frames = set(self._frame_history)

            if isinstance(data.frame, InputAudioRawFrame):
                # Always append to rolling buffer (for pre-padding on
                # interrupted bot-stops).
                self._user_audio_rolling.extend(data.frame.audio)
                self._user_audio_sample_rate = data.frame.sample_rate
                self._user_audio_num_channels = data.frame.num_channels
                max_rolling = int(
                    data.frame.sample_rate
                    * data.frame.num_channels
                    * 2  # 16-bit PCM
                    * self._pre_pad_seconds_on_interrupt
                )
                if len(self._user_audio_rolling) > max_rolling:
                    excess = len(self._user_audio_rolling) - max_rolling
                    del self._user_audio_rolling[:excess]

                if self._user_audio_recording:
                    self._user_audio_buffer.extend(data.frame.audio)
            elif isinstance(data.frame, InterruptionFrame):
                # broadcast_interruption() emits this just before the bot
                # is stopped due to user interruption. Flag so the next
                # BotStoppedSpeakingFrame uses pre-pad.
                self._interruption_pending = True
            elif isinstance(data.frame, BotStartedSpeakingFrame):
                # State-based dedup: only react to the False→True transition.
                if not self._is_bot_speaking:
                    self._user_audio_recording = False

                    if self._flush_before_end_start:
                        # Bot-first pairing: flush onto OLD turn.
                        self._flush_user_audio()

                    if self._is_turn_active and self._has_bot_spoken:
                        await self._end_turn(data, was_interrupted=False)
                        await self._start_turn(data)
                    elif not self._is_turn_active:
                        await self._start_turn(data)
                    # else: adopt auto-started turn.

                    if not self._flush_before_end_start:
                        # User-first pairing: flush onto NEW turn.
                        self._flush_user_audio()

                    self._is_bot_speaking = True
                    self._has_bot_spoken = True
                    # Reset interruption flag for this new bot-speaking window.
                    self._interruption_pending = False
            elif isinstance(data.frame, BotStoppedSpeakingFrame):
                if self._is_bot_speaking:
                    self._is_bot_speaking = False
                    if self._interruption_pending:
                        # User cut the bot off — prepend rolling pre-pad so
                        # their overlapping speech is captured.
                        self._user_audio_buffer = bytearray(self._user_audio_rolling)
                        self._buffer_has_pre_pad = True
                    else:
                        # Natural stop — start with empty buffer so user's
                        # clean speech (after they wait for bot to finish)
                        # has no pre-roll bot tail.
                        self._user_audio_buffer = bytearray()
                        self._buffer_has_pre_pad = False
                    self._user_audio_recording = True
                    self._interruption_pending = False
            elif isinstance(data.frame, (EndFrame, CancelFrame)):
                if self._is_turn_active:
                    self._user_audio_recording = False
                    has_trailing_audio = (
                        len(self._user_audio_buffer) >= self._flush_threshold_bytes()
                    )
                    if (
                        not self._flush_before_end_start
                        and has_trailing_audio
                        and self._has_bot_spoken
                    ):
                        # User-first pairing with trailing user audio after
                        # the last bot reply: open a new half-turn for it
                        # rather than overwriting the current turn's user URL.
                        await self._end_turn(data, was_interrupted=False)
                        await self._start_turn(data)
                        self._flush_user_audio()
                        await self._end_turn(data, was_interrupted=True)
                    else:
                        # Bot-first pairing (current turn correctly takes the
                        # user response), or no trailing speech at all.
                        self._flush_user_audio()
                        await self._end_turn(data, was_interrupted=True)
            # Deliberately ignore: StartFrame, UserStartedSpeakingFrame,
            # UserStoppedSpeakingFrame.

        await super().on_push_frame(data)

    def _flush_threshold_bytes(self) -> int:
        """Minimum byte count to consider the buffer non-silent.

        If pre-pad was prepended (interrupted bot-stop), buffer always
        has pre_pad bytes — so the threshold accounts for that and adds
        `_min_user_audio_bytes` of real speech on top. Without pre-pad
        (natural bot-stop, or initial pipeline-start window in user-first),
        the threshold is just `_min_user_audio_bytes`.
        """
        extra = self._pre_pad_bytes() if self._buffer_has_pre_pad else 0
        return extra + self._min_user_audio_bytes

    def _pre_pad_bytes(self) -> int:
        return int(
            self._user_audio_sample_rate
            * self._user_audio_num_channels
            * 2  # 16-bit PCM
            * self._pre_pad_seconds_on_interrupt
        )

    def _flush_user_audio(self) -> None:
        """Upload buffered user audio and stamp the URL on the current span.

        Skips upload when:
          - buffer is below `_flush_threshold_bytes()` (silent or pre-pad-only), OR
          - no uploader/span configured.
        Buffer is reset in all cases so the next window starts clean.
        """
        threshold = self._flush_threshold_bytes()
        if (
            len(self._user_audio_buffer) < threshold
            or self.audio_uploader is None
            or self._turn_span is None
        ):
            self._user_audio_buffer = bytearray()
            self._buffer_has_pre_pad = False
            return

        audio_bytes = bytes(self._user_audio_buffer)
        url = self.audio_uploader.get_presigned_url_and_upload(
            audio_bytes,
            self._user_audio_sample_rate,
            self._user_audio_num_channels,
            self._turn_count,
            role="user",
        )
        self._turn_span.set_attribute("audio.user.url", url)
        self._user_audio_buffer = bytearray()
        self._buffer_has_pre_pad = False

    # Neutralize parent dispatchers in case anything else routes through them.
    async def _handle_user_started_speaking(self, data: FramePushed) -> None:
        return

    async def _handle_bot_stopped_speaking(self, data: FramePushed) -> None:
        # Clear the speaking flag; do NOT schedule turn end. The next
        # BotStartedSpeakingFrame is what closes the current turn.
        self._is_bot_speaking = False


class AudioTurnObserver(_AudioTurnObserverBase):
    """User-then-bot turn pairing (matches Pipecat convention).

    Each turn span carries ``(user audio + bot audio)``, with user audio
    being the audio captured BEFORE the bot's reply in that turn. Works
    for both bot-speaks-first and user-speaks-first conversations:

    - Bot-first kickoff: turn 1 has only bot audio (no user — VAD
      filtering suppresses silent pre-bot capture); subsequent turns
      pair the user's response to the previous bot utterance with the
      current bot utterance.
    - User-first kickoff: turn 1 = (user 1 + bot 1), turn 2 = (user 2 + bot 2), …
    - Trailing user audio after the last bot reply (user keeps talking
      then disconnects) opens a final half-turn rather than overwriting
      the previous turn's user URL.
    """

    _initial_user_audio_recording = True
    _flush_before_end_start = False


class BotFirstTurnObserver(_AudioTurnObserverBase):
    """Bot-then-user turn pairing (alternate strategy).

    Each turn span carries ``(bot audio + user response to that bot)``.
    Best suited for bot-speaks-first conversations where you want each
    turn anchored to a bot utterance and its user response. Trailing
    user audio after the last bot reply attaches to the current
    (still-open) turn naturally — no half-turn needed.
    """

    _initial_user_audio_recording = False
    _flush_before_end_start = True


