"use client";
import { usePipecatClientMediaTrack } from "@pipecat-ai/client-react";
import {
  animate,
  motionValue,
  type MotionValue,
  type ValueAnimationTransition,
} from "motion/react";
import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";

import { ReactShaderToy } from "@/components/pipecat/wave-shader";
import {
  createVisualizerAnalyser,
  resolveVisualizerColor,
  type VisualizerState,
} from "@/lib/visualizer";

export type { VisualizerState };

type ParticipantType = Parameters<typeof usePipecatClientMediaTrack>[1];

/**
 * Threshold pattern the dither post-process scatters its rounding error
 * with. Bayer is the classic ordered dither — the woven crosshatch that
 * reads as "retro" — at 2x2, 4x4 or 8x8; bigger matrices hold more
 * shades and show less structure. "ign" is interleaved gradient noise,
 * which trades the grid for a fine, almost grainless stipple. "noise" is
 * plain white noise, i.e. film grain.
 */
export type DitherMethod = "bayer2" | "bayer4" | "bayer8" | "ign" | "noise";

/** Tuning for the retro dither post-process (see `dither`). */
export interface DitherOptions {
  /** Threshold pattern (default "bayer8"). */
  method?: DitherMethod;
  /**
   * Chunky pixel size in CSS px (default 3). The aura is sampled once
   * per cell, so this is a real low-resolution render rather than a blur
   * — and one dither cell covers one chunky pixel. 1 leaves the canvas
   * at full resolution and dithers alone.
   */
  pixelSize?: number;
  /**
   * Colour steps per channel (default 4, so a 64-colour palette). 2 is
   * one bit per channel — eight colours, maximum crunch.
   */
  levels?: number;
  /**
   * Steps for the alpha channel (defaults to `levels`). 2 hard-stipples
   * the orb's edge against the page; raise it for a softer falloff.
   */
  alphaLevels?: number;
  /**
   * How much of the pattern to apply, 0–1 (default 1). 0 is plain
   * rounding — flat posterized bands — and 1 the full dither.
   */
  strength?: number;
}

export interface AudioVisualizerWaveViewProps {
  /** Audio track to visualize. Rests as a calm drifting aura when null. */
  track?: MediaStreamTrack | null;
  /**
   * Aura color. Any CSS color, "currentColor", or a "--css-var" name.
   * Defaults to a vivid cyan — the aura is made of light, so near-black
   * colors wash out to gray.
   */
  color?: string;
  /**
   * Explicit second tone. The palette always blends between exactly two
   * colors; without this it derives the accent by rotating `color` by
   * `hueSpread`. Setting it pins the pair instead — speech then
   * interleaves the two tones without widening them. Any CSS color,
   * "currentColor", or a "--css-var" name.
   */
  accentColor?: string;
  /**
   * How many times the palette crosses between its two tones through the
   * depth of the orb (default 0.05). This is banding frequency, not hue
   * range — the range is fixed by `hueSpread`, so turning this up during
   * speech interleaves the two colors rather than adding new ones.
   */
  colorShift?: number;
  /**
   * Hue distance from `color` to its accent, as a fraction of the color
   * wheel (default 0.18, ~65°) — cyan pairs with indigo, say. The aura
   * only ever uses these two hues, so this stays harmonious however wide
   * it goes; 0 makes it single-color, and speech widens it further (see
   * ENERGY_GAIN.hueSpread). Ignored when `accentColor` pins the pair.
   */
  hueSpread?: number;
  /** Visualizer size in px (square, default 224). */
  size?: number;
  /** Animation speed multiplier over the state's base pace (default 1). */
  speed?: number;
  /** Edge-deformation multiplier over the state's base depth (default 1). */
  amplitude?: number;
  /** Brightness multiplier over the state's base glow (default 1). */
  glow?: number;
  /** Edge blur/softness of the aura (default 0.2). */
  softness?: number;
  /**
   * How solid the aura is: 0 draws open contour wisps (smoke), 1 fills the
   * body into an orb. Default 0.4 — enough body to read as a sphere while
   * the contours still show through it; at 1 the fill is uniform and
   * swallows them.
   */
  fill?: number;
  /**
   * Width of each layer's falloff, as a multiple of how far the sample
   * travelled between layers (0–1, default 0.28). This is anti-aliasing:
   * just enough hides the banding, too much (1 smears each layer wider
   * than the orb itself) melts every layer into one flat mass.
   */
  smoothing?: number;
  /**
   * Ink gain before tone mapping (default 0.55). The tone curve saturates
   * hard, so a lower density keeps the mid-tones inside its responsive
   * range and the contours visible; raise it for a denser, hotter aura.
   */
  density?: number;
  /**
   * Brightness at the very centre of the hollow (0–1, default 0.1). 0
   * empties the middle completely; raise it to keep a glow in there.
   */
  core?: number;
  /**
   * Fraction of the radius left open in the middle (0–1, default 0.3).
   * The ink ramps from `core` at this radius up to full at the surface,
   * so the orb reads as a shell with a void you can see into.
   */
  hollow?: number;
  /**
   * How far the innermost contour layer recedes, as a fraction of the
   * radius (0–1, default 0.22). The layers spread across that thickness
   * instead of stacking on one surface, which is what gives the shell
   * depth. 0 collapses them back onto a single sphere.
   */
  depth?: number;
  /**
   * Specular highlight strength (default 0.2; 0 removes it). Kept low now
   * that the middle is hollow — it sits over the void, where it reads
   * much more strongly than it did against a filled body.
   */
  highlight?: number;
  /** Remove the specular shine over the hollow. */
  noHighlight?: boolean;
  /**
   * Shine tint. Any CSS color, "currentColor", or a "--css-var" name.
   * Defaults to white warmed a little toward the aura color.
   */
  highlightColor?: string;
  /**
   * Number of light ribbons layered into the aura (default 24). More is
   * denser at a linear GPU cost. Baked into the shader as a compile-time
   * constant — changing it rebuilds the WebGL program, so treat it as
   * configuration, not animation.
   */
  iterations?: number;
  /**
   * Retro dither post-process: quantizes the finished pixel to a coarse
   * palette and scatters the rounding error into an ordered pattern, over
   * an optional chunky pixel grid. `true` takes the defaults; pass an
   * object to tune it (see {@link DitherOptions}).
   *
   * Compiled into the shader, so switching it on or off — or changing
   * `method` — rebuilds the WebGL program; the numeric knobs are uniforms
   * and change freely. A dithered canvas also renders at a 1:1 pixel
   * ratio: retro pixels are defined in CSS pixels, and supersampling
   * would only average the pattern back out.
   */
  dither?: boolean | DitherOptions;
  /**
   * Background optimization: "dark" composites tonemapped light, "light"
   * boosts saturation. Defaults to detecting the root element's "dark"
   * class, tracked live.
   */
  themeMode?: "dark" | "light";
  /**
   * Override the speech level computed from the track (0–1) — stands in
   * for both the phrase envelope and the gain-following pulse.
   */
  volume?: number;
  /**
   * Override: a session is being established — the aura shimmers gently.
   * Wins over isThinking; the track is ignored while set. Without
   * overrides the visualizer derives silent/speaking from the track on
   * its own.
   */
  isConnecting?: boolean;
  /**
   * Override: the bot is working on a response — the aura pulses deeply.
   * The track is ignored while set.
   */
  isThinking?: boolean;
  className?: string;
}

/** Ignore frame gaps longer than this (tab was backgrounded). */
const MAX_FRAME_SECONDS = 0.1;

/**
 * Band the level is measured over. Speech lives here, and the near-silent
 * top of the spectrum would otherwise drag the average down to a fraction
 * of its range — which reads as an aura that barely responds.
 */
const ENERGY_BAND_HZ = { low: 200, high: 8000 };

/** Band RMS at conversational level, which maps to a full-scale 1. */
const ENERGY_REFERENCE_RMS = 0.3;
/**
 * Envelope time constants, in seconds to cover ~63% of the remaining
 * distance. Rising is a swell rather than a jump; falling is slower still,
 * so the aura drifts back down over a couple of seconds instead of
 * dropping out the moment a phrase ends.
 */
const ENERGY_ATTACK_SECONDS = 0.32;
const ENERGY_RELEASE_SECONDS = 1.3;

/**
 * A second, much faster envelope over the same level, for the body's
 * swell. Slow enough to still ease in and out of silence rather than
 * jitter, quick enough that the orb visibly tracks the gain of the voice
 * instead of following the phrase.
 */
const PULSE_ATTACK_SECONDS = 0.06;
const PULSE_RELEASE_SECONDS = 0.28;

/**
 * Radians of wave phase per second at speed 1. The pace changes with the
 * voice, so the phase is integrated per frame on the CPU rather than
 * derived from the clock — rate × elapsed would jump the pattern every
 * time the pace moved.
 */
const PHASE_RATE = 0.05;

/**
 * Hue rotations per second at speed 1. Integrated at the same speed as the
 * phase, so the palette barely creeps at rest and visibly travels while
 * the bot is talking.
 */
const HUE_RATE = 0.0018;

const DEFAULT_TRANSITION: ValueAnimationTransition = {
  duration: 0.5,
  ease: "easeOut",
};
const DEFAULT_PULSE_TRANSITION: ValueAnimationTransition = {
  duration: 0.35,
  ease: "easeOut",
  repeat: Infinity,
  repeatType: "mirror",
};

interface AuraStateParams {
  speed: number;
  scale: number;
  amplitude: number;
  frequency: number;
  variance: number;
  brightness: number;
}

/**
 * Resting parameters per lifecycle state. Speaking's are the *quiet* end
 * of its range: a live track holds the visualizer in "speaking" for the
 * whole session, so the pauses between phrases have to look as settled as
 * silence does. Speech energy pushes it from here toward ENERGY_GAIN.
 */
const STATE_PARAMS: Record<VisualizerState, AuraStateParams> = {
  silent: {
    speed: 6,
    scale: 0.22,
    amplitude: 0.35,
    frequency: 0.35,
    variance: 0.06,
    brightness: 1.15,
  },
  connecting: {
    speed: 20,
    scale: 0.26,
    amplitude: 0.45,
    frequency: 0.7,
    variance: 0.1,
    brightness: 1.5,
  },
  thinking: {
    speed: 30,
    scale: 0.26,
    amplitude: 0.4,
    frequency: 1.0,
    variance: 0.2,
    brightness: 1.5,
  },
  speaking: {
    speed: 8,
    scale: 0.25,
    amplitude: 0.35,
    frequency: 0.45,
    variance: 0.08,
    brightness: 1.25,
  },
};

/**
 * How far full speech carries each parameter past its speaking baseline.
 * Everything here rides the slow `energy` envelope except scale, which
 * rides the fast `pulse` one — the body tracks the gain of the voice while
 * the churn, color and glow follow the shape of the phrase.
 */
const ENERGY_GAIN = {
  /** ~35% of the resting radius at full gain. */
  scale: 0.085,
  speed: 70,
  amplitude: 1.0,
  frequency: 1.0,
  variance: 0.7,
  /** Fraction of extra glow at full energy. */
  brightness: 0.9,
  /** Multiplier on the caller's colorShift at full energy. */
  colorShift: 1.6,
  /**
   * Multiplier on the caller's hueSpread at full energy. Speech pushes the
   * two tones further apart — more color in the orb — without ever adding
   * a third.
   */
  hueSpread: 0.6,
};

/** The two waiting states breathe; the rest hold a steady glow. */
const PULSE_BRIGHTNESS: Partial<Record<VisualizerState, number[]>> = {
  connecting: [1.7, 2.3],
  thinking: [0.8, 2.8],
};

/**
 * Displacement budget of the turbulence, in units of amplitude/frequency:
 * each of the 4 layers pushes along the swirl matrix's first column
 * (length ≈ 0.65) at 1.4× the previous layer's frequency (Σ 1.4⁻ⁱ ≈ 2.58).
 */
const TURB_REACH = 0.65 * 2.58;
/**
 * Fraction of that worst-case budget that carries visible light. The full
 * bound needs every layer's wave aligned outward at one point, where the
 * lone displaced ribbon is too faint to render; this factor is calibrated
 * numerically against the shader math (brightest-pixel search over
 * states, angles and phases: full-energy speech lights nothing beyond
 * r ≈ 0.42 in unfitted space).
 */
const TURB_VISIBLE_REACH = 0.74;

/**
 * Logical width of shader space mapped across the canvas. Fitted so the
 * farthest the tuning can push visible light — the speaking state at full
 * energy, body swell plus churn — lands exactly on the canvas edge: the
 * aura uses the whole canvas, and the margin left at rest is swell
 * headroom rather than padding. Derived from STATE_PARAMS / ENERGY_GAIN,
 * so retuning those re-fits the canvas automatically.
 */
function auraLogicalSpan(amplitudeProp: number, softness: number): number {
  const atFullEnergy = {
    scale: STATE_PARAMS.speaking.scale + ENERGY_GAIN.scale,
    amplitude: STATE_PARAMS.speaking.amplitude + ENERGY_GAIN.amplitude,
    frequency: STATE_PARAMS.speaking.frequency + ENERGY_GAIN.frequency,
  };
  const params = [...Object.values(STATE_PARAMS), atFullEnergy];
  const maxScale = Math.max(...params.map((p) => p.scale));
  // Displacement is amplitude over the shader's mix(2, 15, uFrequency).
  const maxTurb = Math.max(
    ...params.map((p) => p.amplitude / (2 + 13 * p.frequency)),
  );
  const churn = maxTurb * amplitudeProp * TURB_REACH * TURB_VISIBLE_REACH;
  // The blurred edge glows a little past the surface.
  const glow = 0.05 * softness + 0.005;
  return 2 * (maxScale + churn + glow);
}

// #1FD5F9 as shader RGB — the fallback when a color can't be parsed.
const DEFAULT_RGB: [number, number, number] = [0.121, 0.835, 0.976];

/** Resolved CSS color → RGB floats for the shader uniform. */
function colorToRgb(color: string): [number, number, number] {
  const ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) return DEFAULT_RGB;
  ctx.fillStyle = color;
  const normalized = String(ctx.fillStyle);
  if (normalized.startsWith("#")) {
    const n = parseInt(normalized.slice(1, 7), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }
  const parts = normalized.match(/[\d.]+/g);
  if (parts && parts.length >= 3) {
    return [
      Number(parts[0]) / 255,
      Number(parts[1]) / 255,
      Number(parts[2]) / 255,
    ];
  }
  return DEFAULT_RGB;
}

/**
 * RGB floats → HSV floats, the inverse of the shader's hsv2rgb. The
 * palette endpoints are resolved here so the shader never has to convert
 * a color forward per pixel.
 */
function rgbToHsv([r, g, b]: [number, number, number]): [
  number,
  number,
  number,
] {
  const max = Math.max(r, g, b);
  const d = max - Math.min(r, g, b);
  let h = 0;
  if (d > 0) {
    if (max === r) h = ((g - b) / d + 6) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
  }
  return [h, max === 0 ? 0 : d / max, max];
}

const DITHER_DEFAULTS = {
  method: "bayer8",
  pixelSize: 3,
  levels: 4,
  strength: 1,
} as const satisfies Required<Omit<DitherOptions, "alphaLevels">>;

/** Stable stand-in for `dither: true`, so the resolved knobs stay stable. */
const DITHER_ON: DitherOptions = {};

/**
 * The threshold expression behind each dither method, substituted into
 * the shader so the hot path carries no branch.
 *
 * The Bayer matrices are the classic ordered dither (Bayer, "An
 * optimum method for two-level rendition of continuous-tone pictures",
 * ICC 1973): a fixed weave whose crosshatch is exactly what reads as
 * retro. "ign" is interleaved gradient noise from Jimenez, "Next
 * Generation Post Processing in Call of Duty: Advanced Warfare"
 * (SIGGRAPH 2014) — two fracts and a dot product, yet it spreads far
 * more evenly than a hash, so it dithers as cleanly as blue noise
 * without needing a texture. "noise" is the plain hash, i.e. grain.
 */
const DITHER_PATTERN: Record<DitherMethod, string> = {
  bayer2: "bayer2(cell)",
  bayer4: "bayer4(cell)",
  bayer8: "bayer8(cell)",
  ign: "fract(52.9829189 * fract(dot(cell, vec2(0.06711056, 0.00583715))))",
  noise: "randFibo(cell).x",
};

/** The dither post-process, compiled in only when it is enabled. */
const makeDitherSource = (method: DitherMethod) => `
// Bayer threshold matrix, evaluated from the recursive doubling that
// defines it rather than sampled from a lookup table — no texture, and
// no integer bitwise ops, which GLSL ES 1.00 does not have. bayer2 is
// the 2x2 base [[0,2],[3,1]]/4 and each doubling folds in a
// quarter-weighted finer copy. Reducing mod 2 up front keeps the
// arithmetic exact however large the canvas gets.
float bayer2(vec2 a) {
  a = mod(floor(a), 2.0);
  return fract(a.x * 0.5 + a.y * a.y * 0.75);
}
float bayer4(vec2 a) { return bayer2(a * 0.5) * 0.25 + bayer2(a); }
float bayer8(vec2 a) { return bayer4(a * 0.5) * 0.25 + bayer2(a); }

/** Threshold in [0,1) for one cell of the retro pixel grid. */
float ditherThreshold(vec2 cell) {
  // uDitherStrength blends toward a flat 0.5, which is plain rounding:
  // at 0 the aura posterizes into hard bands, at 1 it fully dithers.
  return mix(0.5, ${DITHER_PATTERN[method]}, uDitherStrength);
}

// Quantize to \`levels\` steps, offset by the threshold first so the
// rounding error lands as a pattern the eye integrates back into the
// original shade instead of as a band. levels - 1 is the step count, so
// 2 levels means black and white and nothing between.
float quantize(float x, float levels, float threshold) {
  float steps = max(levels - 1.0, 1.0);
  return floor(clamp(x, 0.0, 1.0) * steps + threshold) / steps;
}

`;

/**
 * Fragment shader with the ribbon count baked in as a compile-time
 * constant, which keeps the hot loop unrollable. Fixed style parameters
 * are literals rather than uniforms for the same reason. The dither
 * post-process is compile-time too: off, it costs nothing at all.
 */
const makeShaderSource = (iterations: number, dither: DitherMethod | null) => {
  // A 1/255 nudge that hides 8-bit banding in the smooth falloff. The
  // coarse dither supersedes it — quantizing to a handful of levels
  // rounds a sub-step perturbation straight back away.
  const antiBanding = dither
    ? ""
    : "    color += (randFibo(fragCoord).x - 0.5) / 255.0;\n";

  return `
const float TAU = 6.283185;
const float ITERATIONS = ${iterations.toFixed(1)};

// Noise for dithering
vec2 randFibo(vec2 p) {
  p = fract(p * vec2(443.897, 441.423));
  p += dot(p, p.yx + 19.19);
  return fract((p.xx + p.yx) * p.xy);
}

// Tonemap
vec3 Tonemap(vec3 x) {
  x *= 4.0;
  return x / (1.0 + x);
}

// Luma for alpha
float luma(vec3 color) {
  return dot(color, vec3(0.299, 0.587, 0.114));
}

// HSV to RGB
vec3 hsv2rgb(vec3 c) {
  vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
  vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
  return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

float sdCircle(vec2 st, float r) {
  return length(st) - r;
}

vec2 turb(vec2 pos, float t, float it) {
  // Initial rotation matrix for swirl direction
  mat2 rotation = mat2(0.6, -0.25, 0.25, 0.9);
  // Secondary rotation applied each iteration (approx 53 degree rotation)
  mat2 layerRotation = mat2(0.6, -0.8, 0.8, 0.6);

  float frequency = mix(2.0, 15.0, uFrequency);
  float amplitude = uAmplitude;
  float frequencyGrowth = 1.4;
  float animTime = t;

  const int LAYERS = 4;
  for(int i = 0; i < LAYERS; i++) {
    // Calculate wave displacement for this layer
    vec2 rotatedPos = pos * rotation;
    vec2 wave = sin(frequency * rotatedPos + float(i) * animTime + it);

    // Apply displacement along rotation direction
    pos += (amplitude / frequency) * rotation[0] * wave;

    // Evolve parameters for next layer
    rotation *= layerRotation;
    amplitude *= mix(1.0, max(wave.x, wave.y), uVariance);
    frequency *= frequencyGrowth;
  }

  return pos;
}

${dither ? makeDitherSource(dither) : ""}void mainImage(out vec4 fragColor, in vec2 fragCoord) {
${
  dither
    ? `  // Retro pixel grid: every fragment in a cell samples the aura at that
  // cell's centre, so the whole effect is computed at the chunky
  // resolution rather than smooth-shaded and blocked up afterwards. At a
  // uPixelSize of 1 this is the identity — fragCoord already sits on
  // pixel centres — and the dither alone remains.
  vec2 cell = floor(fragCoord / uPixelSize);
  fragCoord = (cell + 0.5) * uPixelSize;
`
    : ""
}  vec2 uv = fragCoord / iResolution.xy;

  vec3 pp = vec3(0.0);
  // Wave phase, integrated on the CPU (see PHASE_RATE) rather than read
  // off the clock — the pace changes with the voice, and rate * elapsed
  // would jump the pattern every time the pace moved.
  float t = uPhase;
  // Shader space spans uSpan across the canvas — fitted so the tuning's
  // maximum reach lands on the edge (see auraLogicalSpan).
  vec2 pos = (uv - 0.5) * uSpan;

  vec2 prevPos = turb(pos, t, 0.0 - 1.0 / ITERATIONS);
  float spacing = mix(1.0, TAU, 0.5);

  // Distance from the centre, in units of the orb's radius.
  float rn = length(pos) / max(uScale, 1e-5);
  // Hollow core: ink fades out toward the middle, from the *unwarped*
  // position so every layer agrees on it. The orb becomes a shell of light
  // you can see into — depth in the churn near the rim, calm in the void —
  // rather than a solid disc where every layer piles up in the middle.
  float hollow = mix(uCore, 1.0, smoothstep(uHollow, 1.0, rn));

  for(float i = 1.0; i < ITERATIONS + 1.0; i++) {
    float iter = i / ITERATIONS;
    vec2 st = turb(pos, t, iter * spacing);
    // Each layer is a slightly smaller shell than the last, so the stack
    // spans a thickness of the orb and reads as depth.
    float sd = sdCircle(st, uScale * (1.0 - uDepth * iter));
    float d = abs(sd);
    float pd = distance(st, prevPos);
    prevPos = st;
    // Anti-aliasing width: how far this layer's sample travelled from the
    // last one. uSmoothing scales it, and it needs to stay well under the
    // orb's radius — at 1.0 the turbulence makes it wider than the whole
    // orb, which smears every layer into one flat mass.
    float dynamicBlur = exp2(pd * 2.0 * 1.4426950408889634) - 1.0;
    float edge = uBlur * 0.05 + max(dynamicBlur * uSmoothing, 0.001);

    // Two ways to ink a layer: the contour shell (wisps tracing the
    // surface) and the filled body (everything inside the surface). uFill
    // crossfades between them. It blends the *ink*, not the distances —
    // blending distances would leave the middle of the ball hollow, since
    // the shell's distance grows again as you move inward.
    float shell = smoothstep(0.0, edge, d) - 1.0;
    float body = smoothstep(0.0, edge, max(sd, 0.0)) - 1.0;
    float ink = mix(shell, body, uFill) * hollow;

    // Two-tone palette: the base color (as uColorHsv) and one accent an
    // HSV step away (uHsvDelta — derived from hueSpread, or the distance
    // to an explicit accentColor). Layers crossfade between just those
    // two, so speech can drive the color hard without the aura turning
    // into a rainbow.
    vec3 color = uColor;
    if(dot(abs(uHsvDelta), vec3(1.0)) > 0.001) {
      // The blend travels across the layers and rotates over time, so the
      // color still moves — uColorShift sets how many times it crosses
      // between the two tones through the depth of the orb. It needs to
      // clear a full cycle at rest, or the layers all sit near one end and
      // the aura looks single-colored.
      float wave = 0.5 + 0.5 * sin(TAU * (uHueDrift + iter * uColorShift * 1.5));
      // Biased toward the endpoints, so the two tones hold and the seams
      // between them stay narrow rather than reading as a sweep.
      vec3 hsv = uColorHsv + uHsvDelta * smoothstep(0.2, 0.8, wave);
      hsv.x = fract(hsv.x);
      hsv.yz = clamp(hsv.yz, 0.0, 1.0);
      color = hsv2rgb(hsv);
    }

    pp += ink * color;
  }

  pp *= 1.0 / ITERATIONS;

  // Specular highlight: a soft spot set up and to the left, scaled with
  // the orb so it holds its place at any size. uHighlightColor defaults
  // to white tinted a little by the aura — the cue that sells a solid
  // sphere over a cloud.
  vec2 hp = pos - vec2(-0.3, 0.3) * uScale;
  float spec = uHighlight * exp(-dot(hp, hp) / max(uScale * uScale * 0.07, 1e-6));
  vec3 highlight = spec * uHighlightColor;

  vec3 color;

  // Dark mode (default)
  if(uMode < 0.5) {
    color = (-pp * uDensity) * 1.2 + highlight;
${antiBanding}    color = Tonemap(color);
    float alpha = luma(color) * uMix;
    fragColor = vec4(color * uMix, alpha);
  }

  // Light mode
  else {
    color = -pp * uDensity + highlight;
${antiBanding}
    // Preserve hue by tone mapping brightness only
    float brightness = length(color);
    vec3 direction = brightness > 0.0 ? color / brightness : color;

    // Reinhard on brightness
    float factor = 2.0;
    float mappedBrightness = (brightness * factor) / (1.0 + brightness * factor);
    color = direction * mappedBrightness;

    // Boost saturation to compensate for white background bleed-through
    // When alpha < 1.0, white bleeds through making colors look desaturated
    // So we increase saturation to maintain vibrant appearance
    float gray = dot(color, vec3(0.2, 0.5, 0.1));
    float saturationBoost = 3.0;
    color = mix(vec3(gray), color, saturationBoost);

    // Clamp between 0-1
    color = clamp(color, 0.0, 1.0);

    float alpha = mappedBrightness * clamp(uMix, 1.0, 2.0);
    fragColor = vec4(color, alpha);
  }
${
  dither
    ? `
  // Post-process the finished pixel: quantize it to a coarse palette and
  // scatter the rounding error with the ordered pattern. Colour and alpha
  // share one threshold so they stay in step — the orb's soft edge
  // stipples out instead of staying smooth against chunky insides.
  float threshold = ditherThreshold(cell);
  fragColor = vec4(
    quantize(fragColor.r, uDitherLevels, threshold),
    quantize(fragColor.g, uDitherLevels, threshold),
    quantize(fragColor.b, uDitherLevels, threshold),
    quantize(fragColor.a, uDitherAlphaLevels, threshold)
  );
`
    : ""
}}`;
};

/**
 * The mutable uniform store behind one shader instance. ReactShaderToy
 * reads each .value fresh every frame, so animation writes land here
 * directly — React never re-renders on the hot path.
 */
type AuraUniformStore = {
  /** Accumulated wave phase, advanced per frame at the current pace. */
  uPhase: { type: "1f"; value: number };
  /** Logical width of shader space across the canvas (max-reach fit). */
  uSpan: { type: "1f"; value: number };
  /** Edge blur/softness. */
  uBlur: { type: "1f"; value: number };
  /** Orb radius in shader space (state base + pulse swell). */
  uScale: { type: "1f"; value: number };
  /** Wave frequency and complexity. */
  uFrequency: { type: "1f"; value: number };
  /** Turbulence amplitude (state base + energy, × amplitude prop). */
  uAmplitude: { type: "1f"; value: number };
  /** Brightness of the aurora (state base × energy boost × glow prop). */
  uMix: { type: "1f"; value: number };
  /** Amplitude variation across layers (0–1) — the churn's raggedness. */
  uVariance: { type: "1f"; value: number };
  /** Width of each layer's falloff — low keeps the contours distinct. */
  uSmoothing: { type: "1f"; value: number };
  /** Ink gain before tone mapping; low leaves headroom for gradients. */
  uDensity: { type: "1f"; value: number };
  /** 0 = open contour wisps, 1 = a filled body. */
  uFill: { type: "1f"; value: number };
  /** Brightness at the very centre (0–1); the floor of the hollow. */
  uCore: { type: "1f"; value: number };
  /** Fraction of the radius left open in the middle (0–1). */
  uHollow: { type: "1f"; value: number };
  /** How far the innermost layer recedes, as a fraction of the radius. */
  uDepth: { type: "1f"; value: number };
  /** Specular highlight strength. */
  uHighlight: { type: "1f"; value: number };
  /** Rotating hue offset, advanced per frame with the phase. */
  uHueDrift: { type: "1f"; value: number };
  /** How often the palette crosses between its two tones, per layer. */
  uColorShift: { type: "1f"; value: number };
  /** HSV step from the base color to its accent tone. */
  uHsvDelta: { type: "3fv"; value: [number, number, number] };
  /** Display mode: 0=dark background, 1=light background. */
  uMode: { type: "1f"; value: number };
  /** Aura color as shader RGB floats. */
  uColor: { type: "3fv"; value: [number, number, number] };
  /** The aura color again, pre-converted to HSV for the palette blend. */
  uColorHsv: { type: "3fv"; value: [number, number, number] };
  /** Shine tint as shader RGB floats. */
  uHighlightColor: { type: "3fv"; value: [number, number, number] };
  /** Retro pixel grid size in canvas pixels; 1 renders at full res. */
  uPixelSize: { type: "1f"; value: number };
  /** Colour steps per channel the dither quantizes to. */
  uDitherLevels: { type: "1f"; value: number };
  /** Steps the dither quantizes alpha to. */
  uDitherAlphaLevels: { type: "1f"; value: number };
  /** Pattern strength: 0 posterizes flat, 1 is the full dither. */
  uDitherStrength: { type: "1f"; value: number };
};

interface AuraEngine {
  speed: MotionValue<number>;
  scale: MotionValue<number>;
  amplitude: MotionValue<number>;
  frequency: MotionValue<number>;
  variance: MotionValue<number>;
  brightness: MotionValue<number>;
  /** Accumulated wave phase (see PHASE_RATE). */
  phase: number;
  /** Rotating hue offset 0–1 (see HUE_RATE). */
  hueDrift: number;
  uniforms: AuraUniformStore;
}

/**
 * Motion values plus the uniform store they feed; created once per
 * mounted visualizer, seeded so the mount animation eases into the
 * silent baseline.
 */
function createAuraEngine(): AuraEngine {
  return {
    speed: motionValue(STATE_PARAMS.silent.speed),
    scale: motionValue(0.2),
    amplitude: motionValue(1.0),
    frequency: motionValue(0.35),
    variance: motionValue(0.06),
    brightness: motionValue(0.9),
    phase: 0,
    hueDrift: 0,
    uniforms: {
      uPhase: { type: "1f", value: 0 },
      uSpan: { type: "1f", value: auraLogicalSpan(1, 0.2) },
      uBlur: { type: "1f", value: 0.2 },
      uScale: { type: "1f", value: 0.2 },
      uFrequency: { type: "1f", value: 0.35 },
      uAmplitude: { type: "1f", value: 1.0 },
      uMix: { type: "1f", value: 0.9 },
      uVariance: { type: "1f", value: 0.06 },
      uSmoothing: { type: "1f", value: 0.28 },
      uDensity: { type: "1f", value: 0.55 },
      uFill: { type: "1f", value: 0.4 },
      uCore: { type: "1f", value: 0.1 },
      uHollow: { type: "1f", value: 0.3 },
      uDepth: { type: "1f", value: 0.22 },
      uHighlight: { type: "1f", value: 0.2 },
      uHueDrift: { type: "1f", value: 0 },
      uColorShift: { type: "1f", value: 0.05 },
      uHsvDelta: { type: "3fv", value: [0.18, 0, 0] },
      uMode: { type: "1f", value: 1.0 },
      uColor: { type: "3fv", value: [...DEFAULT_RGB] },
      uColorHsv: { type: "3fv", value: rgbToHsv(DEFAULT_RGB) },
      uHighlightColor: { type: "3fv", value: defaultHighlightRgb(DEFAULT_RGB) },
      uPixelSize: { type: "1f", value: DITHER_DEFAULTS.pixelSize },
      uDitherLevels: { type: "1f", value: DITHER_DEFAULTS.levels },
      uDitherAlphaLevels: { type: "1f", value: DITHER_DEFAULTS.levels },
      uDitherStrength: { type: "1f", value: DITHER_DEFAULTS.strength },
    },
  };
}

/** The default shine tint: white warmed a little toward the aura color. */
function defaultHighlightRgb(
  rgb: [number, number, number],
): [number, number, number] {
  return [
    0.65 + 0.35 * rgb[0],
    0.65 + 0.35 * rgb[1],
    0.65 + 0.35 * rgb[2],
  ];
}

/** A live analyser and the speech envelopes integrated over it. */
interface AuraAudio {
  analyser: AnalyserNode;
  data: Uint8Array<ArrayBuffer>;
  firstBin: number;
  lastBin: number;
  binCount: number;
  /** Phrase-shaped energy: slow to rise, slower to fall. */
  energy: number;
  /** Gain-following level for the body's swell. */
  pulse: number;
}

/** Per-frame inputs the compositor reads without re-subscribing. */
interface AuraFrameInputs {
  state: VisualizerState;
  volume?: number;
  speed: number;
  amplitude: number;
  glow: number;
  colorShift: number;
  hueSpread: number;
}

/**
 * Maps the kit's visualizer lifecycle onto the shader's parameters:
 * silent drifts calmly, connecting springs up with a gentle shimmer,
 * thinking pulses deeply, and speaking rides the voice — a quiet track
 * sits at the calm baseline and speech drives the turbulence up.
 *
 * Speech level is the band RMS over the voice range, normalized to
 * conversational level, then run through two asymmetric envelopes.
 * `energy` has the long release that keeps the aura from twitching per
 * syllable — it reads the shape of a phrase, holds through the gaps
 * inside it, then eases back down once talking stops. `pulse` tracks the
 * same level far more closely, for the one parameter (the body's swell)
 * that should follow the voice moment to moment. All time constants are
 * applied per elapsed second, so the feel is the same on a 60 Hz and a
 * 120 Hz display.
 *
 * A single rAF compositor integrates the envelopes and the wave/hue
 * phases, samples the motion-value baselines, and writes every derived
 * value into one stable uniform store the shader host reads per frame —
 * no React render ever sits on the animation path.
 */
function useAuraUniforms(opts: {
  state: VisualizerState;
  track: MediaStreamTrack | null;
  volume?: number;
  color: string;
  accentColor?: string;
  colorShift: number;
  hueSpread: number;
  speed: number;
  amplitude: number;
  glow: number;
  softness: number;
  fill: number;
  core: number;
  hollow: number;
  depth: number;
  smoothing: number;
  density: number;
  highlight: number;
  noHighlight: boolean;
  highlightColor?: string;
  ditherPixelSize: number;
  ditherLevels: number;
  ditherAlphaLevels: number;
  ditherStrength: number;
  themeMode?: "dark" | "light";
  className?: string;
  rootRef: RefObject<HTMLDivElement | null>;
}): AuraUniformStore {
  const {
    state,
    track,
    volume,
    color,
    accentColor,
    colorShift,
    hueSpread,
    speed,
    amplitude,
    glow,
    softness,
    fill,
    core,
    hollow,
    depth,
    smoothing,
    density,
    highlight,
    noHighlight,
    highlightColor,
    ditherPixelSize,
    ditherLevels,
    ditherAlphaLevels,
    ditherStrength,
    themeMode,
    className,
    rootRef,
  } = opts;
  const [engine] = useState(createAuraEngine);
  const audioRef = useRef<AuraAudio | null>(null);
  // The HSV step to an explicit accentColor; null derives it from
  // hueSpread instead.
  const accentDeltaRef = useRef<[number, number, number] | null>(null);
  const frameInputsRef = useRef<AuraFrameInputs>({
    state,
    volume,
    speed,
    amplitude,
    glow,
    colorShift,
    hueSpread,
  });

  useEffect(() => {
    frameInputsRef.current = {
      state,
      volume,
      speed,
      amplitude,
      glow,
      colorShift,
      hueSpread,
    };
  });

  // The compositor: one always-on rAF loop for everything per-frame.
  // Unmount cancels it and parks the motion values — the infinite pulse
  // animations would otherwise tick forever.
  useEffect(() => {
    const { uniforms } = engine;
    let rafId = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const delta = Math.min((now - last) / 1000, MAX_FRAME_SECONDS);
      last = now;
      const inputs = frameInputsRef.current;
      const audio = audioRef.current;
      const speaking = inputs.state === "speaking";

      // Only speech drives the boost; the other states are self-animated.
      // An explicit volume override stands in for both envelopes.
      let energy = 0;
      let pulse = 0;
      if (speaking && inputs.volume !== undefined) {
        energy = pulse = inputs.volume;
      } else if (speaking && audio) {
        audio.analyser.getByteFrequencyData(audio.data);
        let sum = 0;
        for (let i = audio.firstBin; i <= audio.lastBin; i++) {
          const v = (audio.data[i] ?? 0) / 255;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / audio.binCount);
        const level = Math.min(1, rms / ENERGY_REFERENCE_RMS);

        const seconds =
          level > audio.energy ? ENERGY_ATTACK_SECONDS : ENERGY_RELEASE_SECONDS;
        audio.energy += (level - audio.energy) * (1 - Math.exp(-delta / seconds));
        const pulseSeconds =
          level > audio.pulse ? PULSE_ATTACK_SECONDS : PULSE_RELEASE_SECONDS;
        audio.pulse +=
          (level - audio.pulse) * (1 - Math.exp(-delta / pulseSeconds));
        energy = audio.energy;
        pulse = audio.pulse;
      }

      // Both phases integrate at the current pace, so the churn and the
      // color rotation accelerate together when the voice picks up.
      const pace = (engine.speed.get() + ENERGY_GAIN.speed * energy) * inputs.speed;
      engine.phase += delta * PHASE_RATE * pace;
      engine.hueDrift = (engine.hueDrift + delta * HUE_RATE * pace) % 1;

      // Energy rides on top of the animated baselines, so the two
      // compose: state changes still ease, and the voice moves the aura
      // within a state.
      uniforms.uPhase.value = engine.phase;
      uniforms.uHueDrift.value = engine.hueDrift;
      uniforms.uScale.value = engine.scale.get() + ENERGY_GAIN.scale * pulse;
      uniforms.uAmplitude.value =
        (engine.amplitude.get() + ENERGY_GAIN.amplitude * energy) *
        inputs.amplitude;
      uniforms.uFrequency.value =
        engine.frequency.get() + ENERGY_GAIN.frequency * energy;
      uniforms.uVariance.value =
        engine.variance.get() + ENERGY_GAIN.variance * energy;
      uniforms.uMix.value =
        engine.brightness.get() * (1 + ENERGY_GAIN.brightness * energy) *
        inputs.glow;
      // Speech interleaves the two tones more finely through the orb and,
      // when the accent is derived from hueSpread, pushes them further
      // apart; an explicit accentColor pins the pair instead.
      uniforms.uColorShift.value =
        inputs.colorShift * (1 + ENERGY_GAIN.colorShift * energy);
      const hsvDelta = uniforms.uHsvDelta.value;
      const accentDelta = accentDeltaRef.current;
      if (accentDelta) {
        hsvDelta[0] = accentDelta[0];
        hsvDelta[1] = accentDelta[1];
        hsvDelta[2] = accentDelta[2];
      } else {
        hsvDelta[0] = inputs.hueSpread * (1 + ENERGY_GAIN.hueSpread * energy);
        hsvDelta[1] = 0;
        hsvDelta[2] = 0;
      }

      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafId);
      engine.speed.stop();
      engine.scale.stop();
      engine.amplitude.stop();
      engine.frequency.stop();
      engine.variance.stop();
      engine.brightness.stop();
    };
  }, [engine]);

  // The analyser only exists while speaking without a volume override.
  // Its envelopes live with it, so a new speaking session starts from
  // silence rather than inheriting a stale level.
  useEffect(() => {
    if (state !== "speaking" || !track || volume !== undefined) return;
    const { analyser, dispose } = createVisualizerAnalyser(track);
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.55;
    const data = new Uint8Array(analyser.frequencyBinCount);

    // Bin range covering ENERGY_BAND_HZ.
    const binHz = analyser.context.sampleRate / 2 / analyser.frequencyBinCount;
    const firstBin = Math.max(1, Math.floor(ENERGY_BAND_HZ.low / binHz));
    const lastBin = Math.min(
      data.length - 1,
      Math.ceil(ENERGY_BAND_HZ.high / binHz),
    );
    audioRef.current = {
      analyser,
      data,
      firstBin,
      lastBin,
      binCount: Math.max(1, lastBin - firstBin + 1),
      energy: 0,
      pulse: 0,
    };
    return () => {
      audioRef.current = null;
      dispose();
    };
  }, [state, track, volume]);

  useEffect(() => {
    const base = STATE_PARAMS[state];
    const scaleTransition: ValueAnimationTransition =
      state === "connecting"
        ? { type: "spring", duration: 1.0, bounce: 0.35 }
        : DEFAULT_TRANSITION;
    const pulse = PULSE_BRIGHTNESS[state];

    animate(engine.speed, base.speed, DEFAULT_TRANSITION);
    animate(engine.scale, base.scale, scaleTransition);
    animate(engine.amplitude, base.amplitude, DEFAULT_TRANSITION);
    animate(engine.frequency, base.frequency, DEFAULT_TRANSITION);
    animate(engine.variance, base.variance, DEFAULT_TRANSITION);
    animate(
      engine.brightness,
      pulse ?? base.brightness,
      pulse ? DEFAULT_PULSE_TRANSITION : DEFAULT_TRANSITION,
    );
  }, [engine, state]);

  useEffect(() => {
    const { uniforms } = engine;
    uniforms.uSpan.value = auraLogicalSpan(amplitude, softness);
    uniforms.uBlur.value = softness;
    uniforms.uFill.value = fill;
    uniforms.uCore.value = core;
    uniforms.uHollow.value = hollow;
    uniforms.uDepth.value = depth;
    uniforms.uSmoothing.value = smoothing;
    uniforms.uDensity.value = density;
    uniforms.uHighlight.value = noHighlight ? 0 : highlight;
    uniforms.uPixelSize.value = ditherPixelSize;
    uniforms.uDitherLevels.value = ditherLevels;
    uniforms.uDitherAlphaLevels.value = ditherAlphaLevels;
    uniforms.uDitherStrength.value = ditherStrength;
  }, [
    engine,
    amplitude,
    softness,
    fill,
    core,
    hollow,
    depth,
    smoothing,
    density,
    highlight,
    noHighlight,
    ditherPixelSize,
    ditherLevels,
    ditherAlphaLevels,
    ditherStrength,
  ]);

  // Resolve CSS-flavored colors to shader RGB. className is a dependency
  // because it can change what currentColor resolves to.
  useEffect(() => {
    const { uniforms } = engine;
    const rgb = colorToRgb(resolveVisualizerColor(color, rootRef.current));
    const baseHsv = rgbToHsv(rgb);
    uniforms.uColor.value = rgb;
    uniforms.uColorHsv.value = baseHsv;

    if (accentColor) {
      const accentHsv = rgbToHsv(
        colorToRgb(resolveVisualizerColor(accentColor, rootRef.current)),
      );
      // Hue takes the short way around the wheel.
      let hue = accentHsv[0] - baseHsv[0];
      hue -= Math.round(hue);
      accentDeltaRef.current = [
        hue,
        accentHsv[1] - baseHsv[1],
        accentHsv[2] - baseHsv[2],
      ];
    } else {
      accentDeltaRef.current = null;
    }

    uniforms.uHighlightColor.value = highlightColor
      ? colorToRgb(resolveVisualizerColor(highlightColor, rootRef.current))
      : defaultHighlightRgb(rgb);
  }, [engine, color, accentColor, highlightColor, className, rootRef]);

  // Without an explicit themeMode, follow the documentElement's "dark"
  // class live.
  useEffect(() => {
    if (themeMode) {
      engine.uniforms.uMode.value = themeMode === "light" ? 1.0 : 0.0;
      return;
    }
    const root = document.documentElement;
    const apply = () => {
      engine.uniforms.uMode.value = root.classList.contains("dark") ? 0.0 : 1.0;
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, [engine, themeMode]);

  return engine.uniforms;
}

// MSAA does nothing for a fullscreen quad and the shader needs no depth
// buffer. Alpha stays on — both shader modes composite via destination
// alpha.
const AURA_CONTEXT_ATTRIBUTES = { antialias: false, depth: false };

// The aura is soft by design, so supersampling past 1.5x is invisible —
// and fragment cost is quadratic in the pixel ratio.
const MAX_PIXEL_RATIO = 1.5;

/**
 * Shader aura audio visualizer for any MediaStreamTrack: swirling ribbons
 * of turbulent light that react to the session. Silent drifts calmly;
 * speaking answers the voice with turbulence — the churn quickens, the
 * wisps reach further out, the layers grow more ragged, and the body
 * swells slightly — all easing back to the calm flow through pauses;
 * connecting springs up with a gentle shimmer; thinking pulses deeply.
 *
 * Silent and speaking derive from the track; the isConnecting /
 * isThinking overrides opt into the kit's other shared lifecycle states,
 * and every state change animates instead of snapping. The resolved
 * VisualizerState is exposed as data-state. Renders nothing where WebGL
 * is unavailable.
 *
 * The canvas is fitted to the tuning's maximum reach: at full speech the
 * aura just touches its edges, so the margin around the resting orb is
 * swell headroom rather than padding (see auraLogicalSpan).
 */
export const AudioVisualizerWaveView = memo(function AudioVisualizerWaveView({
  track = null,
  color = "#1FD5F9",
  accentColor,
  colorShift = 0.05,
  hueSpread = 0.18,
  size = 224,
  speed = 1,
  amplitude = 1,
  glow = 1,
  softness = 0.2,
  fill = 0.4,
  core = 0.1,
  hollow = 0.3,
  depth = 0.22,
  smoothing = 0.28,
  density = 0.55,
  highlight = 0.2,
  noHighlight = false,
  highlightColor,
  iterations = 24,
  dither = false,
  themeMode,
  volume,
  isConnecting = false,
  isThinking = false,
  className,
}: AudioVisualizerWaveViewProps) {
  const rootRef = useRef<HTMLDivElement>(null);

  // Resolved to primitives rather than an options object: `dither={{...}}`
  // is a fresh literal every render, and both the shader source and the
  // canvas remount key have to key off values that hold still.
  const ditherOpts = typeof dither === "object" ? dither : DITHER_ON;
  const ditherMethod = dither
    ? (ditherOpts.method ?? DITHER_DEFAULTS.method)
    : null;
  const ditherPixelSize = Math.max(
    1,
    ditherOpts.pixelSize ?? DITHER_DEFAULTS.pixelSize,
  );
  const ditherLevels = Math.max(2, ditherOpts.levels ?? DITHER_DEFAULTS.levels);
  const ditherAlphaLevels = Math.max(2, ditherOpts.alphaLevels ?? ditherLevels);
  const ditherStrength = Math.min(
    1,
    Math.max(0, ditherOpts.strength ?? DITHER_DEFAULTS.strength),
  );

  const state: VisualizerState = isConnecting
    ? "connecting"
    : isThinking
      ? "thinking"
      : track
        ? "speaking"
        : "silent";

  const uniforms = useAuraUniforms({
    state,
    track,
    volume,
    color,
    accentColor,
    colorShift,
    hueSpread,
    speed,
    amplitude,
    glow,
    softness,
    fill,
    core,
    hollow,
    depth,
    smoothing,
    density,
    highlight,
    noHighlight,
    highlightColor,
    ditherPixelSize,
    ditherLevels,
    ditherAlphaLevels,
    ditherStrength,
    themeMode,
    className,
    rootRef,
  });

  const ribbonCount = Math.max(1, Math.round(iterations));
  const shaderSource = useMemo(
    () => makeShaderSource(ribbonCount, ditherMethod),
    [ribbonCount, ditherMethod],
  );

  return (
    <div
      ref={rootRef}
      data-slot="audio-visualizer-wave"
      data-state={state}
      style={{ width: size, height: size }}
      className={className}
    >
      <ReactShaderToy
        key={`${ribbonCount}:${ditherMethod ?? "off"}`}
        fs={shaderSource}
        devicePixelRatio={
          // Retro pixels are sized in CSS pixels, and supersampling would
          // only average the pattern back out — so a dithered canvas
          // renders 1:1, which is cheaper besides.
          ditherMethod
            ? 1
            : Math.min(globalThis.devicePixelRatio ?? 1, MAX_PIXEL_RATIO)
        }
        uniforms={uniforms}
        contextAttributes={AURA_CONTEXT_ATTRIBUTES}
        onError={(error) => {
          console.error("Shader error:", error);
        }}
        onWarning={(warning) => {
          console.warn("Shader warning:", warning);
        }}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
});

export interface AudioVisualizerWaveProps extends Omit<
  AudioVisualizerWaveViewProps,
  "track"
> {
  /** Which participant's audio to visualize. */
  participantType: ParticipantType;
}

/**
 * Aura audio visualizer wired to a Pipecat media track. Pass
 * isConnecting / isThinking to reflect session state; silent and speaking
 * follow the participant's audio automatically. Must be rendered inside a
 * PipecatClientProvider.
 */
export function AudioVisualizerWave({
  participantType,
  ...props
}: AudioVisualizerWaveProps) {
  const track = usePipecatClientMediaTrack("audio", participantType);
  return <AudioVisualizerWaveView track={track} {...props} />;
}
