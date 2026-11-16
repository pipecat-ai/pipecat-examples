// Pacing. A moving frame at full quality can cost more than one refresh of a
// fast display allows. Drawing as fast as it will go then gives frames of
// uneven length, which reads as stutter. So the loop keeps to a ladder of
// settings (fewer samples a pixel, or a frame on every second or third
// refresh) and holds the best rung on which frames arrive on time.
//
// It starts low, so the first frames are smooth, and climbs a rung every few
// seconds while frames keep arriving on time. A rung that doesn't hold is
// tried once more after a longer wait and then left alone until the window
// changes, so it doesn't hunt. It judges by late frames, against the
// display's refresh time measured while nothing is being drawn. (Timing the
// GPU directly isn't dependable in a browser: reading back to wait for it
// costs more than a frame.)

export type PaceSettings = {
  motionSpp: number; // the most samples a pixel a moving frame may take
  // What to give up first when a frame won't fit: 'frame rate' keeps the
  // display's rate and takes fewer samples; 'fidelity' keeps the samples and
  // draws on every second (third...) refresh.
  prefer: 'frame rate' | 'fidelity';
};

export class Pacer {
  refresh = 1000 / 60; // the display's frame time, ms
  every = 1;           // draw on every n-th refresh
  spp = 1;             // samples a pixel
  rung = 0;            // how far down the ladder
  late = 0;            // tally of frames that overran
  locked = false;      // hold the pace as it is (for looking into it by hand)

  private graceUntil = 0;       // frames before this aren't judged: start-up and changes of pace stumble on their own
  private warmUntil = 0;        // rungs that fail before this aren't held against them: the GPU takes a while to get going
  private raisedAt = -Infinity; // when it last climbed a rung
  private retryAt = 0;          // no climbing before this
  private failed: number[] = []; // how often climbing to each rung has not held
  private measuring = 0;        // callbacks left of a spell of timing the display
  private gaps: number[] = [];
  private lastTick = 0;

  constructor(private settings: () => PaceSettings, private maxSamples: number) {}

  // Time the display over the next few callbacks. Nothing should be drawn
  // meanwhile (see tick), so the gaps between them are the display's own.
  measure() {
    this.measuring = 16;
    this.gaps = [];
    this.lastTick = 0;
  }

  // Call on every animation callback. True while it is timing the display,
  // when the caller should draw nothing.
  tick(now: number) {
    if (this.measuring <= 0) return false;
    if (this.lastTick > 0) this.gaps.push(now - this.lastTick);
    this.lastTick = now;
    if (--this.measuring === 0) {
      if (this.gaps.length > 4) {
        const sorted = this.gaps.sort((a, b) => a - b);
        this.refresh = Math.max(1000 / 240, Math.min(1000 / 24, sorted[sorted.length >> 1]));
      }
      this.reset(now); // the ladder depends on the display's rate
    }
    return true;
  }

  // Whether a frame is due, `interval` ms after the last one drawn.
  due(interval: number) {
    return interval >= this.refresh * (this.every - 0.5);
  }

  isLate(interval: number) {
    return interval > this.refresh * (this.every + 0.6);
  }

  // The settings to hold, best first, as [every, spp]. Never slower than
  // about 30 frames a second.
  ladder(): [number, number][] {
    const { motionSpp, prefer } = this.settings();
    const most = Math.max(1, Math.min(this.maxSamples, Math.round(motionSpp)));
    const slowest = Math.max(1, Math.round(1000 / 30 / this.refresh));
    const rungs: [number, number][] = [];
    if (prefer === 'frame rate') {
      for (let every = 1; every <= slowest; every++) for (let spp = most; spp >= 1; spp--) rungs.push([every, spp]);
    } else {
      for (let every = 1; every <= slowest; every++) rungs.push([every, most]);
      for (let spp = most - 1; spp >= 1; spp--) rungs.push([slowest, spp]);
    }
    return rungs;
  }

  private setRung(rung: number, now: number) {
    const rungs = this.ladder();
    this.rung = Math.max(0, Math.min(rungs.length - 1, rung));
    [this.every, this.spp] = rungs[this.rung];
    this.late = 0;
    this.graceUntil = Math.max(this.graceUntil, now + 300);
  }

  // When to try the rung above: soon, later if it has failed once, never if twice.
  private nextClimb(now: number) {
    const tries = this.failed[this.rung - 1] ?? 0;
    return tries >= 2 ? Infinity : now + (tries ? 30000 : 3000);
  }

  // Start over: from the display's own rate at one sample a pixel (or the
  // second rung, for 'fidelity'), climbing from there. Also forgets which
  // rungs failed, as the window may have changed size or moved to another
  // screen.
  reset(now: number) {
    const { motionSpp, prefer } = this.settings();
    this.failed = [];
    this.graceUntil = now + 1500;
    this.warmUntil = now + 12000;
    this.setRung(prefer === 'frame rate' ? Math.round(motionSpp) - 1 : 1, now);
    this.retryAt = this.graceUntil + 1500;
  }

  // Call for each frame of a moving picture with whether it arrived late.
  judge(late: boolean, now: number) {
    if (this.locked || now < this.graceUntil) return;
    // A pace holds if only the odd frame is late: about one in twenty.
    this.late = late ? this.late + 1 : Math.max(0, this.late - 0.06);
    if (this.late > 8) {
      // Overrunning. If it had only just climbed here, this rung doesn't hold.
      if (now - this.raisedAt < 8000 && now > this.warmUntil) this.failed[this.rung] = (this.failed[this.rung] ?? 0) + 1;
      this.setRung(this.rung + 1, now);
      this.retryAt = this.nextClimb(now);
    } else if (this.rung > 0 && this.late < 1 && now > this.retryAt) {
      this.setRung(this.rung - 1, now);
      this.raisedAt = now;
      this.retryAt = this.nextClimb(now);
    }
  }
}
