import type {
  UserPerceptionLabel,
  UserPerceptionSignal,
} from "@pipecat-ai/client-js";

import type { Model } from "@/types/perception";

/** The four colours a reading can take, which are Voice Reader's tones of voice. */
export const TONES = ["positive", "neutral", "sad", "frustrated"] as const;
export type Tone = (typeof TONES)[number];

export interface Measure {
  name: string;
  title: string;
  /** The top of its scale. A scale that tops out at 1 is shown as a percentage. */
  max: number;
  unit?: string;
}

/**
 * One model's side of the page, laid out from the signals Pipecat's source
 * for it reports (`PipecatVoiceSource` and `PipecatToneSource`), by name.
 */
export interface ModelInfo {
  title: string;
  /** What it reads. */
  reads: string;
  /** Its classifier, as the bot's metrics name it. */
  processor: string;
  /** The signal whose labels are its headline and panels, and what the page calls it. */
  feeling: { name: string; title: string };
  /** The signal the sincerity badge is decided from. */
  sarcasm: string;
  /** The measured signals shown as gauges, in the order they're shown. */
  measures: readonly Measure[];
}

export const MODEL_INFO: Record<Model, ModelInfo> = {
  voice: {
    title: "Voice Reader",
    reads: "Hears the voice",
    processor: "PipecatVoiceClassifier",
    feeling: { name: "tone", title: "Tone" },
    sarcasm: "sarcasm_voice",
    measures: [
      { name: "sarcasm_voice", title: "Sarcasm", max: 1 },
      { name: "laughter", title: "Laughter", max: 1 },
      { name: "arousal", title: "Energy", max: 1 },
      { name: "speech_rate", title: "Pace", max: 9, unit: "syl/s" },
    ],
  },
  words: {
    title: "Tone Reader",
    reads: "Reads the words",
    processor: "PipecatToneClassifier",
    feeling: { name: "emotion", title: "Emotion" },
    sarcasm: "sarcasm",
    measures: [{ name: "sarcasm", title: "Sarcasm", max: 1 }],
  },
};

/**
 * The conclusion the bot weighs the two readings into (server/conclusion.py):
 * the turn's feeling, one of the four tones, and its sarcasm.
 */
export const OVERALL = { feeling: "feeling", sarcasm: "sarcasm_overall" };

/** The sarcasm from which a turn counts as sarcastic rather than sincere: likelier than not. */
export const SARCASM_THRESHOLD = 0.5;

/** The top of the latency bars' scale, in milliseconds. Both models run beside the bot. */
export const LATENCY_SCALE_MS = 250;

/** The colour each of Tone Reader's emotions is shown in: the tone of voice nearest to it. */
const EMOTION_TONES: Record<string, Tone> = {
  happy: "positive",
  amused: "positive",
  surprised: "positive",
  neutral: "neutral",
  sad: "sad",
  afraid: "sad",
  angry: "frustrated",
  disgusted: "frustrated",
  contemptuous: "frustrated",
};

/** The colour a label is shown in, whichever model it's from, or undefined for one the page doesn't know. */
export function toneOf(label: string | undefined): Tone | undefined {
  if (label === undefined) return undefined;
  return TONES.find((tone) => tone === label) ?? EMOTION_TONES[label];
}

/** The signals of a reading that are one model's. */
export function signalsOf(
  perception: UserPerceptionSignal[] | undefined,
  model: Model,
): UserPerceptionSignal[] {
  const { feeling, measures } = MODEL_INFO[model];
  const names = [feeling.name, ...measures.map((measure) => measure.name)];
  return (perception ?? []).filter((signal) => names.includes(signal.name));
}

/** A signal's labels in a reading, likeliest first, or undefined if it has none. */
export function labelsOf(
  signals: UserPerceptionSignal[] | undefined,
  name: string,
): UserPerceptionLabel[] | undefined {
  const signal = signals?.find((candidate) => candidate.name === name);
  return signal?.labels.length ? signal.labels : undefined;
}

/** A model's likeliest labels in its reading, likeliest first, or undefined if it has none. */
export function feelingsOf(
  signals: UserPerceptionSignal[] | undefined,
  model: Model,
): UserPerceptionLabel[] | undefined {
  return labelsOf(signals, MODEL_INFO[model].feeling.name);
}

const PERCENT = "%";

/** A measured signal's value in a reading, or undefined if it has none. */
export function valueOf(
  signals: UserPerceptionSignal[] | undefined,
  name: string,
): number | undefined {
  return (
    signals?.find((candidate) => candidate.name === name)?.value ?? undefined
  );
}

/** A value as the page shows it: its figure, its unit, and how much of its bar it fills. */
export interface Figure {
  text: string;
  unit: string;
  fraction: number;
}

/** The unit a measure is shown in: a scale that tops out at 1 is a percentage. */
export function unitOf(measure: Measure): string {
  return measure.max === 1 ? PERCENT : (measure.unit ?? "");
}

export function figureFor(measure: Measure, value: number): Figure {
  const fraction = Math.min(Math.max(value / measure.max, 0), 1);
  const text =
    measure.max === 1 ? String(Math.round(fraction * 100)) : value.toFixed(1);
  return { text, unit: unitOf(measure), fraction };
}

export function percent(confidence: number): string {
  return `${Math.round(confidence * 100)}${PERCENT}`;
}

/** Whether a turn was meant, as a model heard it. */
export type Sincerity = "sincere" | "sarcastic";

export interface SincerityReading {
  sincerity: Sincerity;
  /** The chance the model gave that the turn is sarcastic, from 0 to 1. */
  sarcasm: number;
}

/** Whether a sarcasm signal has its turn as meant, or undefined if the reading doesn't have it. */
export function sincerityOf(
  signals: UserPerceptionSignal[] | undefined,
  name: string,
): SincerityReading | undefined {
  const sarcasm = valueOf(signals, name);
  if (sarcasm === undefined) return undefined;
  return {
    sincerity: sarcasm >= SARCASM_THRESHOLD ? "sarcastic" : "sincere",
    sarcasm,
  };
}
