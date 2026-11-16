import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

const LABEL = "The audio being heard";

/** The waveform's columns, in CSS pixels, and how much audio each one stands for. */
const COLUMN_WIDTH = 3;
const COLUMN_GAP = 2;
const COLUMN_MS = 40;
/** The shortest a column is drawn, so silence is a line rather than nothing. */
const MIN_HEIGHT = 2;
/** How far the loudest sample of a slice is lifted, so speech fills the strip. */
const GAIN = 1.8;
/** How faint the columns are when nothing is being heard. */
const IDLE_ALPHA = 0.25;

interface VoiceWaveformProps {
  /** The audio being heard, or null when nothing is. */
  track: MediaStreamTrack | null;
  className?: string;
}

/**
 * The audio being heard as a wide waveform scrolling by: a column for every
 * 40 ms, as tall as that slice is loud. It stops where it is when the audio
 * does, so the last turn's shape stays on show beside its reading.
 */
export function VoiceWaveform({ track, className }: VoiceWaveformProps) {
  // The canvas it draws on.
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // The columns drawn so far, the oldest first. Kept across tracks, so one
  // turn's audio scrolls off as the next comes in.
  const levelsRef = useRef<number[]>([]);

  // Drawing is the canvas's own business, and listening is the audio graph's.
  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const audio = track ? new AudioContext() : null;
    const analyser = audio?.createAnalyser();
    if (audio && analyser && track) {
      analyser.fftSize = 2048;
      audio.createMediaStreamSource(new MediaStream([track])).connect(analyser);
      void audio.resume();
    }
    const samples = new Float32Array(analyser?.fftSize ?? 0);

    let frame = 0;
    let last = performance.now();
    let peak = 0;

    const draw = (now: number) => {
      frame = requestAnimationFrame(draw);
      const levels = levelsRef.current;
      if (analyser) {
        analyser.getFloatTimeDomainData(samples);
        for (const sample of samples) peak = Math.max(peak, Math.abs(sample));
        while (now - last >= COLUMN_MS) {
          levels.push(Math.min(1, peak * GAIN));
          last += COLUMN_MS;
          peak = 0;
        }
      }

      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const ratio = window.devicePixelRatio || 1;
      if (
        canvas.width !== Math.round(width * ratio) ||
        canvas.height !== Math.round(height * ratio)
      ) {
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
      }
      const columns = Math.floor(
        (width + COLUMN_GAP) / (COLUMN_WIDTH + COLUMN_GAP),
      );
      if (levels.length > columns) levels.splice(0, levels.length - columns);

      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      // The canvas's own text colour, so the waveform follows the theme.
      context.fillStyle = getComputedStyle(canvas).color;
      context.globalAlpha = analyser ? 1 : IDLE_ALPHA;
      const empty = columns - levels.length;
      for (let column = 0; column < columns; column++) {
        const level = levels[column - empty] ?? 0;
        const tall = Math.max(MIN_HEIGHT, level * height);
        context.fillRect(
          column * (COLUMN_WIDTH + COLUMN_GAP),
          (height - tall) / 2,
          COLUMN_WIDTH,
          tall,
        );
      }
    };
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      void audio?.close();
    };
  }, [track]);

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label={LABEL}
      className={cn("block w-full text-foreground", className)}
    />
  );
}
