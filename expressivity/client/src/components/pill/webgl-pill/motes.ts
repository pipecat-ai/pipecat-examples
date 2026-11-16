// Motes: a handful of bright specks that drift in the light inside the pill,
// circling its axis and working their way outwards. A voice drives them out
// faster and lights them up; left alone they idle.
import { mulberry32 } from './math';

export const MOTE_COUNT = 16; // keep in sync with NUM_MOTES in pathtrace.frag

export type MoteDrive = {
  level: number;
  energy: number;
  tempo: number;    // the mood's pace
  restless: number; // how unevenly they move
};

export class Motes {
  // x, y, z in the dish's own space and a brightness, for each mote.
  readonly data = new Float32Array(MOTE_COUNT * 4);

  private rand = mulberry32(23);
  private radius = new Float32Array(MOTE_COUNT); // 0 at the axis, 1 at the edge of the light
  private angle = new Float32Array(MOTE_COUNT);
  private pace = new Float32Array(MOTE_COUNT);
  private phase = new Float32Array(MOTE_COUNT);
  private clock = 0;

  constructor() {
    for (let i = 0; i < MOTE_COUNT; i++) {
      this.spawn(i);
      this.radius[i] = this.rand(); // start spread out rather than all at the middle
    }
  }

  private spawn(i: number) {
    this.radius[i] = 0.03 + 0.09 * this.rand();
    this.angle[i] = this.rand() * 2 * Math.PI;
    this.pace[i] = 0.6 + 0.8 * this.rand();
    this.phase[i] = this.rand() * 2 * Math.PI;
  }

  // centre, half: the height of the middle of the light and half its depth; reach: its radius.
  update(dt: number, drive: MoteDrive, centre: number, half: number, reach: number, brightness: number) {
    this.clock += dt;
    const t = this.clock;
    const push = 0.03 + 0.42 * drive.level * drive.level + 0.1 * drive.energy;
    for (let i = 0; i < MOTE_COUNT; i++) {
      const r = this.radius[i];
      // Quicker round the middle, like anything circling a drain.
      const swirl = (0.3 + 0.16 / (0.2 + r)) * drive.tempo;
      const jitter = drive.restless * 0.5 * Math.sin(t * (2.1 + this.pace[i]) + this.phase[i]);
      this.angle[i] += dt * swirl * (1 + jitter);
      this.radius[i] = r + dt * push * this.pace[i] * drive.tempo;
      if (this.radius[i] > 0.95) this.spawn(i);

      const rr = this.radius[i] * reach;
      const fadeIn = Math.min(1, Math.max(0, (this.radius[i] - 0.03) / 0.15));
      const fadeOut = Math.min(1, Math.max(0, (0.95 - this.radius[i]) / 0.2));
      const twinkle = 0.6 + 0.4 * Math.sin(t * (1.7 + 2.3 * this.pace[i]) + this.phase[i]);
      this.data[i * 4] = rr * Math.cos(this.angle[i]);
      this.data[i * 4 + 1] = centre + 0.55 * half * Math.sin(this.phase[i] + t * 0.4 * this.pace[i]);
      this.data[i * 4 + 2] = rr * Math.sin(this.angle[i]);
      this.data[i * 4 + 3] = brightness * fadeIn * fadeOut * twinkle * (0.2 + 2.2 * drive.energy + 1.2 * drive.level);
    }
  }
}
