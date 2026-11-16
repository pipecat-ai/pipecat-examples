import type {
  PipecatMetricsData,
  UserInputData,
  UserPerceptionSignal,
} from "@pipecat-ai/client-js";
import { create } from "zustand";

import { MODEL_INFO, OVERALL, signalsOf } from "@/lib/perception";
import {
  type ClipInfo,
  isServerMessage,
  type Model,
  MODELS,
  type ServerMessage,
} from "@/types/perception";

/** What the pipeline is doing with the audio it hears: nothing, hearing a turn, or reading the turn just heard. */
export type Phase = "idle" | "hearing" | "reading";

/** What one model made of the turn on show. */
export interface Reading {
  signals: UserPerceptionSignal[];
  /** How long after the turn stopped it reached the page, in milliseconds. */
  arrivedMs: number;
}

type PerModel<Value> = Record<Model, Value>;

function perModel<Value>(value: (model: Model) => Value): PerModel<Value> {
  return { voice: value("voice"), words: value("words") };
}

interface PerceptionState {
  /** The clips the bot can play, once it has said. */
  clips: ClipInfo[];
  phase: Phase;
  /** How many turns the user has started. */
  turn: number;
  /** The clip being played, if any. */
  activeClipId: string | null;
  /** The clip played last, which the next one follows. */
  lastClipId: string | null;
  /** How many clips have been started, so each one's progress ring starts afresh. */
  clipCount: number;
  /** Whether Play is running through the clips, one after another. */
  isCycling: boolean;
  /** Where the turn on show came from: a clip's id, null for the microphone, undefined before any turn. */
  turnClipId: string | null | undefined;
  /** When the turn on show stopped, on the page's clock, or null while it is heard. */
  stoppedAt: number | null;
  /** How many readings have arrived, so the page can tell a new one from the last. */
  readingCount: number;
  /** What each model made of the turn on show, once its reading is in. */
  readings: PerModel<Reading | null>;
  /** What the bot concluded from both readings of the turn on show, once it's in. */
  overall: UserPerceptionSignal[] | null;
  /** How long each model took over its read of the turn on show, in milliseconds, as the bot measured it. */
  readMs: PerModel<number | null>;
  /** The models that gave no reading of the turn on show. */
  missed: PerModel<boolean>;
  /** The turn's words, as transcribed. */
  words: string;
  /** Why a session couldn't be started. */
  connectionError: string | null;

  /** One of the demo's own messages arrived. */
  receive: (data: unknown) => void;
  /** The user, or a clip in their place, started speaking. */
  turnStarted: () => void;
  /** They stopped: the turn is being read. */
  turnStopped: () => void;
  /** Words of the user's arrived, with the reading of how they were said. */
  heard: (input: UserInputData) => void;
  /** The bot reported how long its services took. */
  measured: (metrics: PipecatMetricsData) => void;
  /** The readings still awaited never came. */
  readingTimedOut: () => void;
  setCycling: (isCycling: boolean) => void;
  setConnectionError: (error: string | null) => void;
  sessionEnded: () => void;
}

function apply(
  state: PerceptionState,
  message: ServerMessage,
): Partial<PerceptionState> {
  switch (message.type) {
    case "clips":
      return { clips: message.clips };
    case "clip-started":
      return {
        activeClipId: message.clipId,
        lastClipId: message.clipId,
        clipCount: state.clipCount + 1,
      };
    case "clip-finished":
      return state.activeClipId === message.clipId
        ? { activeClipId: null }
        : {};
  }
}

export const usePerceptionStore = create<PerceptionState>()((set) => ({
  clips: [],
  phase: "idle",
  turn: 0,
  activeClipId: null,
  lastClipId: null,
  clipCount: 0,
  isCycling: false,
  turnClipId: undefined,
  stoppedAt: null,
  readingCount: 0,
  readings: perModel(() => null),
  overall: null,
  readMs: perModel(() => null),
  missed: perModel(() => false),
  words: "",
  connectionError: null,

  receive: (data) => {
    if (isServerMessage(data)) {
      set((state) => apply(state, data));
    }
  },
  // A new turn: the last one's readings make way for it.
  turnStarted: () =>
    set((state) => ({
      phase: "hearing",
      turn: state.turn + 1,
      turnClipId: state.activeClipId,
      stoppedAt: null,
      readings: perModel(() => null),
      overall: null,
      readMs: perModel(() => null),
      missed: perModel(() => false),
      words: "",
    })),
  turnStopped: () =>
    set((state) =>
      state.phase === "hearing"
        ? { phase: "reading", stoppedAt: performance.now() }
        : {},
    ),
  heard: (input) => {
    if (input.input_type !== "transcription" || !input.final) return;
    set((state) => {
      // Words that arrive once the next turn has started are of the turn before it.
      if (state.phase === "hearing" || state.stoppedAt === null) return {};
      // The bot sends a turn's words on once its reader has read them, so the reading comes with
      // them. A model with no signals in it gave none: Voice Reader, of speech too short for it.
      const arrivedMs = performance.now() - state.stoppedAt;
      const readings = perModel((model) => {
        const signals = signalsOf(input.perception, model);
        if (!signals.length) return null;
        // A turn's later words carry its reading again: it landed when the first did.
        return {
          signals,
          arrivedMs: state.readings[model]?.arrivedMs ?? arrivedMs,
        };
      });
      const overall = (input.perception ?? []).filter(
        (signal) =>
          signal.name === OVERALL.feeling || signal.name === OVERALL.sarcasm,
      );
      return {
        phase: "idle",
        words: `${state.words} ${input.text}`.trim(),
        readings,
        overall: overall.length ? overall : null,
        missed: perModel((model) => !readings[model]),
        readingCount: state.readingCount + 1,
      };
    });
  },
  measured: (metrics) => {
    // Each classifier's processing time is how long its read took. Other services report theirs
    // too. Tone Reader's can come while the turn is still heard: the words are often final
    // before the VAD is sure the speech has stopped.
    set((state) => {
      const readMs = { ...state.readMs };
      for (const metric of metrics.processing ?? []) {
        const model = MODELS.find((candidate) =>
          metric.processor.startsWith(MODEL_INFO[candidate].processor),
        );
        if (model) readMs[model] = metric.value * 1000;
      }
      return { readMs };
    });
  },
  readingTimedOut: () =>
    set((state) =>
      state.phase === "reading"
        ? {
            phase: "idle",
            missed: perModel((model) => !state.readings[model]),
          }
        : {},
    ),
  setCycling: (isCycling) => set({ isCycling }),
  setConnectionError: (connectionError) => set({ connectionError }),
  // The last readings stay on the page after a session ends; only what was live is cleared.
  sessionEnded: () =>
    set((state) => ({
      phase: "idle",
      activeClipId: null,
      isCycling: false,
      missed: perModel(
        (model) => !state.readings[model] && state.stoppedAt !== null,
      ),
    })),
}));
