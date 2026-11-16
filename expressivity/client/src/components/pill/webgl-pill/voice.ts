// Turns a voice into the few numbers the pill runs on: a loudness that
// follows syllables, a slower energy that lingers between words, its spectrum,
// and the recent history of the loudness. The shader lays that history out
// from the centre of the dish to its wall, so each syllable travels outwards
// as a ripple, and bends the edge of the light's core by the spectrum.

import { mulberry32 } from './math';

export type VoiceSource = 'None' | 'Demo' | 'Microphone' | 'Stream' | 'External';

export const WAVE_TEXELS = 64;
export const SPECTRUM_BANDS = 32; // 90 Hz to 7.5 kHz, evenly spaced by pitch

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

// One audio context serves every pill on the page (browsers allow only a
// few), made when the first one needs it and closed when the last lets go.
let sharedContext: AudioContext | null = null;
let contextUsers = 0;

function acquireContext() {
  sharedContext ??= new AudioContext();
  contextUsers++;
  return sharedContext;
}

function releaseContext() {
  if (--contextUsers > 0 || !sharedContext) return;
  void sharedContext.close().catch(() => {});
  sharedContext = null;
}

// A made-up spectrum for voices that only come as a loudness: three resonances
// that wander the way the mouth's do, so the light still has a shape to take.
class Formants {
  private rand = mulberry32(3);
  private at = [6, 13, 22];
  private to = [6, 13, 22];
  private hold = 0;

  shape(out: Float32Array, dt: number, level: number) {
    this.hold -= dt;
    if (this.hold <= 0) {
      this.hold = 0.12 + 0.2 * this.rand();
      this.to = [3 + 6 * this.rand(), 10 + 8 * this.rand(), 19 + 8 * this.rand()];
    }
    const k = 1 - Math.exp(-dt / 0.06);
    for (let f = 0; f < 3; f++) this.at[f] += (this.to[f] - this.at[f]) * k;
    for (let b = 0; b < out.length; b++) {
      let v = 0.1;
      for (let f = 0; f < 3; f++) {
        const d = (b - this.at[f]) / (2.2 + f * 0.6);
        v += (1 - 0.22 * f) * Math.exp(-d * d);
      }
      out[b] = clamp01(v * level);
    }
  }
}

const HISTORY_SECONDS = 6;

// Stands in for someone talking: phrases of a few syllables with pauses
// between, for trying the pill out without a microphone.
class DemoVoice {
  private rand = mulberry32(11);
  private pause = 0.5;
  private phrase = 0;
  private phraseLength = 1;
  private t = 0;
  private duration = 0;
  private gap = 0;
  private loudness = 0;
  bands: [number, number, number] = [0, 0, 0];

  sample(dt: number) {
    if (this.pause > 0) {
      this.pause -= dt;
      if (this.pause <= 0) {
        this.phraseLength = this.phrase = 1.1 + 2.6 * this.rand();
        this.t = Infinity;
      }
      return 0;
    }
    this.phrase -= dt;
    this.t += dt;
    if (this.t > this.duration + this.gap) {
      if (this.phrase <= 0) {
        this.pause = 0.45 + 1.3 * this.rand();
        return 0;
      }
      this.t = 0;
      this.duration = 0.1 + 0.2 * this.rand();
      // Mostly run together, now and then a break between words.
      this.gap = this.rand() < 0.22 ? 0.12 + 0.14 * this.rand() : 0.015 + 0.05 * this.rand();
      this.loudness = 0.4 + 0.6 * this.rand();
      this.bands = [0.3 + 0.7 * this.rand(), 0.2 + 0.8 * this.rand(), this.rand() * this.rand()];
    }
    if (this.t > this.duration) return 0;
    const x = this.t / this.duration;
    // A phrase rises a little, then tails off.
    const contour = 0.65 + 0.35 * Math.sin(Math.PI * Math.min(1, 1 - this.phrase / this.phraseLength));
    return this.loudness * contour * Math.sin(Math.PI * Math.pow(x, 0.7));
  }
}

export class Voice {
  level = 0;  // loudness, 0..1, follows syllables
  crisp = 0;  // the same with a quicker fall, so the gaps between syllables show
  energy = 0; // rises while speaking, falls away over a second or so
  bands: [number, number, number] = [0, 0, 0]; // low, mid, high; 0..1
  spectrum = new Float32Array(SPECTRUM_BANDS);  // 0..1 each, low to high
  speaking = false; // someone is talking, give or take the gaps between words
  burst = 0;        // a one-off flash, see pulse()
  gain = 1;

  private kind: VoiceSource = 'None';
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private input: MediaStreamAudioSourceNode | null = null;
  private owned: MediaStream | null = null; // a stream opened here, so closed here
  private samples: Float32Array<ArrayBuffer> | null = null;
  private bins: Uint8Array<ArrayBuffer> | null = null;
  private heard = new Float32Array(SPECTRUM_BANDS); // the spectrum as just measured, before smoothing
  private formants = new Formants();
  private external = 0;
  private demo = new DemoVoice();
  private quiet = 1;
  private disposed = false;
  private silent = HISTORY_SECONDS; // seconds since there was last anything to show

  // The loudness over the last few seconds as (time, value), oldest first.
  private times: number[] = [];
  private values: number[] = [];
  private clock = 0;

  get source() {
    return this.kind;
  }

  private release() {
    this.input?.disconnect();
    this.input = null;
    this.analyser = null;
    this.owned?.getTracks().forEach((t) => t.stop());
    this.owned = null;
    if (this.ctx) {
      this.ctx = null;
      releaseContext();
    }
  }

  // Let go of everything: the audio graph, and the microphone if it was
  // opened here. Streams handed in from outside are left running.
  dispose() {
    this.disposed = true;
    this.release();
    this.kind = 'None';
  }

  // Browsers hold audio back until the page has been clicked or typed in.
  // Call this from such a moment if a stream was attached before one.
  resume() {
    if (this.ctx?.state === 'suspended') void this.ctx.resume().catch(() => {});
  }

  none() {
    this.release();
    this.kind = 'None';
  }

  useDemo() {
    this.release();
    this.kind = 'Demo';
  }

  // Nothing of the voice is left to show: no sound, and the last of it has
  // travelled out of the light. The picture can stand still.
  get settled() {
    return this.silent >= HISTORY_SECONDS && this.energy === 0;
  }

  // A flash that isn't speech: one bright ripple from the core, e.g. to mark a
  // change of mood.
  pulse(strength = 1) {
    this.burst = Math.max(this.burst, strength);
  }

  // Loudness from somewhere else (0..1), e.g. a level a voice pipeline reports.
  setLevel(v: number) {
    if (this.kind !== 'External') this.release();
    this.kind = 'External';
    this.external = Math.max(0, Math.min(1, v));
  }

  // Asks for the microphone. Rejects if the user or the browser says no.
  async useMicrophone() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    if (this.disposed) {
      // Let go of while the browser was still asking: don't leave the microphone on.
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    await this.listen(stream, 'Microphone');
    this.owned = stream;
  }

  // Any audio stream or track: a call participant, a bot's voice, ...
  async useStream(source: MediaStream | MediaStreamTrack) {
    await this.listen(source instanceof MediaStream ? source : new MediaStream([source]), 'Stream');
  }

  private async listen(stream: MediaStream, kind: VoiceSource) {
    if (this.disposed) return;
    this.release();
    this.ctx = acquireContext();
    // Browsers hold audio back until the page has been clicked or typed in;
    // analysis simply starts once it runs, so don't wait on it here.
    this.resume();
    const analyser = this.ctx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.5;
    this.input = this.ctx.createMediaStreamSource(stream);
    this.input.connect(analyser); // analysed only, never played back
    this.analyser = analyser;
    this.samples = new Float32Array(analyser.fftSize);
    this.bins = new Uint8Array(analyser.frequencyBinCount);
    this.kind = kind;
  }

  private measure(dt: number): number {
    if (this.kind === 'Demo') {
      const v = this.demo.sample(dt);
      this.follow(this.bands, this.demo.bands.map((b) => b * v) as [number, number, number], dt);
      this.formants.shape(this.heard, dt, v);
      return v;
    }
    if (this.kind === 'External') {
      this.formants.shape(this.heard, dt, this.external);
      return this.external;
    }
    if (!this.analyser || !this.samples || !this.bins) {
      this.heard.fill(0);
      return 0;
    }

    this.analyser.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (let i = 0; i < this.samples.length; i++) sum += this.samples[i] * this.samples[i];
    const db = 10 * Math.log10(sum / this.samples.length + 1e-12);
    // Room noise sits below about -50 dB, speech peaks around -15.
    const v = Math.max(0, Math.min(1, (db + 50) / 35));

    this.analyser.getByteFrequencyData(this.bins);
    const bins = this.bins;
    const hz = this.ctx!.sampleRate / this.analyser.fftSize;
    const band = (from: number, to: number) => {
      const a = Math.max(1, Math.floor(from / hz));
      const b = Math.min(bins.length - 1, Math.max(a, Math.floor(to / hz)));
      let s = 0;
      for (let i = a; i <= b; i++) s += bins[i];
      return clamp01((s / (b - a + 1) / 255 - 0.28) * 1.7);
    };
    this.follow(this.bands, [band(80, 350), band(350, 2000), band(2000, 7000)], dt);
    const edge = (b: number) => 90 * Math.pow(7500 / 90, b / SPECTRUM_BANDS);
    for (let b = 0; b < SPECTRUM_BANDS; b++) this.heard[b] = band(edge(b), edge(b + 1));
    return v;
  }

  private follow(out: number[], to: number[], dt: number) {
    const k = 1 - Math.exp(-dt / 0.08);
    for (let i = 0; i < out.length; i++) out[i] += (to[i] - out[i]) * k;
  }

  update(dt: number) {
    const raw = Math.min(1, this.measure(dt) * this.gain);
    const smooth = 1 - Math.exp(-dt / 0.06);
    for (let b = 0; b < SPECTRUM_BANDS; b++) {
      this.spectrum[b] += (Math.min(1, this.heard[b] * this.gain) - this.spectrum[b]) * smooth;
    }
    // Quick to rise, slower to fall, like a level meter.
    this.level += (raw - this.level) * (1 - Math.exp(-dt / (raw > this.level ? 0.03 : 0.16)));
    this.crisp += (raw - this.crisp) * (1 - Math.exp(-dt / (raw > this.crisp ? 0.02 : 0.07)));
    if (this.crisp < 1e-3) this.crisp = 0;
    this.energy += (this.level - this.energy) * (1 - Math.exp(-dt / (this.level > this.energy ? 0.35 : 1.1)));
    if (this.kind === 'None' || this.kind === 'External') this.follow(this.bands, [0, 0, 0], dt);
    if (this.level < 1e-3) {
      this.level = 0;
      this.crisp = 0;
    }
    if (this.energy < 1e-3) this.energy = 0;

    // Talking, until it has been quiet for longer than a pause between words.
    this.quiet = this.level > 0.1 ? 0 : this.quiet + dt;
    this.speaking = this.quiet < 0.7;
    this.burst *= Math.exp(-dt / 0.1);
    if (this.burst < 1e-3) this.burst = 0;

    this.silent = this.crisp + this.burst > 0 ? 0 : this.silent + dt;

    this.clock += dt;
    this.times.push(this.clock);
    this.values.push(this.crisp + this.burst);
    let old = 0;
    while (old < this.times.length - 2 && this.times[old + 1] < this.clock - HISTORY_SECONDS) old++;
    if (old > 64) {
      this.times.splice(0, old);
      this.values.splice(0, old);
    }
  }

  // The loudness over the last `seconds`, newest first, evenly spaced.
  fillWave(out: Float32Array, seconds: number) {
    const n = out.length;
    let j = this.times.length - 1;
    for (let i = 0; i < n; i++) {
      const t = this.clock - (i / (n - 1)) * seconds;
      while (j > 0 && this.times[j - 1] >= t) j--;
      if (j <= 0 || this.times.length === 0) {
        out[i] = this.times.length && t >= this.times[0] ? this.values[0] : 0;
      } else if (j >= this.times.length - 1 && t >= this.times[j]) {
        out[i] = this.values[j];
      } else {
        const t0 = this.times[j - 1], t1 = this.times[j];
        const f = t1 > t0 ? (t - t0) / (t1 - t0) : 0;
        out[i] = this.values[j - 1] + (this.values[j] - this.values[j - 1]) * Math.max(0, Math.min(1, f));
      }
    }
  }

  // The spectrum stretched over `out`, low to high.
  fillSpectrum(out: Float32Array) {
    const n = out.length;
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * (SPECTRUM_BANDS - 1);
      const a = Math.floor(x);
      const b = Math.min(SPECTRUM_BANDS - 1, a + 1);
      out[i] = this.spectrum[a] + (this.spectrum[b] - this.spectrum[a]) * (x - a);
    }
  }
}
