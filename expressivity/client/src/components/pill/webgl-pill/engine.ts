// The pill's renderer: everything between a canvas and the picture on it.
//
// createPillEngine(canvas) sets up WebGL, runs the animation loop and exposes
// what a host drives the pill with (mood, motion, a voice). It assumes
// nothing about the page: it sizes itself to the canvas, stops drawing while
// off screen or at rest, survives a lost graphics context, and lets go of
// everything in dispose(). Several can run on one page.
import vertSrc from './shaders/fullscreen.vert?raw';
import geometrySrc from './shaders/geometry.glsl?raw';
import traceSrc from './shaders/pathtrace.frag?raw';
import taaSrc from './shaders/taa.frag?raw';
import downSrc from './shaders/bloomDown.frag?raw';
import upSrc from './shaders/bloomUp.frag?raw';
import flareSrc from './shaders/flare.frag?raw';
import compositeSrc from './shaders/composite.frag?raw';
import { createProgram, createTarget, deleteTarget, type Program, type Target } from './gl';
import {
  DEG, axisAngle, cloudNoise, cross, dirFromAngles, mul, normalize, rotX, rotY,
  type Mat3, type Vec3,
} from './math';
import { MOODS, MOOD_NAMES, MoodState, type Mood } from './mood';
import { MOTE_COUNT, Motes } from './motes';
import { Motion, facing, type MotionMode, type MotionState } from './motion';
import { Pacer } from './pacing';
import { defaultLights, defaultSettings, type Light, type PillSettings } from './settings';
import { Voice, WAVE_TEXELS, type VoiceSource } from './voice';

export const MOTION_MODES: readonly MotionMode[] = ['auto', 'idle', 'listening', 'spinning', 'rest'];

export type PillEngineOptions = {
  mood?: Mood;
  motion?: MotionMode;
  /**
   * Let the pointer take hold of the pill and turn it, and have the pill lean
   * towards the pointer as it moves about the page. Default true.
   */
  interactive?: boolean;
  /**
   * Draw onto a see-through canvas, so whatever is behind shows where the
   * pill is dark. Meant for dark backgrounds. Default true. Fixed for the
   * life of the engine.
   */
  transparent?: boolean;
  /** Make an entrance when first started. Default true. */
  intro?: boolean;
  settings?: Partial<PillSettings>;
  lights?: readonly Light[];
  onStateChange?: (state: MotionState) => void;
};

export type PillStats = {
  width: number;
  height: number;
  fps: number;
  /** frames drawn since it started */
  frames: number;
  state: MotionState;
  /** the picture is standing still and being refined */
  still: boolean;
  /** how many frames the still is built from so far */
  samples: number;
  maxSamples: number;
  /** samples a pixel while moving */
  spp: number;
  /** a frame is drawn on every n-th refresh */
  every: number;
  /** the display's frame time, ms */
  refresh: number;
  mood: Mood;
  voice: VoiceSource;
  level: number;
};

// The browser can't run the pill: no WebGL 2, or no floating-point render
// targets.
export class PillUnsupportedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PillUnsupportedError';
  }
}

/** A running pill. Made by createPillEngine(). */
export interface PillEngine {
  readonly canvas: HTMLCanvasElement;
  /** Live settings. Write to them freely, then call invalidate(); or use configure(). */
  readonly settings: PillSettings;
  /** The studio lights. Change them freely, then call invalidate(). */
  readonly lights: Light[];
  /** Begin drawing. The first time, it makes its entrance (unless told not to). */
  start(): void;
  /** Stop drawing. start() picks up where it left off. */
  stop(): void;
  /** Stop for good and let go of everything: listeners, audio, and what was made on the graphics context. */
  dispose(): void;
  /** Change settings. */
  configure(changes: Partial<PillSettings>): void;
  /** Start the picture afresh, after writing to `settings` or `lights` directly. */
  invalidate(): void;
  /** The sentiment it shows. Unless `immediate`, it turns once as the colour comes over it. */
  setMood(mood: Mood, immediate?: boolean): void;
  readonly mood: Mood;
  /**
   * How it carries itself: 'auto' (listening while someone talks, then idle,
   * then at rest), or hold it in 'idle', 'listening', 'spinning' or 'rest'.
   */
  setMotion(mode: MotionMode): void;
  readonly motion: MotionMode;
  /** What it is doing right now. */
  readonly state: MotionState;
  /**
   * The voice it follows: any audio stream or track (a call participant, a
   * bot's voice, a microphone you opened), or null for none. The stream is
   * only analysed, never played, and is left running when the pill lets go.
   */
  setAudio(source: MediaStream | MediaStreamTrack | null): Promise<void>;
  /** Opens the microphone itself. Rejects if the user or the browser says no. */
  useMicrophone(): Promise<void>;
  /** A stand-in voice, for trying it out. */
  useDemoVoice(): void;
  /** Loudness from elsewhere, 0..1 (a level your voice pipeline already has). Cheap to call every frame. */
  setLevel(level: number): void;
  /** Stop following any voice. */
  stopVoice(): void;
  readonly voice: VoiceSource;
  /** The loudness it is showing, 0..1. */
  readonly level: number;
  /** One bright ripple from the core, with a shiver: to mark a moment. */
  pulse(strength?: number): void;
  /** Bring it back to rest from wherever it has been turned or thrown. */
  reset(): void;
  /** Keep it from going to rest just yet. */
  wake(): void;
  /** Make its entrance (again): out of the dark, spinning in from further off. */
  appear(): void;
  /** Let the pointer take hold of it, or not. */
  setInteractive(on: boolean): void;
  /** Hold everything as it is: nothing moves, nothing is drawn. */
  setPaused(on: boolean): void;
  readonly paused: boolean;
  getStats(): PillStats;
  /** Helpers for tuning and measuring, used by the playground. Not part of what an app needs. */
  readonly debug: {
    readonly pacer: Pacer;
    /** While set, frames are only drawn when these helpers ask. */
    setManual(on: boolean): void;
    renderFrames(count: number, dt?: number): void;
    /** Milliseconds per whole moving frame along a fixed path, as throughput. */
    benchmark(frames?: number, batch?: number): number;
    /** Milliseconds per pass. */
    profile(runs?: number): Record<string, number>;
    captureTrace(seconds: number): Float32Array;
    captureMotion(seconds: number, frames?: number): Float32Array;
    /** Which world direction the picture sees at (u, v), 0..1 from the top left. */
    probe(u: number, v: number, mode?: number): { yaw: number; pitch: number; weight: number } | null;
    probeImage(mode?: number): { data: Float32Array; width: number; height: number };
    view(): { state: MotionState; rotation: number[]; camera: Vec3 };
  };
}

// Counts the engines made on each canvas, so that one being disposed can
// tell whether another has since taken the canvas over (React's strict mode
// mounts, unmounts and mounts again on the same element).
const generations = new WeakMap<HTMLCanvasElement, number>();

/**
 * Starts a pill on a canvas. Throws PillUnsupportedError if the browser can't
 * run it. Call start() to begin drawing and dispose() when done.
 */
export function createPillEngine(canvas: HTMLCanvasElement, options: PillEngineOptions = {}): PillEngine {
  const params: PillSettings = { ...defaultSettings, ...options.settings };
  const lights: Light[] = (options.lights ?? defaultLights).map((l) => ({ ...l }));
  const transparent = options.transparent ?? true;
  let interactive = options.interactive ?? true;
  let motionMode: MotionMode = options.motion ?? 'auto';

  const context = canvas.getContext('webgl2', {
    antialias: false,
    alpha: transparent,
    premultipliedAlpha: true,
    preserveDrawingBuffer: false,
    powerPreference: 'high-performance',
  });
  if (!context) throw new PillUnsupportedError('WebGL 2 is not available.');
  const gl: WebGL2RenderingContext = context;
  const generation = (generations.get(canvas) ?? 0) + 1;
  generations.set(canvas, generation);

  const mood = new MoodState(options.mood ?? 'neutral');
  const voice = new Voice();
  const motion = new Motion();
  const motes = new Motes();

  // What the tracer reads of the voice, two strips: its recent loudness,
  // newest first, which is read by distance from the dish's axis, and its
  // spectrum.
  const waveData = new Float32Array(WAVE_TEXELS * 2);
  const waveLoudness = waveData.subarray(0, WAVE_TEXELS);
  const waveSpectrum = waveData.subarray(WAVE_TEXELS);
  // Cloud noise the smudges, the coating and the wisps are cut from.
  const SMUDGE_NOISE = 256;
  const smudgeNoise = cloudNoise(SMUDGE_NOISE, 8, 5);

  // ---------------------------------------------------------------- GL resources

  // Everything made on the context. A lost context takes it all with it, so
  // it is made again from here when the context comes back.
  let traceProg!: Program;
  let taaProg!: Program;
  let downProg!: Program;
  let upProg!: Program;
  let flareProg!: Program;
  let compositeProg!: Program;
  let vao: WebGLVertexArrayObject | null = null;
  let waveTex: WebGLTexture | null = null;
  let smudgeTex: WebGLTexture | null = null;
  let floatLinear = false;

  function createResources() {
    if (!gl.getExtension('EXT_color_buffer_float')) {
      throw new PillUnsupportedError('Floating-point render targets are not available.');
    }
    floatLinear = !!gl.getExtension('OES_texture_float_linear');

    const withGeometry = (src: string) => src.replace('#include "geometry.glsl"', geometrySrc);
    traceProg = createProgram(gl, vertSrc, withGeometry(traceSrc));
    taaProg = createProgram(gl, vertSrc, withGeometry(taaSrc));
    downProg = createProgram(gl, vertSrc, downSrc);
    upProg = createProgram(gl, vertSrc, upSrc);
    flareProg = createProgram(gl, vertSrc, flareSrc);
    compositeProg = createProgram(gl, vertSrc, compositeSrc);
    vao = gl.createVertexArray();

    waveTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, waveTex);
    gl.texStorage2D(gl.TEXTURE_2D, 1, gl.R16F, WAVE_TEXELS, 2);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    smudgeTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, smudgeTex);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, SMUDGE_NOISE, SMUDGE_NOISE, 0, gl.RED, gl.UNSIGNED_BYTE, smudgeNoise);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
  }

  function deleteResources() {
    for (const p of [traceProg, taaProg, downProg, upProg, flareProg, compositeProg]) {
      if (p) gl.deleteProgram(p.program);
    }
    gl.deleteVertexArray(vao);
    gl.deleteTexture(waveTex);
    gl.deleteTexture(smudgeTex);
    deleteTargets();
  }

  // ---------------------------------------------------------------- targets

  // frameTarget: this frame's raw trace. history: TAA / accumulation ping-pong.
  let frameTarget: Target | null = null;
  let history: Target[] = [];
  let bloomMips: Target[] = [];
  let flareTarget: Target | null = null;
  let current = 0;

  function allocate(width: number, height: number) {
    if (frameTarget) deleteTarget(gl, frameTarget);
    history.forEach((t) => deleteTarget(gl, t));
    bloomMips.forEach((t) => deleteTarget(gl, t));
    if (flareTarget) deleteTarget(gl, flareTarget);
    frameTarget = createTarget(gl, width, height, gl.RGBA16F, gl.NEAREST);
    // 32-bit keeps long still accumulations exact; it needs the linear-filter
    // extension for the bicubic history fetch, 16-bit is the fallback.
    const historyFormat = floatLinear ? gl.RGBA32F : gl.RGBA16F;
    history = [0, 1].map(() => createTarget(gl, width, height, historyFormat, gl.LINEAR));
    bloomMips = [];
    let w = width >> 1, h = height >> 1;
    for (let i = 0; i < 7 && w >= 8 && h >= 8; i++) {
      bloomMips.push(createTarget(gl, w, h, gl.RGBA16F, gl.LINEAR));
      w >>= 1;
      h >>= 1;
    }
    // Shafts and streak are soft, so a quarter of the size is plenty.
    const quarter = bloomMips[Math.min(1, bloomMips.length - 1)];
    flareTarget = createTarget(gl, quarter.width, quarter.height, gl.RGBA16F, gl.LINEAR);
    current = 0;
  }

  function deleteTargets() {
    if (frameTarget) deleteTarget(gl, frameTarget);
    history.forEach((t) => deleteTarget(gl, t));
    bloomMips.forEach((t) => deleteTarget(gl, t));
    if (flareTarget) deleteTarget(gl, flareTarget);
    frameTarget = null;
    history = [];
    bloomMips = [];
    flareTarget = null;
  }

  // Set when the canvas's box may have changed (see the observers below).
  let sizeStale = true;
  let pixelRatio = 0;

  // Match the drawing size to the canvas's size on the page.
  function resize() {
    const ratio = window.devicePixelRatio || 1;
    if (!sizeStale && ratio === pixelRatio) return;
    sizeStale = false;
    pixelRatio = ratio;
    let scale = params.renderScale * Math.min(ratio, params.maxPixelRatio);
    const cssWidth = canvas.clientWidth, cssHeight = canvas.clientHeight;
    // A very large canvas is drawn at less than full size rather than at any cost.
    const pixels = cssWidth * cssHeight * scale * scale;
    if (pixels > params.maxPixels) scale *= Math.sqrt(params.maxPixels / pixels);
    const w = Math.max(32, Math.round(cssWidth * scale));
    const h = Math.max(32, Math.round(cssHeight * scale));
    if (w !== canvas.width || h !== canvas.height || !frameTarget) {
      canvas.width = w;
      canvas.height = h;
      allocate(w, h);
      invalidate();
    }
  }

  // The camera's view is fitted to the canvas: the pill's diameter takes
  // `fill` of the shorter side. This is the tangent of half the view's
  // height.
  function tanHalfFov() {
    return canvas.height / (params.camDistance * params.fill * Math.min(canvas.width, canvas.height));
  }

  const reduceMotionQuery =
    typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
  function reducedMotion() {
    return params.reducedMotion === 'auto' ? !!reduceMotionQuery?.matches : params.reducedMotion;
  }

  // ---------------------------------------------------------------- state

  let frameIndex = 0;
  let historyCount = 0; // frames averaged into the history while still
  let prevRot: Mat3 | null = null;
  let rot: Mat3 = motion.matrix(); // the dish's pose this frame
  // The dish shifting about is drawn as the camera shifting the other way.
  let camPos: Vec3 = [0, 0, params.camDistance];
  let prevCam: Vec3 = camPos;
  let dirty = true;
  let lightsStale = true;
  let soulClock = 0;
  // The inner light's slow stirring: how far its wisps have turned and slid.
  const stir = { turn: 0, slide: 0 };
  // 1 while the pill is awake, easing to 0 as it comes to rest; whatever moves
  // by itself in the light inside runs at this pace, so it winds down too.
  let liveliness = 1;
  // Seconds along a fixed path, while the console helpers measure or capture:
  // the same poses every time, whatever the pill happened to be doing.
  let scripted: number | null = null;
  // The pointer, wherever it is on the page, and whether it has hold of the pill.
  let pointerAt: { x: number; y: number } | null = null;
  let held: { id: number; x: number; y: number } | null = null;

  // Something about the picture changed that the history can't account for:
  // start it afresh.
  function invalidate() {
    historyCount = 0;
    dirty = true;
    lightsStale = true;
  }

  function same(a: ArrayLike<number>, b: ArrayLike<number>) {
    for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 1e-7) return false;
    return true;
  }

  function halton(index: number, base: number) {
    let f = 1, r = 0;
    for (let i = index; i > 0; i = Math.floor(i / base)) {
      f /= base;
      r += f * (i % base);
    }
    return r;
  }

  // The fixed path: a 16 second tumble from face-on, right over and back, which
  // shows the dish from every side.
  function measuringPath(seconds: number): Mat3 {
    const tau = (seconds / 16) % 1;
    const a = 2 * Math.PI * tau;
    const sinT = Math.sin(Math.PI * tau);
    const theta = 75 * DEG * sinT * (2 - sinT);
    const phi = a * 0.5;
    const tip = axisAngle([-Math.sin(phi), Math.cos(phi), 0], theta);
    return mul(tip, mul(rotX(Math.PI / 2), rotY(a)));
  }

  // Works out this frame's pose: `rot` and `camPos`.
  function updatePose(dt: number) {
    if (scripted !== null) {
      scripted += dt;
      rot = measuringPath(scripted);
      camPos = [0, 0, params.camDistance];
      return;
    }
    const fixed = params.mode === 'Reference pose' ? facing(params.refYaw, params.refPitch, params.refRoll * DEG) : null;
    // With motion reduced it holds still: no drift to wind down, either.
    const calm = reducedMotion();
    if (calm) motion.hush();
    motion.mode = calm ? 'rest' : motionMode;
    // The pointer has moved since the last frame: look at where it is now,
    // measured from the pill out to the edge of the window.
    if (pointerAt) {
      const box = canvas.getBoundingClientRect();
      const reach = 0.5 * Math.max(window.innerWidth, window.innerHeight);
      if (interactive && !held && !calm && params.pointerTilt > 0 && box.width > 0 && reach > 0) {
        // Straight towards the pointer, by more the further off it is:
        // quicker to respond near the pill, levelling off towards the edge.
        const dx = (pointerAt.x - (box.left + box.width / 2)) / reach;
        const dy = (pointerAt.y - (box.top + box.height / 2)) / reach;
        const far = Math.min(1, Math.hypot(dx, dy));
        const turn = far > 0 ? Math.sin((far * Math.PI) / 2) / Math.hypot(dx, dy) : 0;
        motion.look(dx * turn, dy * turn);
      }
      pointerAt = null;
    }
    motion.update(dt, voice, params, fixed);
    rot = motion.matrix();
    camPos = [-motion.pos[0], -motion.pos[1], params.camDistance - motion.pos[2]];
  }

  // Where the middle of the pill is on screen, 0..1 from the bottom left.
  function screenCentre(): [number, number] {
    const t = tanHalfFov();
    const aspect = canvas.width / canvas.height;
    return [0.5 - (0.5 * camPos[0]) / (camPos[2] * t * aspect), 0.5 - (0.5 * camPos[1]) / (camPos[2] * t)];
  }

  const MAX_LIGHTS = 8; // keep in sync with NUM_LIGHTS in pathtrace.frag

  const lightData = {
    dir: new Float32Array(MAX_LIGHTS * 3),
    right: new Float32Array(MAX_LIGHTS * 3),
    up: new Float32Array(MAX_LIGHTS * 3),
    size: new Float32Array(MAX_LIGHTS * 2),
    colA: new Float32Array(MAX_LIGHTS * 3),
    colB: new Float32Array(MAX_LIGHTS * 3),
    irr: new Float32Array(MAX_LIGHTS * 3),
    intensity: new Float32Array(MAX_LIGHTS),
    soft: new Float32Array(MAX_LIGHTS),
    grad: new Float32Array(MAX_LIGHTS),
  };

  // Only worked out again when a light, or the mood colouring them, changes.
  function lightUniforms() {
    const { dir, right, up, size, colA, colB, irr, intensity, soft, grad } = lightData;
    if (!lightsStale) return lightData;
    lightsStale = false;
    intensity.fill(0);
    lights.slice(0, MAX_LIGHTS).forEach((l, i) => {
      const f = dirFromAngles(l.yaw, l.pitch);
      const up0: Vec3 = Math.abs(f[1]) > 0.99 ? [0, 0, -1] : [0, 1, 0];
      let r = normalize(cross(f, up0));
      let u = cross(r, f);
      const roll = l.roll * DEG;
      const c = Math.cos(roll), s = Math.sin(roll);
      const r2: Vec3 = [r[0] * c + u[0] * s, r[1] * c + u[1] * s, r[2] * c + u[2] * s];
      const u2: Vec3 = [u[0] * c - r[0] * s, u[1] * c - r[1] * s, u[2] * c - r[2] * s];
      r = r2;
      u = u2;
      const a = mood.colour(l.colorTop);
      const b = mood.colour(l.colorBottom);
      const I = l.enabled ? l.intensity * params.rig : 0;
      // Solid angle of a rectangle on the unit tangent plane.
      const sx = l.width, sy = l.height;
      const omega = 4 * Math.atan((sx * sy) / Math.sqrt(1 + sx * sx + sy * sy));
      for (let k = 0; k < 3; k++) {
        dir[i * 3 + k] = f[k];
        right[i * 3 + k] = r[k];
        up[i * 3 + k] = u[k];
        colA[i * 3 + k] = a[k];
        colB[i * 3 + k] = b[k];
        irr[i * 3 + k] = (((a[k] + b[k]) * 0.5 * I * omega) / Math.PI) * 0.5;
      }
      size[i * 2] = sx;
      size[i * 2 + 1] = sy;
      intensity[i] = I;
      soft[i] = l.soft;
      grad[i] = l.gradient;
    });
    return lightData;
  }

  // Smooth wandering value in -1..1.
  function wobble(t: number) {
    return (Math.sin(t) + Math.sin(t * 1.73 + 1.1) + Math.sin(t * 2.89 + 4.2)) / 3;
  }

  // How bright a unit of the soul's colours comes out, chosen so the core at
  // rest is a soft glow and a loud voice makes it bloom.
  const SOUL_GAIN = 10;
  const MOTE_RADIUS = 0.01;

  // The hollow of the dish, which the light inside fills: from the floor to the
  // rim, just short of the wall.
  function soulBox() {
    const top = params.height / 2;
    const bottom = -top + params.floor;
    return { centre: (top + bottom) / 2, half: (top - bottom) / 2, reach: (1 - params.wall) * 0.985 };
  }

  function setSoulUniforms(loc: (name: string) => WebGLUniformLocation | null) {
    const on = params.soul && params.soulIntensity > 0;
    gl.uniform1i(loc('uSoulSteps'), on ? Math.max(1, Math.round(params.soulSteps)) : 0);
    gl.activeTexture(gl.TEXTURE2);
    gl.bindTexture(gl.TEXTURE_2D, waveTex);
    gl.uniform1i(loc('uWave'), 2);
    if (on) {
      const tempo = mood.trait('tempo');
      const restless = mood.trait('restless');
      voice.fillWave(waveLoudness, (1.5 * params.soulTravel) / tempo);
      // Deepen the troughs, so syllables part into separate ripples.
      for (let i = 0; i < WAVE_TEXELS; i++) waveLoudness[i] = 1.3 * Math.pow(waveLoudness[i], 1.6);
      // The spectrum goes in as how far each part stands above or below its
      // average, so it reshapes the core's edge without swelling it.
      voice.fillSpectrum(waveSpectrum);
      let mean = 0;
      for (let i = 0; i < WAVE_TEXELS; i++) mean += waveSpectrum[i] / WAVE_TEXELS;
      for (let i = 0; i < WAVE_TEXELS; i++) waveSpectrum[i] = 2.5 * (waveSpectrum[i] - mean);
      // Smoothed, so it pulls the edge into soft lobes rather than spikes.
      for (let pass = 0; pass < 3; pass++) {
        let before = waveSpectrum[0];
        for (let i = 0; i < WAVE_TEXELS - 1; i++) {
          const here = waveSpectrum[i];
          waveSpectrum[i] = 0.25 * before + 0.5 * here + 0.25 * waveSpectrum[i + 1];
          before = here;
        }
      }
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, WAVE_TEXELS, 2, gl.RED, gl.FLOAT, waveData);

      const box = soulBox();
      const breath = 0.5 + 0.5 * Math.sin((soulClock * 2 * Math.PI) / 4.6);
      const radius =
        params.soulRadius * (1 + mood.trait('swell') * (0.55 * voice.energy + 0.35 * voice.level) + 0.06 * breath);
      gl.uniform4f(loc('uSoulBox'), box.centre, box.half, box.reach, 1 / (radius * radius));

      const unsteady = 1 + mood.trait('flicker') * 0.25 * wobble(soulClock * 23) * (0.35 + voice.energy);
      const core =
        (params.soulIdle * (0.6 + 0.4 * breath) + 1.1 * voice.level + 0.5 * voice.energy + 1.5 * voice.burst) *
        unsteady * params.soulCore * params.soulIntensity * SOUL_GAIN;
      const aura = params.soulRipple * params.soulIntensity * SOUL_GAIN;
      const c = mood.core();
      const a = mood.aura();
      gl.uniform3f(loc('uSoulCore'), c[0] * core, c[1] * core, c[2] * core);
      gl.uniform3f(loc('uSoulAura'), a[0] * aura, a[1] * aura, a[2] * aura);

      // The fronts lean two and three ways at once, turning slowly; the voice's
      // pitch pushes them about.
      const bend = params.soulWarp * restless * (0.6 + 0.4 * Math.min(1, 2 * voice.energy));
      const a2 = soulClock * 0.31 * tempo + 1.3 * voice.bands[0];
      const a3 = -soulClock * 0.47 * tempo + 2 * voice.bands[2];
      gl.uniform4f(
        loc('uSoulWarp'),
        bend * Math.cos(a2), bend * Math.sin(a2), 0.6 * bend * Math.cos(a3), 0.6 * bend * Math.sin(a3),
      );
      // The glass's own glow: faint at rest, swelling while the voice carries on.
      const body =
        params.soulBody * params.soulIntensity * (0.15 + voice.energy + 0.4 * voice.level) * (0.9 + 0.1 * breath);
      gl.uniform3f(loc('uEmit'), a[0] * body, a[1] * body, a[2] * body);
      gl.uniform1f(loc('uSoulGlass'), params.soulGlass);
      gl.uniform1f(loc('uSoulSurface'), params.soulSurface);

      // Wisps wind tighter and glow more as the voice carries on; the flare
      // patterns turn slowly against each other.
      gl.uniform4f(
        loc('uSoulStir'),
        stir.turn, 1.6 + voice.energy,
        params.soulWisps * (0.04 + 0.5 * voice.energy + 0.15 * voice.level), params.soulFlare,
      );
      const f2 = soulClock * 0.21;
      const f3 = -soulClock * 0.33;
      gl.uniform4f(loc('uSoulFlare'), Math.cos(f2), Math.sin(f2), Math.cos(f3), Math.sin(f3));
      gl.uniform4f(loc('uSoulDrift'), stir.slide * 1.1, stir.slide * 0.7, -stir.slide * 0.9, stir.slide * 1.3);

      const speck = 3.5 * params.soulIntensity;
      gl.uniform1i(loc('uMoteCount'), params.soulMotes > 0 && liveliness > 0 ? MOTE_COUNT : 0);
      gl.uniform4fv(loc('uMotes'), motes.data);
      gl.uniform3f(
        loc('uMoteColor'),
        (0.6 * c[0] + 0.4 * a[0]) * speck, (0.6 * c[1] + 0.4 * a[1]) * speck, (0.6 * c[2] + 0.4 * a[2]) * speck,
      );
      gl.uniform1f(loc('uMoteFalloff'), 1 / (MOTE_RADIUS * MOTE_RADIUS));
    } else {
      gl.uniform3f(loc('uEmit'), 0, 0, 0);
    }
    gl.activeTexture(gl.TEXTURE0);
  }

  // ---------------------------------------------------------------- passes

  function drawTriangle() {
    gl.bindVertexArray(vao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  let debugMode = 0;

  type Rect = [number, number, number, number]; // x, y, width, height in pixels

  // Screen rectangle that can contain the dish this frame: its bounding box
  // corners projected with the same camera the shaders use (at +Z, looking down
  // -Z), plus a margin for jitter and the TAA neighbourhood. Pixels outside it
  // would only ever see the black background, so the passes skip them.
  function dishRect(width: number, height: number): Rect {
    const t = tanHalfFov();
    const aspect = width / height;
    const h2 = params.height / 2;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const cx of [-1, 1]) for (const cy of [-h2, h2]) for (const cz of [-1, 1]) {
      const wx = rot[0] * cx + rot[3] * cy + rot[6] * cz;
      const wy = rot[1] * cx + rot[4] * cy + rot[7] * cz;
      const wz = rot[2] * cx + rot[5] * cy + rot[8] * cz;
      const depth = camPos[2] - wz;
      if (depth < 0.05) return [0, 0, width, height];
      const sx = (((wx - camPos[0]) / (depth * t * aspect)) * 0.5 + 0.5) * width;
      const sy = (((wy - camPos[1]) / (depth * t)) * 0.5 + 0.5) * height;
      x0 = Math.min(x0, sx); x1 = Math.max(x1, sx);
      y0 = Math.min(y0, sy); y1 = Math.max(y1, sy);
    }
    const margin = 4;
    const left = Math.max(0, Math.floor(x0) - margin);
    const bottom = Math.max(0, Math.floor(y0) - margin);
    const right = Math.min(width, Math.ceil(x1) + margin);
    const top = Math.min(height, Math.ceil(y1) + margin);
    return [left, bottom, Math.max(0, right - left), Math.max(0, top - bottom)];
  }

  // Clear the whole target, then limit drawing to `rect`.
  function beginScissored(target: Target, rect: Rect) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, target.fb);
    gl.viewport(0, 0, target.width, target.height);
    gl.disable(gl.SCISSOR_TEST);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.SCISSOR_TEST);
    gl.scissor(rect[0], rect[1], rect[2], rect[3]);
  }

  const CAM_BASIS = new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1]);

  // Geometry and camera uniforms shared by the tracer and the TAA resolve.
  function setSceneUniforms(loc: (name: string) => WebGLUniformLocation | null) {
    gl.uniformMatrix3fv(loc('uObjRot'), false, rot);
    gl.uniform3f(loc('uCamPos'), camPos[0], camPos[1], camPos[2]);
    gl.uniformMatrix3fv(loc('uCamBasis'), false, CAM_BASIS);
    gl.uniform1f(loc('uTanHalfFov'), tanHalfFov());
    gl.uniform1f(loc('uRadius'), 1);
    gl.uniform1f(loc('uHeight'), params.height);
    gl.uniform1f(loc('uWall'), params.wall);
    gl.uniform1f(loc('uFloor'), params.floor);
    // Keep the roundings from overlapping: two edges share the wall's thickness
    // and the height, and the fillet sits between floor and rim.
    const bevel = Math.max(0, Math.min(params.bevel, params.wall / 2 - 1e-4, params.height / 2 - 1e-4));
    const fillet = Math.max(0, Math.min(params.fillet, 1 - params.wall - 1e-4, params.height - params.floor - bevel - 1e-4));
    gl.uniform1f(loc('uBevel'), bevel);
    gl.uniform1f(loc('uFillet'), fillet);
  }

  const MAX_SAMPLES = 16; // keep in sync with MAX_SAMPLES in pathtrace.frag

  // `count` samples per pixel, stratified: a Hammersley set across the pixel
  // shifted by `shift`, all at the centre of each wavelength band (still frames
  // randomise the wavelength in the shader instead).
  function samplePattern(count: number, shift: [number, number]) {
    const n = Math.max(1, Math.min(MAX_SAMPLES, Math.round(count)));
    const data = new Float32Array(MAX_SAMPLES * 3);
    for (let s = 0; s < n; s++) {
      data[s * 3] = (shift[0] + (s + 0.5) / n) % 1;
      data[s * 3 + 1] = (shift[1] + halton(s, 2) + 0.5 / n) % 1;
      data[s * 3 + 2] = 0.5;
    }
    return { data, count: n };
  }

  // Pixel-centre single sample, for probes and deterministic captures.
  const CENTRE_SAMPLE = samplePattern(1, [0, 0]);

  function tracePass(samples: { data: Float32Array; count: number }, stochastic: boolean) {
    const { program, loc } = traceProg;
    const dst = frameTarget!;
    gl.useProgram(program);
    // The debug probes want every pixel.
    beginScissored(dst, debugMode ? [0, 0, dst.width, dst.height] : dishRect(dst.width, dst.height));
    gl.disable(gl.BLEND);

    gl.uniform2f(loc('uResolution'), dst.width, dst.height);
    gl.uniform1ui(loc('uFrame'), frameIndex);
    gl.uniform1i(loc('uSpp'), samples.count);
    gl.uniform3fv(loc('uSamples'), samples.data);
    gl.uniform1i(loc('uStochastic'), stochastic ? 1 : 0);
    setSceneUniforms(loc);

    gl.uniform1f(loc('uIor'), params.ior);
    gl.uniform1f(loc('uDispersion'), params.dispersion);
    const tint = mood.colour(params.absorbColor);
    gl.uniform3f(
      loc('uSigma'),
      -Math.log(Math.max(tint[0], 1e-3)) * params.absorbDensity,
      -Math.log(Math.max(tint[1], 1e-3)) * params.absorbDensity,
      -Math.log(Math.max(tint[2], 1e-3)) * params.absorbDensity,
    );
    gl.uniform1f(loc('uRoughness'), params.roughness);
    const glow = mood.colour(params.glowColor);
    gl.uniform3f(loc('uGlow'), glow[0] * params.glow, glow[1] * params.glow, glow[2] * params.glow);
    gl.uniform1f(loc('uGlowDensity'), params.glowDensity);

    gl.uniform1f(loc('uScratchDensity'), params.scratchDensity);
    gl.uniform1f(loc('uWallScratches'), params.wallScratches);
    gl.uniform1f(loc('uScratchWidth'), params.scratchWidth);
    gl.uniform1f(loc('uScratchSlope'), params.scratchSlope);
    gl.uniform1f(loc('uScratchScale'), params.scratchScale);
    gl.uniform1f(loc('uScratchLength'), params.scratchLength);
    gl.uniform1f(loc('uScratchStrength'), params.scratchStrength);
    gl.uniform1f(loc('uSmudge'), params.smudge);
    gl.uniform1f(loc('uSmudgeScale'), params.smudgeScale);
    gl.uniform1f(loc('uHaze'), params.haze);
    // The coating's rainbow suits a colourless pill best; a strongly coloured
    // mood keeps less of it, so its own colour stays clean.
    const sheen = params.film * mood.trait('sheen');
    gl.uniform4f(loc('uFilm'), sheen, params.filmThickness, params.filmVariation, sheen > 0 ? params.filmShine : 0);

    gl.uniform1i(loc('uMaxDepth'), params.maxDepth);
    gl.uniform1i(loc('uMaxSegments'), params.maxSegments);
    gl.uniform1f(loc('uMinWeight'), params.minWeight);
    gl.uniform1i(loc('uDebug'), debugMode);
    gl.activeTexture(gl.TEXTURE3);
    gl.bindTexture(gl.TEXTURE_2D, smudgeTex);
    gl.uniform1i(loc('uSmudgeNoise'), 3);
    setSoulUniforms(loc);

    const L = lightUniforms();
    gl.uniform3fv(loc('uLightDir'), L.dir);
    gl.uniform3fv(loc('uLightRight'), L.right);
    gl.uniform3fv(loc('uLightUp'), L.up);
    gl.uniform2fv(loc('uLightSize'), L.size);
    gl.uniform3fv(loc('uLightColA'), L.colA);
    gl.uniform3fv(loc('uLightColB'), L.colB);
    gl.uniform3fv(loc('uLightIrr'), L.irr);
    gl.uniform1fv(loc('uLightIntensity'), L.intensity);
    gl.uniform1fv(loc('uLightSoft'), L.soft);
    gl.uniform1fv(loc('uLightGrad'), L.grad);
    gl.uniform3f(loc('uBackground'), 0, 0, 0);

    drawTriangle();
    gl.disable(gl.SCISSOR_TEST);
  }

  // Where the history holds anything but black (set by the TAA pass).
  let historyRect: Rect | null = null;

  // Folds the new frame into the history: TAA while moving, a plain running
  // average while still.
  function taaPass(alpha: number, reproject: boolean) {
    const { program, loc } = taaProg;
    const dst = history[1 - current];
    gl.useProgram(program);
    historyRect = dishRect(dst.width, dst.height);
    beginScissored(dst, historyRect);
    gl.disable(gl.BLEND);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, frameTarget!.tex);
    gl.uniform1i(loc('uCurrent'), 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, history[current].tex);
    gl.uniform1i(loc('uHistory'), 1);
    gl.activeTexture(gl.TEXTURE0);
    gl.uniform2f(loc('uResolution'), dst.width, dst.height);
    gl.uniform1f(loc('uAlpha'), alpha);
    gl.uniform1i(loc('uReproject'), reproject ? 1 : 0);
    gl.uniform1f(loc('uClipGamma'), params.clipGamma);
    setSceneUniforms(loc);
    gl.uniformMatrix3fv(loc('uPrevObjRot'), false, prevRot ?? rot);
    gl.uniform3f(loc('uPrevCamPos'), prevCam[0], prevCam[1], prevCam[2]);
    drawTriangle();
    gl.disable(gl.SCISSOR_TEST);
    current = 1 - current;
  }

  function bloomPass() {
    gl.disable(gl.BLEND);
    gl.useProgram(downProg.program);
    gl.activeTexture(gl.TEXTURE0);
    gl.uniform1i(downProg.loc('uSrc'), 0);
    let src: Target = history[current];
    bloomMips.forEach((dst, i) => {
      if (i === 0 && historyRect) {
        // Half-res, so halve the rectangle; the 13 taps reach two source texels
        // out, i.e. one texel here, and bilinear filtering one more.
        const r = historyRect;
        const x0 = Math.max(0, Math.floor(r[0] / 2) - 3);
        const y0 = Math.max(0, Math.floor(r[1] / 2) - 3);
        const x1 = Math.min(dst.width, Math.ceil((r[0] + r[2]) / 2) + 3);
        const y1 = Math.min(dst.height, Math.ceil((r[1] + r[3]) / 2) + 3);
        beginScissored(dst, [x0, y0, Math.max(0, x1 - x0), Math.max(0, y1 - y0)]);
      } else {
        gl.bindFramebuffer(gl.FRAMEBUFFER, dst.fb);
        gl.viewport(0, 0, dst.width, dst.height);
      }
      gl.bindTexture(gl.TEXTURE_2D, src.tex);
      gl.uniform2f(downProg.loc('uTexel'), 1 / src.width, 1 / src.height);
      gl.uniform1i(downProg.loc('uKaris'), i === 0 ? 1 : 0);
      drawTriangle();
      gl.disable(gl.SCISSOR_TEST);
      src = dst;
    });

    gl.useProgram(upProg.program);
    gl.uniform1i(upProg.loc('uSrc'), 0);
    gl.uniform1f(upProg.loc('uRadius'), params.bloomRadius);
    gl.uniform1f(upProg.loc('uWeight'), 1);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    for (let i = bloomMips.length - 1; i > 0; i--) {
      const from = bloomMips[i];
      const to = bloomMips[i - 1];
      gl.bindFramebuffer(gl.FRAMEBUFFER, to.fb);
      gl.viewport(0, 0, to.width, to.height);
      gl.bindTexture(gl.TEXTURE_2D, from.tex);
      gl.uniform2f(upProg.loc('uTexel'), 1 / from.width, 1 / from.height);
      drawTriangle();
    }
    gl.disable(gl.BLEND);
  }

  // Shafts of light from the pill's middle and a streak across its highlights,
  // both brighter while the voice carries on.
  function flarePass() {
    const { program, loc } = flareProg;
    const dst = flareTarget!;
    const src = bloomMips[Math.min(1, bloomMips.length - 1)];
    gl.useProgram(program);
    gl.bindFramebuffer(gl.FRAMEBUFFER, dst.fb);
    gl.viewport(0, 0, dst.width, dst.height);
    gl.disable(gl.BLEND);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, src.tex);
    gl.uniform1i(loc('uSrc'), 0);
    gl.uniform2f(loc('uTexel'), 1 / src.width, 1 / src.height);
    const centre = screenCentre();
    gl.uniform2f(loc('uCentre'), centre[0], centre[1]);
    const lit = params.soul ? 0.25 + 1.6 * voice.energy + 0.6 * voice.level + voice.burst : 0.25;
    // The bloom chain sums its levels; scale to match (see compositePass).
    const scale = 1 / Math.max(1, bloomMips.length - 1);
    gl.uniform1f(loc('uShafts'), params.shafts * lit * scale);
    gl.uniform1f(loc('uShaftReach'), params.shaftReach);
    // About the middle half of the pill, as it looks from the camera's distance.
    gl.uniform1f(loc('uSourceSize'), 0.28 / (camPos[2] * tanHalfFov()));
    gl.uniform1f(loc('uAspect'), dst.width / dst.height);
    gl.uniform1f(loc('uStreak'), params.streak * (0.5 + voice.energy) * scale);
    drawTriangle();
  }

  function compositePass() {
    const { program, loc } = compositeProg;
    gl.useProgram(program);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, history[current].tex);
    gl.uniform1i(loc('uHdr'), 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, bloomMips[0].tex);
    gl.uniform1i(loc('uBloom'), 1);
    gl.activeTexture(gl.TEXTURE2);
    gl.bindTexture(gl.TEXTURE_2D, flareTarget!.tex);
    gl.uniform1i(loc('uFlare'), 2);
    const centre = screenCentre();
    gl.uniform2f(loc('uCentre'), centre[0], centre[1]);
    gl.uniform1f(loc('uAspect'), canvas.width / canvas.height);
    const air = mood.aura();
    const halo = params.soul ? params.halo * (0.04 + 0.22 * voice.energy + 0.3 * voice.burst) : 0;
    gl.uniform3f(loc('uHalo'), air[0] * halo, air[1] * halo, air[2] * halo);
    gl.uniform1f(loc('uHaloSize'), 0.3);
    gl.uniform1f(loc('uAberration'), params.aberration);
    // During the entrance the whole picture comes up out of the dark.
    gl.uniform1f(loc('uExposure'), params.exposure * (scripted !== null ? 1 : motion.reveal));
    gl.uniform1i(loc('uTransparent'), transparent ? 1 : 0);
    // The mip chain sums ~N levels; normalise so strength stays intuitive.
    gl.uniform1f(loc('uBloomStrength'), params.bloomStrength / Math.max(1, bloomMips.length));
    gl.uniform1i(loc('uToneMap'), ['AgX', 'AgX punchy', 'ACES'].indexOf(params.toneMap));
    gl.uniform1f(loc('uSaturation'), params.saturation);
    gl.uniform1f(loc('uGrain'), params.grain);
    gl.uniform1ui(loc('uFrame'), frameIndex);
    drawTriangle();
    gl.activeTexture(gl.TEXTURE0);
  }

  // ---------------------------------------------------------------- loop

  const pacer = new Pacer(() => params, MAX_SAMPLES);
  let raf = 0;
  let running = false;
  let started = false;
  let disposed = false;
  let lost = false;      // the graphics context is gone for now
  let paused = false;
  let onScreen = true;
  let last = 0;
  let fps = 60;
  let manual = false;    // the debug helpers drive frames themselves while set
  let lastFrameLive = false; // the last frame was one of a moving picture, not a still
  let stillFrame = false;
  let reported: MotionState | null = null;

  function motionSamples() {
    return params.autoQuality ? Math.min(pacer.spp, params.motionSpp) : params.motionSpp;
  }

  function frame(now: number) {
    raf = requestAnimationFrame(frame);
    if (manual) return;
    if (paused || !onScreen || lost) {
      last = now;
      return;
    }
    if (pacer.tick(now)) return; // timing the display
    const interval = now - last;
    const auto = params.autoQuality;
    if (auto && !pacer.due(interval)) return; // not this refresh's turn
    const dt = Math.min(0.1, interval / 1000);
    last = now;
    fps += (1 / Math.max(dt, 1e-3) - fps) * 0.05;

    const moving = renderFrame(dt);
    // Long gaps (hidden tab, debugger) say nothing about rendering speed.
    if (auto && moving && interval < 250) pacer.judge(pacer.isLate(interval), now);

    if (motion.state !== reported) {
      reported = motion.state;
      options.onStateChange?.(reported);
    }
  }

  // One step of the loop: advance time by dt, trace, resolve, post. Returns
  // whether it drew a frame of a moving picture (rather than a still, or nothing).
  function renderFrame(dt: number) {
    resize();

    // The voice first: the pose and the light inside both follow it.
    voice.gain = params.voiceGain;
    voice.update(dt);
    if (mood.update(dt, params.moodSeconds)) lightsStale = true;
    updatePose(dt);

    // Whatever moves by itself in the light inside winds down as the pill
    // comes to rest, and stops.
    liveliness = scripted !== null ? 1 : motion.ease;
    const drift = dt * liveliness;
    soulClock += drift;
    const tempo = mood.trait('tempo');
    stir.turn += drift * 0.22 * tempo * (1 + 1.5 * voice.energy);
    stir.slide += drift * 0.011 * tempo;
    const box = soulBox();
    motes.update(
      drift, { level: voice.level, energy: voice.energy, tempo, restless: mood.trait('restless') },
      box.centre, box.half, box.reach, params.soulMotes * liveliness,
    );

    const moved = prevRot !== null && !(same(rot, prevRot) && same(camPos, prevCam));
    // The picture stands still only when nothing is left to change it: the
    // dish at rest, the light inside wound down, the last of the voice gone
    // and the mood arrived. Then it is refined instead of redrawn.
    const soulOn = params.soul && params.soulIntensity > 0;
    const live =
      moved || mood.transitioning || motion.appearing || (soulOn && (liveliness > 0 || !voice.settled));

    // Moving frames (and the first after a change) are anti-aliased within the
    // frame by a fixed stratified sample set, so they stand on their own; TAA,
    // if enabled, only smooths what's left. Still frames add one jittered,
    // randomised sample set per frame to a running average.
    let alpha = 1;
    let reproject = false;
    let stochastic = false;
    // With TAA on, the motion pattern shifts every frame so the history keeps
    // gaining new sample positions instead of re-averaging the same ones.
    const k = (frameIndex % 16) + 1;
    const motionShift: [number, number] = params.taaBlend < 1 ? [halton(k, 2), halton(k, 3)] : [0, 0];
    let samples = samplePattern(motionSamples(), motionShift);
    let render = true;
    if (dirty || historyCount === 0 || prevRot === null) {
      historyCount = 1;
    } else if (live) {
      alpha = params.taaBlend;
      reproject = true;
      // Once it stops, carry on averaging as if the history held this many frames.
      historyCount = Math.max(1, Math.round(1 / params.taaBlend));
    } else if (historyCount < params.maxSamples) {
      alpha = 1 / (historyCount + 1);
      stochastic = true;
      samples = samplePattern(params.spp, [halton(historyCount, 2), halton(historyCount, 3)]);
      historyCount++;
    } else {
      render = false;
    }

    if (render) {
      tracePass(samples, stochastic);
      taaPass(alpha, reproject);
      bloomPass();
      flarePass();
      compositePass();
      frameIndex++;
    }
    prevRot = rot;
    prevCam = camPos;
    dirty = false;
    lastFrameLive = live;

    stillFrame = !live;
    return render && live;
  }

  // ---------------------------------------------------------------- what a host drives it with

  function setMood(name: Mood, immediate = false) {
    if (!(name in MOODS)) throw new Error(`Unknown mood "${name}". Try: ${MOOD_NAMES.join(', ')}`);
    const changed = name !== mood.target;
    mood.set(name, immediate);
    lightsStale = true;
    // A change of heart shows: it turns once as the colour comes over it,
    // with one bright ripple from the core.
    if (changed && !immediate) {
      voice.pulse(0.6);
      if (reducedMotion()) motion.wake();
      else motion.turnOnce(params.turnSeconds);
    }
  }

  function setMotion(mode: MotionMode) {
    if (!MOTION_MODES.includes(mode)) throw new Error(`Unknown motion "${mode}". Try: ${MOTION_MODES.join(', ')}`);
    motionMode = mode;
    motion.wake();
  }

  // Make its entrance (again): out of the dark, spinning in from further off.
  function appear() {
    const still = reducedMotion();
    motion.appear(params.introSeconds, still ? 0 : params.introTurns, still ? 0 : params.introDepth);
  }

  // Change settings. (They can also be written to directly, on `settings`
  // and `lights`; call invalidate() afterwards.)
  function configure(changes: Partial<PillSettings>) {
    const repace = 'motionSpp' in changes || 'prefer' in changes;
    Object.assign(params, changes);
    sizeStale = true;
    invalidate();
    if (repace) pacer.reset(performance.now());
  }

  // ---------------------------------------------------------------- pointer

  // Where a mouse or pen last moved to, anywhere on the page, if it has moved
  // since the last frame (see updatePose). Touches don't hover, so don't count.
  function onPointerAbout(e: PointerEvent) {
    if (e.pointerType !== 'touch') pointerAt = { x: e.clientX, y: e.clientY };
  }

  // Take hold of the pill and turn it; let go and it carries on with whatever
  // spin it was given, then comes home. Double-click brings it home at once.

  function onPointerDown(e: PointerEvent) {
    if (!interactive || (e.pointerType === 'mouse' && e.button !== 0)) return;
    canvas.setPointerCapture(e.pointerId);
    held = { id: e.pointerId, x: e.clientX, y: e.clientY };
    motion.grab();
  }

  function onPointerMove(e: PointerEvent) {
    if (!held || e.pointerId !== held.id) return;
    // Dragging across the pill's width turns it about a third of the way round.
    const perPixel = 2.2 / Math.max(1, params.fill * Math.min(canvas.clientWidth, canvas.clientHeight));
    motion.drag((e.clientX - held.x) * perPixel, (e.clientY - held.y) * perPixel);
    held.x = e.clientX;
    held.y = e.clientY;
  }

  function onPointerUp(e: PointerEvent) {
    if (!held || e.pointerId !== held.id) return;
    held = null;
    motion.release();
  }

  function onDoubleClick() {
    if (interactive) motion.reset();
  }

  // ---------------------------------------------------------------- lifecycle

  function onContextLost(e: Event) {
    e.preventDefault(); // ask for it back
    lost = true;
  }

  function onContextRestored() {
    // Everything made on the old context went with it.
    frameTarget = null;
    history = [];
    bloomMips = [];
    flareTarget = null;
    try {
      createResources();
    } catch {
      return; // still unusable; stay dark
    }
    lost = false;
    sizeStale = true;
    lightsStale = true;
    prevRot = null;
    invalidate();
  }

  // Browsers hold audio back until the page has been clicked or typed in.
  const resumeAudio = () => voice.resume();
  const onVisibility = () => {
    // Back in view, perhaps on another screen: time the display again.
    if (!document.hidden) pacer.measure();
  };
  const onMotionPreference = () => motion.wake();

  const sizeObserver =
    typeof ResizeObserver === 'function'
      ? new ResizeObserver(() => {
          sizeStale = true;
          // The window may have moved to another display, too.
          if (running && !manual) pacer.measure();
        })
      : null;
  const viewObserver =
    typeof IntersectionObserver === 'function'
      ? new IntersectionObserver((entries) => {
          onScreen = entries[entries.length - 1].isIntersecting;
        })
      : null;

  canvas.addEventListener('webglcontextlost', onContextLost);
  canvas.addEventListener('webglcontextrestored', onContextRestored);
  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('dblclick', onDoubleClick);
  window.addEventListener('pointermove', onPointerAbout, { passive: true });
  window.addEventListener('pointerdown', resumeAudio, { passive: true });
  window.addEventListener('keydown', resumeAudio, { passive: true });
  document.addEventListener('visibilitychange', onVisibility);
  reduceMotionQuery?.addEventListener('change', onMotionPreference);
  sizeObserver?.observe(canvas);
  viewObserver?.observe(canvas);

  if (gl.isContextLost()) lost = true;
  else createResources();

  // Begin drawing. The first time, it makes its entrance (unless told not to).
  function start() {
    if (running || disposed) return;
    running = true;
    if (!started) {
      started = true;
      if (options.intro ?? true) appear();
      if (!lost) renderFrame(0); // something to show at once
    }
    last = performance.now();
    pacer.measure();
    raf = requestAnimationFrame(frame);
  }

  function stop() {
    running = false;
    cancelAnimationFrame(raf);
  }

  // Stop, and let go of everything: listeners, audio, and what was made on
  // the graphics context.
  function dispose() {
    if (disposed) return;
    stop();
    disposed = true;
    canvas.removeEventListener('webglcontextlost', onContextLost);
    canvas.removeEventListener('webglcontextrestored', onContextRestored);
    canvas.removeEventListener('pointerdown', onPointerDown);
    canvas.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('pointerup', onPointerUp);
    canvas.removeEventListener('pointercancel', onPointerUp);
    canvas.removeEventListener('dblclick', onDoubleClick);
    window.removeEventListener('pointermove', onPointerAbout);
    window.removeEventListener('pointerdown', resumeAudio);
    window.removeEventListener('keydown', resumeAudio);
    document.removeEventListener('visibilitychange', onVisibility);
    reduceMotionQuery?.removeEventListener('change', onMotionPreference);
    sizeObserver?.disconnect();
    viewObserver?.disconnect();
    voice.dispose();
    if (!gl.isContextLost()) deleteResources();
    // Hand the context back promptly (browsers allow only a handful), unless
    // another engine has taken this canvas over in the meantime.
    setTimeout(() => {
      if (generations.get(canvas) === generation) gl.getExtension('WEBGL_lose_context')?.loseContext();
    }, 0);
  }

  function getStats(): PillStats {
    return {
      width: canvas.width,
      height: canvas.height,
      fps,
      frames: frameIndex,
      state: motion.state,
      still: stillFrame,
      samples: historyCount,
      maxSamples: params.maxSamples,
      spp: motionSamples(),
      every: params.autoQuality ? pacer.every : 1,
      refresh: pacer.refresh,
      mood: mood.target,
      voice: voice.source,
      level: voice.level,
    };
  }

  // ---------------------------------------------------------------- looking into it

  // Helpers for tuning and measuring, used by the playground. Not part of
  // what an app needs.

  function readTarget(t: Target) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, t.fb);
    const data = new Float32Array(t.width * t.height * 4);
    gl.readPixels(0, 0, t.width, t.height, gl.RGBA, gl.FLOAT, data);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return data;
  }

  // Which world direction does the image see at (u, v)? (0..1 from top-left.)
  // mode 1: strongest escaping path, mode 2: first-surface mirror direction.
  // Answers in the same yaw / pitch terms the lights use.
  function probe(u: number, v: number, mode = 1) {
    const { data, width, height } = probeImage(mode);
    const i = (Math.floor((1 - v) * height) * width + Math.floor(u * width)) * 4;
    const [x, y, z, w] = data.slice(i, i + 4);
    if (w === 0) return null;
    return {
      yaw: +(Math.atan2(x, z) / DEG).toFixed(1),
      pitch: +(Math.asin(Math.max(-1, Math.min(1, y))) / DEG).toFixed(1),
      weight: +w.toFixed(3),
    };
  }

  // Full-frame version of probe(): xyz direction + weight per pixel, bottom-up rows.
  function probeImage(mode = 1) {
    debugMode = mode;
    tracePass(CENTRE_SAMPLE, false);
    debugMode = 0;
    invalidate();
    return { data: readTarget(frameTarget!), width: frameTarget!.width, height: frameTarget!.height };
  }

  // Render frames without waiting for requestAnimationFrame (which stops when
  // the page is hidden), e.g. renderFrames(16, 0) to converge a still.
  // Wait for the GPU to finish everything submitted so far.
  function drainGpu() {
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
  }

  // Frames are normally paced by requestAnimationFrame. Driven from a loop,
  // nothing stops them queueing faster than the GPU finishes them, and a long
  // enough queue trips the macOS GPU watchdog (which then bans the browser's
  // GPU process). So wait for each frame before starting the next.
  function renderFrames(count: number, dt = 1 / 60) {
    for (let i = 0; i < count; i++) {
      renderFrame(dt);
      drainGpu();
    }
  }

  // Raw trace at `t` seconds along the fixed path, with pixel-centre rays and no
  // randomness, so two builds can be compared pixel for pixel.
  function captureTrace(t: number) {
    scripted = t;
    updatePose(0);
    tracePass(CENTRE_SAMPLE, false);
    scripted = null;
    invalidate();
    return readTarget(frameTarget!);
  }

  // TAA history after `frames` steps along the fixed path from `t` seconds in.
  // Leaves the path running; benchmark() carries on from there.
  function captureMotion(t: number, frames = 30) {
    scripted = t;
    frameIndex = 0;
    prevRot = null;
    invalidate();
    renderFrames(frames, 1 / 60);
    const data = readTarget(history[current]);
    scripted = null;
    resumeAt = t + frames / 60;
    return data;
  }
  let resumeAt = 0;

  // Milliseconds per whole moving frame along the fixed path, measured as
  // throughput: frames go out in small batches with the GPU drained between
  // them, which keeps it busy (and clocked up) without ever letting the queue
  // grow long.
  function benchmark(frames = 48, batch = 4) {
    scripted = resumeAt;
    renderFrame(1 / 60);
    drainGpu();
    const t0 = performance.now();
    for (let i = 0; i < frames; i++) {
      renderFrame(1 / 60);
      gl.flush();
      if (i % batch === batch - 1) drainGpu();
    }
    drainGpu();
    const ms = (performance.now() - t0) / frames;
    resumeAt = scripted;
    scripted = null;
    return +ms.toFixed(2);
  }

  // Milliseconds per pass while the dish is moving. Each pass is run `runs`
  // times back to back and the GPU drained before and after, so the numbers
  // are throughput (timer queries are unreliable under ANGLE / Metal).
  function profile(runs = 10) {
    // Reading back a pixel the pass wrote makes the GPU finish that work.
    const drain = (target: () => Target | null) => {
      const t = target();
      gl.bindFramebuffer(gl.FRAMEBUFFER, t ? t.fb : null);
      if (t) gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.FLOAT, new Float32Array(4));
      else gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(4));
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    };
    const timePass = (pass: () => void, target: () => Target | null) => {
      pass();
      drain(target);
      const t0 = performance.now();
      for (let i = 0; i < runs; i++) {
        pass();
        drain(target); // never let passes queue up (see renderFrames)
      }
      return +((performance.now() - t0) / runs).toFixed(2);
    };
    scripted = resumeAt;
    updatePose(0);
    prevRot = rot;
    prevCam = camPos;
    updatePose(1 / 60);
    const result = {
      trace: timePass(() => tracePass(samplePattern(params.motionSpp, [0, 0]), false), () => frameTarget),
      taa: timePass(() => taaPass(params.taaBlend, true), () => history[current]),
      bloom: timePass(bloomPass, () => bloomMips[0]),
      flare: timePass(flarePass, () => flareTarget),
      composite: timePass(compositePass, () => null),
      total: 0,
    };
    result.total = +(result.trace + result.taa + result.bloom + result.flare + result.composite).toFixed(2);
    invalidate();

    // Main-thread cost of a whole frame (JS, uniforms, DOM), median of `runs`.
    const cpu: number[] = [];
    for (let i = 0; i < runs; i++) {
      const t0 = performance.now();
      renderFrame(1 / 60);
      cpu.push(performance.now() - t0);
      if (i % 4 === 3) drain(() => null);
    }
    scripted = null;
    cpu.sort((a, b) => a - b);
    return { ...result, cpuFrame: +cpu[Math.floor(runs / 2)].toFixed(3) };
  }

  return {
    canvas,
    settings: params,
    lights,
    start,
    stop,
    dispose,
    configure,
    invalidate,
    setMood,
    get mood() {
      return mood.target;
    },
    setMotion,
    get motion() {
      return motionMode;
    },
    get state() {
      return motion.state;
    },
    setAudio: async (source) => {
      if (source) await voice.useStream(source);
      else voice.none();
    },
    useMicrophone: () => voice.useMicrophone(),
    useDemoVoice: () => voice.useDemo(),
    setLevel: (level) => voice.setLevel(level),
    stopVoice: () => voice.none(),
    get voice() {
      return voice.source;
    },
    get level() {
      return voice.level;
    },
    pulse: (strength = 1) => {
      voice.pulse(strength);
      if (reducedMotion()) motion.wake();
      else motion.kick([2.2 * strength, -3.2 * strength, 0.8 * strength]);
    },
    reset: () => motion.reset(),
    wake: () => motion.wake(),
    appear,
    setInteractive: (on) => {
      interactive = on;
      if (!on && held) {
        held = null;
        motion.release();
      }
    },
    setPaused: (on) => {
      paused = on;
    },
    get paused() {
      return paused;
    },
    getStats,
    debug: {
      pacer,
      setManual: (on) => {
        manual = on;
        last = performance.now();
      },
      renderFrames,
      benchmark,
      profile,
      captureTrace,
      captureMotion,
      probe,
      probeImage,
      view: () => ({ state: motion.state, rotation: Array.from(rot), camera: camPos }),
    },
  };
}
