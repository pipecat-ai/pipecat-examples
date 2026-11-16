"""One conclusion from the two readings: what the turn felt like, and whether it was sarcastic.

Pipecat Voice Reader hears the voice and Pipecat Tone reads the words, and neither is right alone.
The words are the stronger reader of sarcasm, but read a joke told through laughter as one. The
voice is the better reader of feeling, since plain words can be said in any mood, but its sarcasm
is a weak cue. ``conclude`` weighs the two into two more signals:

- ``feeling``: positive, neutral, sad or frustrated, with a confidence for the two likeliest.
- ``sarcasm_overall``: the chance the turn is sarcastic, from 0 to 1.

``PerceptionConclusion`` is the processor that adds them to each transcription's reading. The
weights below are a starting point, set by hand and checked against this demo's twelve clips only:
measure them on your own calls before relying on them.
"""

from pipecat.expressive.perception import (
    PerceptionCapabilities,
    PerceptionSignal,
    PerceptionTerm,
)
from pipecat.frames.frames import Frame, PerceptionMetadataFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

FEELINGS = ["positive", "neutral", "sad", "frustrated"]

#: Each of Pipecat Tone's emotions as the feeling nearest to it.
EMOTION_FEELINGS = {
    "happy": "positive",
    "amused": "positive",
    "surprised": "positive",
    "neutral": "neutral",
    "sad": "sad",
    "afraid": "sad",
    "angry": "frustrated",
    "disgusted": "frustrated",
    "contemptuous": "frustrated",
}

#: How much of the feeling comes from the voice, and how much from the words.
VOICE_FEELING_WEIGHT = 0.6
WORDS_FEELING_WEIGHT = 0.4
#: Neutral words show no strong feeling, which isn't the same as the user feeling none, so they
#: count for this much of what any other emotion in the words does.
NEUTRAL_WORDS_WEIGHT = 0.5

#: How much of the sarcasm comes from the words, and how much from the voice.
WORDS_SARCASM_WEIGHT = 0.65
VOICE_SARCASM_WEIGHT = 0.35
#: A voice flatter than this, saying bright words, is one of the mismatches the voice is trusted on.
FLAT_AROUSAL = 0.35

CAPABILITIES = PerceptionCapabilities(
    [
        PerceptionTerm(
            "feeling",
            "How the turn felt overall, weighing the user's voice with their words.",
            labels=FEELINGS,
        ),
        PerceptionTerm(
            "sarcasm_overall",
            "The chance the turn is sarcastic, from 0 to 1, weighing the words with the voice. "
            "Go by this one over the two it's made from.",
        ),
    ]
)


def conclude(reading: list[PerceptionSignal]) -> list[PerceptionSignal]:
    """Weigh a turn's voice and words readings into one conclusion.

    Args:
        reading: The turn's reading: Voice Reader's ``tone``, ``arousal``, ``laughter`` and
            ``sarcasm_voice``, and Pipecat Tone's ``emotion`` and ``sarcasm``. Either model's may
            be missing, such as the voice's of speech too short for it.

    Returns:
        The signals to add to the reading: ``feeling`` and ``sarcasm_overall``, each only when
        there is something to conclude it from.
    """
    signals = {signal.name: signal for signal in reading}
    conclusion = []
    feeling = _feeling(signals)
    if feeling:
        conclusion.append(PerceptionSignal("feeling", labels=feeling))
    sarcasm = _sarcasm(signals)
    if sarcasm is not None:
        conclusion.append(PerceptionSignal("sarcasm_overall", value=round(sarcasm, 2)))
    return conclusion


def _feeling(signals: dict[str, PerceptionSignal]) -> list[tuple[str, float]]:
    """The two likeliest feelings, likeliest first, or none without a tone or an emotion."""
    scores = dict.fromkeys(FEELINGS, 0.0)
    if "tone" in signals:
        for tone, confidence in signals["tone"].labels:
            scores[tone] += VOICE_FEELING_WEIGHT * confidence
    if "emotion" in signals:
        for emotion, confidence in signals["emotion"].labels:
            weight = NEUTRAL_WORDS_WEIGHT if emotion == "neutral" else 1.0
            scores[EMOTION_FEELINGS[emotion]] += WORDS_FEELING_WEIGHT * weight * confidence
    total = sum(scores.values())
    if not total:
        return []
    likeliest = sorted(scores.items(), key=lambda score: score[1], reverse=True)[:2]
    return [(feeling, round(score / total, 2)) for feeling, score in likeliest if score]


def _sarcasm(signals: dict[str, PerceptionSignal]) -> float | None:
    """The chance the turn is sarcastic, or None without either model's sarcasm."""
    words = _value(signals, "sarcasm")
    voice = _value(signals, "sarcasm_voice")
    if words is None or voice is None:
        # One reader alone: its own answer is all there is.
        return words if voice is None else voice

    # A joke told through laughter reads as sarcasm in the words. The more the voice laughs, the
    # less the words' sarcasm counts.
    words *= 1 - (_value(signals, "laughter") or 0.0)
    sarcasm = WORDS_SARCASM_WEIGHT * words + VOICE_SARCASM_WEIGHT * voice

    # The voice's sarcasm is weak on its own, but it's what catches bright words said flat or
    # through gritted teeth, which read sincere on the page. There it's taken at its word.
    if _is_positive(signals.get("emotion")) and _is_flat_or_frustrated(signals):
        sarcasm = max(sarcasm, voice)
    return sarcasm


def _value(signals: dict[str, PerceptionSignal], name: str) -> float | None:
    signal = signals.get(name)
    return signal.value if signal else None


def _likeliest(signal: PerceptionSignal | None) -> str | None:
    return signal.labels[0][0] if signal and signal.labels else None


def _is_positive(emotion: PerceptionSignal | None) -> bool:
    likeliest = _likeliest(emotion)
    return likeliest is not None and EMOTION_FEELINGS[likeliest] == "positive"


def _is_flat_or_frustrated(signals: dict[str, PerceptionSignal]) -> bool:
    tone = _likeliest(signals.get("tone"))
    arousal = _value(signals, "arousal")
    is_flat = tone == "neutral" and arousal is not None and arousal < FLAT_AROUSAL
    return tone == "frustrated" or is_flat


class PerceptionConclusion(FrameProcessor):
    """Adds ``conclude``'s signals to the reading of each transcription.

    Goes right after the ``PerceptionReader``. It declares its two signals with the reader's, as
    any perception producer does, so RTVI sends a transcription to the client once its reading
    has the conclusion too, and an LLM after it would be told how to read them.
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, PerceptionMetadataFrame):
            # The reader's signals, with the conclusion's.
            declared = frame.perception.merge(CAPABILITIES)
            frame = PerceptionMetadataFrame(service_name=self.name, perception=declared)
        elif isinstance(frame, TranscriptionFrame) and frame.perception:
            frame.perception = [*frame.perception, *conclude(frame.perception)]
        await self.push_frame(frame, direction)
