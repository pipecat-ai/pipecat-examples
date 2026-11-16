// <Pill>: the glass pill as a React component. It owns a canvas and an
// engine for as long as it is mounted, and keeps the engine in step with its
// props. Sizes itself to its box: give it a size with className, style or
// `size`; with none of those it is a square as wide as its container.
import {
  forwardRef, useEffect, useImperativeHandle, useRef, useState,
  type CSSProperties, type HTMLAttributes, type ReactNode,
} from 'react';
import { createPillEngine, type PillEngine, type PillStats } from './engine';
import type { Mood } from './mood';
import type { MotionMode, MotionState } from './motion';
import { defaultSettings, type Light, type PillSettings } from './settings';

/**
 * The voice the pill follows: an audio stream or track you already have (a
 * call participant, a bot's voice, a microphone you opened), 'microphone' to
 * have the pill open the microphone itself, 'demo' for a stand-in voice, or
 * null for none.
 */
export type PillAudio = MediaStream | MediaStreamTrack | 'microphone' | 'demo' | null;

export type PillProps = Omit<HTMLAttributes<HTMLDivElement>, 'children' | 'onError'> & {
  /** The sentiment it shows. Default 'neutral'. */
  mood?: Mood;
  /**
   * How it carries itself. 'auto' (the default) listens while there is a
   * voice, idles for a few seconds afterwards, then comes to rest; or hold it
   * in 'idle', 'listening', 'spinning' or 'rest'.
   */
  motion?: MotionMode;
  /** The voice it follows; see PillAudio. Default none. */
  audio?: PillAudio;
  /**
   * Loudness, 0..1, if your app already measures it; takes the place of
   * `audio`. For values that change every frame, prefer the ref's setLevel().
   */
  level?: number;
  /**
   * Let the pointer take hold of the pill and turn it, and have the pill lean
   * towards the pointer as it moves about the page. Default true.
   */
  interactive?: boolean;
  /** Hold everything as it is. Default false. */
  paused?: boolean;
  /**
   * Draw onto a see-through canvas, so the page shows where the pill is
   * dark. Meant for dark backgrounds. Default true.
   */
  transparent?: boolean;
  /** Make an entrance when it mounts. Default true. */
  intro?: boolean;
  /** Width and height, as a number of pixels or any CSS length. */
  size?: number | string;
  /** Changes to the look and feel; see PillSettings. */
  settings?: Partial<PillSettings>;
  /** The studio lights, if not the standard set. Read once, when it mounts. */
  lights?: readonly Light[];
  /** Shown instead if the browser can't run the pill (no WebGL 2). */
  fallback?: ReactNode;
  onStateChange?: (state: MotionState) => void;
  /** The engine is up. Handy for anything the props don't cover. */
  onReady?: (engine: PillEngine) => void;
  /** The pill couldn't start, or couldn't open the microphone. */
  onError?: (error: Error) => void;
};

export type PillHandle = {
  /** One bright ripple from the core, with a shiver: to mark a moment. */
  pulse(strength?: number): void;
  /** Bring it back to rest from wherever it has been turned or thrown. */
  reset(): void;
  /** Keep it from going to rest just yet. */
  wake(): void;
  /** Make its entrance again. */
  appear(): void;
  /** Loudness, 0..1, from your own measurement. Cheap to call every frame. */
  setLevel(level: number): void;
  getStats(): PillStats | null;
  /** The engine itself, once it is up. */
  readonly engine: PillEngine | null;
};

const toError = (e: unknown) => (e instanceof Error ? e : new Error(String(e)));

export const Pill = forwardRef<PillHandle, PillProps>(function Pill(
  {
    mood = 'neutral', motion = 'auto', audio = null, level, interactive = true, paused = false,
    transparent = true, intro = true, size, settings, lights, fallback = null,
    onStateChange, onReady, onError, className, style, 'aria-label': label = 'Voice indicator', ...rest
  },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<PillEngine | null>(null);
  const [failure, setFailure] = useState<Error | null>(null);

  // The latest callbacks and start-up props, without restarting the engine
  // when they change.
  const latest = useRef({ mood, motion, interactive, intro, settings, lights, onStateChange, onReady, onError });
  latest.current = { mood, motion, interactive, intro, settings, lights, onStateChange, onReady, onError };
  const applied = useRef<Partial<PillSettings>>({});

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const now = latest.current;
    let engine: PillEngine;
    try {
      engine = createPillEngine(canvas, {
        mood: now.mood,
        motion: now.motion,
        interactive: now.interactive,
        intro: now.intro,
        transparent,
        settings: now.settings,
        lights: now.lights,
        onStateChange: (state) => latest.current.onStateChange?.(state),
      });
    } catch (e) {
      const error = toError(e);
      setFailure(error);
      now.onError?.(error);
      return;
    }
    engineRef.current = engine;
    applied.current = { ...now.settings };
    engine.start();
    now.onReady?.(engine);
    return () => {
      engineRef.current = null;
      engine.dispose();
    };
    // `transparent` is fixed when the canvas's context is made; changing it
    // remounts the canvas (see its key) and starts a new engine, which is why
    // the effects below depend on it too. They run after this one, so the
    // engine is always there for them.
  }, [transparent]);

  useEffect(() => {
    engineRef.current?.setMood(mood);
  }, [mood, transparent]);

  useEffect(() => {
    engineRef.current?.setMotion(motion);
  }, [motion, transparent]);

  useEffect(() => {
    engineRef.current?.setInteractive(interactive);
  }, [interactive, transparent]);

  useEffect(() => {
    engineRef.current?.setPaused(paused);
  }, [paused, transparent]);

  const external = level !== undefined;
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine || external) return;
    if (audio === 'microphone') {
      engine.useMicrophone().catch((e) => latest.current.onError?.(toError(e)));
    } else if (audio === 'demo') {
      engine.useDemoVoice();
    } else if (audio) {
      engine.setAudio(audio).catch((e) => latest.current.onError?.(toError(e)));
    } else {
      engine.stopVoice();
    }
  }, [audio, external, transparent]);

  useEffect(() => {
    if (level !== undefined) engineRef.current?.setLevel(level);
  }, [level, transparent]);

  // Pass on only the settings that actually changed: `settings` is usually a
  // fresh object on every render, and applying it restarts the still picture.
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine) return;
    const next = settings ?? {};
    const changes: Record<string, unknown> = {};
    const defaults = defaultSettings as Record<string, unknown>;
    for (const key of new Set([...Object.keys(applied.current), ...Object.keys(next)])) {
      const value = key in next ? (next as Record<string, unknown>)[key] : defaults[key];
      const before = key in applied.current ? (applied.current as Record<string, unknown>)[key] : defaults[key];
      if (value !== before) changes[key] = value;
    }
    applied.current = { ...next };
    if (Object.keys(changes).length) engine.configure(changes as Partial<PillSettings>);
  }, [settings, transparent]);

  useImperativeHandle(
    ref,
    () => ({
      pulse: (strength) => engineRef.current?.pulse(strength),
      reset: () => engineRef.current?.reset(),
      wake: () => engineRef.current?.wake(),
      appear: () => engineRef.current?.appear(),
      setLevel: (value) => engineRef.current?.setLevel(value),
      getStats: () => engineRef.current?.getStats() ?? null,
      get engine() {
        return engineRef.current;
      },
    }),
    [],
  );

  if (failure) return <>{fallback}</>;

  // The canvas fills this box, whatever its own drawing size, so the two
  // can't feed back on each other. With no size given, it is a square as wide
  // as its container.
  const sized = size !== undefined || className || style?.width !== undefined || style?.height !== undefined;
  const box: CSSProperties = {
    position: 'relative',
    ...(size !== undefined ? { width: size, height: size } : sized ? null : { width: '100%', aspectRatio: '1 / 1' }),
    ...style,
  };
  return (
    <div role="img" aria-label={label} className={className} style={box} {...rest}>
      <canvas
        key={transparent ? 'see-through' : 'opaque'}
        ref={canvasRef}
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          display: 'block',
          touchAction: interactive ? 'none' : undefined,
          cursor: interactive ? 'grab' : undefined,
        }}
      />
    </div>
  );
});
