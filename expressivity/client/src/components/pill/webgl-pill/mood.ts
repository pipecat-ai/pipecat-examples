// The pill's mood: which colours it takes and how its inner light behaves.
//
// The lights and the glass are authored once, in the violet of the reference
// image: hues from deep blue (about 265 degrees in OKLCh) through violet to
// pink (345). A mood turns that range of hues to its own and scales the
// chroma, so every light keeps its brightness and its place in the scheme
// while the whole pill changes colour. Moods cross-fade in OKLab, which goes
// through soft neutral tones rather than round the rainbow.
import type { Vec3 } from './math';
import { srgbToLinear } from './math';

export type Mood = 'neutral' | 'frustrated' | 'sad' | 'positive' | 'violet';

type MoodDef = {
  label: string;
  hueDeep: number;  // where the scheme's blue end goes, degrees
  hueLight: number; // ... and its pink end
  chroma: number;   // chroma scale
  core: string;     // the inner light: its core
  aura: string;     // ... and the ripples around it
  tempo: number;    // how fast ripples travel
  restless: number; // how much the ripple fronts bend and wander
  flicker: number;  // unsteadiness of the core
  swell: number;    // how far the core grows with the voice
  // How much of the glass coating's rainbow shows. Colour is what tells the
  // moods apart, so none of them lets it stray far from its own.
  sheen: number;
};

export const MOODS: Record<Mood, MoodDef> = {
  // Zinc: the scheme with nearly all its colour taken out, a touch cool.
  neutral: {
    label: 'Neutral',
    hueDeep: 275, hueLight: 290, chroma: 0.07,
    core: '#fafafa', aura: '#c4c4cc',
    tempo: 1, restless: 0.5, flicker: 0, swell: 1, sheen: 0.35,
  },
  // Red into orange; quick, uneven, agitated.
  frustrated: {
    label: 'Frustrated',
    hueDeep: 22, hueLight: 62, chroma: 1.05,
    core: '#ffb066', aura: '#ff4a1c',
    tempo: 1.55, restless: 1.25, flicker: 1, swell: 1.25, sheen: 0.25,
  },
  // Deep blue into azure; slow and heavy.
  sad: {
    label: 'Sad',
    hueDeep: 266, hueLight: 236, chroma: 0.95,
    core: '#a5c8ff', aura: '#2f6bff',
    tempo: 0.62, restless: 0.3, flicker: 0, swell: 0.75, sheen: 0.5,
  },
  // Emerald into fresh green; lively.
  positive: {
    label: 'Positive',
    hueDeep: 168, hueLight: 134, chroma: 0.95,
    core: '#c8ffd4', aura: '#1fd666',
    tempo: 1.2, restless: 0.75, flicker: 0, swell: 1.1, sheen: 0.45,
  },
  // The scheme as authored, to compare against the reference image.
  violet: {
    label: 'Violet',
    hueDeep: 265, hueLight: 345, chroma: 1,
    core: '#f3d4ff', aura: '#b867ff',
    tempo: 1, restless: 0.6, flicker: 0, swell: 1, sheen: 0.6,
  },
};

export const MOOD_NAMES = Object.keys(MOODS) as Mood[];

const SRC_DEEP = 265;
const SRC_LIGHT = 345;

// ------------------------------------------------------------------ OKLab

function toOklab([r, g, b]: Vec3): Vec3 {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function fromOklab([L, a, b]: Vec3): Vec3 {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

const inGamut = (c: Vec3) => c.every((v) => v >= -1e-4 && v <= 1 + 1e-4);

// An authored colour as a mood shows it, in OKLab. Where the turned hue
// can't hold the chroma at that lightness, the chroma gives way.
function recolour(hex: string, def: MoodDef): Vec3 {
  const lab = toOklab(srgbToLinear(hex));
  const chroma = Math.hypot(lab[1], lab[2]);
  if (chroma < 1e-4) return lab;
  let hue = (Math.atan2(lab[2], lab[1]) * 180) / Math.PI;
  // Hues are compared on a circle centred on the middle of the authored range.
  const mid = (SRC_DEEP + SRC_LIGHT) / 2;
  hue = mid + ((((hue - mid + 180) % 360) + 360) % 360) - 180;
  const t = Math.max(0, Math.min(1, (hue - SRC_DEEP) / (SRC_LIGHT - SRC_DEEP)));
  const h = ((def.hueDeep + (def.hueLight - def.hueDeep) * t) * Math.PI) / 180;
  const at = (c: number): Vec3 => [lab[0], c * Math.cos(h), c * Math.sin(h)];
  const want = chroma * def.chroma;
  if (inGamut(fromOklab(at(want)))) return at(want);
  let lo = 0, hi = want;
  for (let i = 0; i < 12; i++) {
    const c = (lo + hi) / 2;
    if (inGamut(fromOklab(at(c)))) lo = c;
    else hi = c;
  }
  return at(lo);
}

// ------------------------------------------------------------------ state

const cache = new Map<string, Vec3>();

function recoloured(hex: string, mood: Mood): Vec3 {
  const key = mood + hex;
  let lab = cache.get(key);
  if (!lab) {
    lab = mood === 'violet' ? toOklab(srgbToLinear(hex)) : recolour(hex, MOODS[mood]);
    cache.set(key, lab);
  }
  return lab;
}

function plain(hex: string): Vec3 {
  let lab = cache.get(hex);
  if (!lab) {
    lab = toOklab(srgbToLinear(hex));
    cache.set(hex, lab);
  }
  return lab;
}

export class MoodState {
  target: Mood;
  // How much of each mood is showing; sums to 1.
  private weights: Record<Mood, number>;

  constructor(initial: Mood) {
    this.target = initial;
    this.weights = Object.fromEntries(MOOD_NAMES.map((m) => [m, m === initial ? 1 : 0])) as Record<Mood, number>;
  }

  get transitioning() {
    return this.weights[this.target] < 1;
  }

  set(mood: Mood, immediate = false) {
    this.target = mood;
    if (immediate) for (const m of MOOD_NAMES) this.weights[m] = m === mood ? 1 : 0;
  }

  // Ease towards the target over about `seconds`. Returns whether anything changed.
  update(dt: number, seconds: number) {
    const w = this.weights[this.target];
    if (w >= 1) return false;
    let next = seconds > 0 ? w + (1 - w) * (1 - Math.exp((-4 * dt) / seconds)) : 1;
    if (next > 0.998) next = 1;
    const rest = 1 - w;
    for (const m of MOOD_NAMES) {
      if (m === this.target) this.weights[m] = next;
      else this.weights[m] = rest > 1e-6 ? (this.weights[m] * (1 - next)) / rest : 0;
    }
    return true;
  }

  private blend(pick: (mood: Mood) => Vec3): Vec3 {
    const lab: Vec3 = [0, 0, 0];
    for (const m of MOOD_NAMES) {
      const w = this.weights[m];
      if (w <= 0) continue;
      const c = pick(m);
      lab[0] += c[0] * w;
      lab[1] += c[1] * w;
      lab[2] += c[2] * w;
    }
    const rgb = fromOklab(lab);
    return [Math.max(rgb[0], 0), Math.max(rgb[1], 0), Math.max(rgb[2], 0)];
  }

  // An authored (violet scheme) colour as the current mood shows it, linear RGB.
  colour(hex: string): Vec3 {
    return this.blend((m) => recoloured(hex, m));
  }

  core(): Vec3 {
    return this.blend((m) => plain(MOODS[m].core));
  }

  aura(): Vec3 {
    return this.blend((m) => plain(MOODS[m].aura));
  }

  trait(key: 'tempo' | 'restless' | 'flicker' | 'swell' | 'sheen') {
    let v = 0;
    for (const m of MOOD_NAMES) v += MOODS[m][key] * this.weights[m];
    return v;
  }
}
