// How the pill carries itself. It is a rigid body on springs: each state says
// which way it would like to face and where it would like to sit, and a
// spring pulls it there. So a change of state, a syllable or a shove from the
// pointer all play out as motion with weight, overshoot and settle, and any
// of them can interrupt any other without a jump.
//
// Left alone it comes to rest: the drift dies away, it settles on one pose
// and stops dead, so the picture can stand still and be refined.
import {
  DEG, dirFromAngles, qAxisAngle, qConj, qFromTo, qMul, qNormalize, qRotationVector, qToMat3,
  type Quat, type Vec3,
} from './math';

/**
 * rest: stock still. idle: afloat, looking slowly about. listening: facing
 * you and moving with the voice it hears. spinning: turning like a coin.
 */
export type MotionState = 'rest' | 'idle' | 'listening' | 'spinning';
/**
 * auto: listening while someone is talking, then idle, then, after a while
 * with nothing happening, at rest.
 */
export type MotionMode = 'auto' | MotionState;

export type MotionSettings = {
  /** degrees its face wanders while idle */
  idleSway: number;
  idleSpeed: number;
  /** how far it floats up and down */
  bob: number;
  /** degrees it nods with the voice */
  listenNod: number;
  /** how far it comes forward on a loud syllable */
  listenPunch: number;
  /** one turn while spinning */
  spinSeconds: number;
  /**
   * one slow turn while idle; 0 to hold its place and look about instead. A
   * spin that ends then slows into this turn rather than coming round to
   * face front.
   */
  idleTurnSeconds: number;
  /** 0 settles dead, 1 overshoots freely */
  bounce: number;
  /** seconds with nothing happening before it comes to rest */
  restAfter: number;
  /** degrees it turns to look at the pointer; 0 for none */
  pointerTilt: number;
};

export type VoiceDrive = {
  level: number;
  energy: number;
  bands: [number, number, number];
  speaking: boolean;
};

// Seconds it goes on looking at a pointer that has stopped moving.
const GAZE_HOLD = 2.5;

const X: Vec3 = [1, 0, 0];
const Y: Vec3 = [0, 1, 0];
const TAU = 2 * Math.PI;
const MAX_SPIN = 16; // radians a second; a fling can't throw it faster
// Where it faces at rest: a little to one side and down, so its depth shows.
const HOME_YAW = -16;
const HOME_PITCH = -6;

const smooth = (x: number) => x * x * (3 - 2 * x);

// Facing along yaw / pitch (0, 0 is straight at the camera), turned by `roll`
// about its own axis.
export function facing(yaw: number, pitch: number, roll = 0): Quat {
  return qMul(qFromTo(Y, dirFromAngles(yaw, pitch)), qAxisAngle(Y, roll));
}

export class Motion {
  mode: MotionMode = 'auto';
  state: MotionState = 'idle'; // what it is doing now
  q: Quat = facing(HOME_YAW, HOME_PITCH);
  w: Vec3 = [0, 0, 0];         // angular velocity, radians a second
  pos: Vec3 = [0, 0, 0];       // offset from its place; +z is towards the camera
  vel: Vec3 = [0, 0, 0];
  // How alive it is: 1 awake, 0 at rest. Everything that moves by itself,
  // here and in the light inside, is scaled by this, so it all dies away
  // together.
  ease = 1;

  private easing = 1;                    // `ease` before smoothing
  private calm = 0;                      // seconds since anything last happened
  private clock = 0;
  private roll = 0;
  private turn = 0;                      // how far round a spin has come, radians
  private turnEnd: number | null = null; // where a spin that was called off will stop
  private turnRate = 0;                  // how fast it is turning, radians a second, eased between states
  private turning = false;               // whether `turn` is where it is now: spinning, or turning idly
  private once = 1;                      // how far through a single turn it is; 1 when done
  private onceSeconds = 1.3;
  private entering = 1;                  // how far through its entrance it is; 1 when done
  private entrance = { seconds: 1.8, turns: 1.25, depth: 3, fresh: false };
  // How far it has come out of the dark, 0..1: the picture's brightness
  // during the entrance.
  reveal = 1;
  private gazeTo: [number, number] = [0, 0]; // where the pointer is: -1..1 across and down from the pill
  private gaze: [number, number] = [0, 0];   // ... as far as it has got round to looking
  private glanced = Infinity;                // seconds since the pointer last moved
  private held = false;
  private pull: Vec3 = [0, 0, 0];        // how far the pointer has turned it since the last update
  private coasting = 0;                  // seconds of free spin left after a fling
  private settling = 0;                  // seconds left of the looser spring that brings it home
  private omega = 5;                     // the spring in force, eased from state to state
  private zeta = 0.85;

  // True while the pointer has hold of it or it is spinning free.
  get loose() {
    return this.held || this.coasting > 0;
  }

  // Something happened: don't go to rest just yet.
  wake() {
    this.calm = 0;
  }

  // The pointer has moved to (x, y): -1..1 across and down from the pill. It
  // turns its face that way and keeps it there while the pointer is about,
  // then straightens up again. Counts as something happening.
  look(x: number, y: number) {
    this.gazeTo = [Math.max(-1, Math.min(1, x)), Math.max(-1, Math.min(1, y))];
    this.glanced = 0;
    this.wake();
  }

  // Stop drifting at once, rather than winding down. (For when there is to
  // be no motion at all.)
  hush() {
    this.easing = 0;
    this.ease = 0;
  }

  grab() {
    this.held = true;
    this.coasting = 0;
    this.pull = [0, 0, 0];
    this.w = [0, 0, 0];
    this.wake();
  }

  // Turn it by the pointer: dx about the vertical, dy about the horizontal.
  drag(dx: number, dy: number) {
    if (!this.held) return;
    this.q = qNormalize(qMul(qMul(qAxisAngle([0, 1, 0], dx), qAxisAngle([1, 0, 0], dy)), this.q));
    this.pull[0] += dy;
    this.pull[1] += dx;
  }

  // Let go: thrown hard enough it spins on for a while, then comes home.
  release() {
    if (!this.held) return;
    this.held = false;
    if (Math.hypot(...this.w) > 1.2) this.coasting = 2.5;
    else this.settling = 1.6;
  }

  // Come back to where the current state wants it, with a bit of spring.
  reset() {
    this.held = false;
    this.coasting = 0;
    this.settling = 1.8;
    this.wake();
  }

  // A shove: it wobbles and settles.
  kick(w: Vec3) {
    this.w = [this.w[0] + w[0], this.w[1] + w[1], this.w[2] + w[2]];
    this.settling = Math.max(this.settling, 1.2);
    this.wake();
  }

  // One full turn about the vertical, taking `seconds`, on top of whatever
  // else it is doing.
  turnOnce(seconds: number) {
    this.wake();
    if (this.state === 'spinning') return; // already turning
    this.once = 0;
    this.onceSeconds = Math.max(0.3, seconds);
  }

  // Make an entrance: from the dark and from `depth` further off, spinning
  // `turns` times as it slows into place. With no turns and no depth it
  // simply fades in.
  appear(seconds: number, turns: number, depth: number) {
    this.wake();
    this.entering = 0;
    this.entrance = { seconds: Math.max(0.2, seconds), turns, depth, fresh: true };
    this.reveal = 0;
    this.once = 1;
    this.held = false;
    this.coasting = 0;
  }

  // True while it is still making its entrance.
  get appearing() {
    return this.entering < 1;
  }

  matrix() {
    return qToMat3(this.q);
  }

  // The yaw it is facing, radians.
  private heading() {
    const m = qToMat3(this.q);
    return Math.atan2(m[3], m[5]);
  }

  // `fixed`: hold this pose instead of following a state (the reference pose).
  update(dt: number, voice: VoiceDrive, s: MotionSettings, fixed: Quat | null) {
    if (dt <= 0) return;
    this.clock += dt;
    const t = this.clock;
    // Anything going on puts off its rest: a voice, the pointer, a turn, its
    // entrance, or being held in a state that moves.
    const busy =
      voice.speaking || this.loose || this.once < 1 || this.entering < 1 ||
      this.state === 'spinning' || this.state === 'listening';
    this.calm = busy ? 0 : this.calm + dt;

    // Which state it should be in. A spin that is called off carries on round
    // until it faces front again, rather than unwinding.
    const auto: MotionState = voice.speaking ? 'listening' : this.calm > s.restAfter ? 'rest' : 'idle';
    const wanted: MotionState = fixed ? 'rest' : this.mode === 'auto' ? auto : this.mode;
    const turnRate = TAU / Math.max(0.2, s.spinSeconds);
    // Idle, it can go on turning, slowly. Then a spin has nowhere to come
    // home to: it slows down where it is.
    const idleRate = s.idleTurnSeconds > 0 ? TAU / s.idleTurnSeconds : 0;
    const drifting = idleRate > 0 && wanted === 'idle';
    if (wanted === 'spinning') {
      if (this.state !== 'spinning' && !this.turning) this.turn = this.heading();
      this.state = 'spinning';
      this.turnEnd = null;
      this.turnRate = turnRate;
      this.turn += turnRate * dt;
    } else if (drifting) {
      if (this.state !== 'spinning' && !this.turning) {
        this.turn = this.heading();
        this.turnRate = 0;
      }
      this.state = 'idle';
      this.turnEnd = null;
      // From a spin it winds down to the idle turn; from stillness it picks up.
      this.turnRate += (idleRate - this.turnRate) * (1 - Math.exp(-dt / 0.7));
      this.turn += this.turnRate * dt;
    } else if (this.state === 'spinning') {
      this.turnEnd ??= Math.ceil((this.turn + 0.9) / TAU) * TAU;
      const left = this.turnEnd - this.turn;
      this.turn += Math.min(left, Math.min(turnRate, 0.7 + 3.5 * left) * dt);
      if (left < 0.02) {
        this.state = wanted;
        this.turnEnd = null;
        this.settling = 1.4;
      }
    } else {
      this.state = wanted;
    }
    this.turning = this.state === 'spinning' || drifting;

    // Waking is quick; going to rest takes its time.
    const awake = this.state !== 'rest';
    this.easing = fixed ? 0 : Math.max(0, Math.min(1, this.easing + (awake ? dt / 0.4 : -dt / 2.5)));
    this.ease = smooth(this.easing);

    // Where that state wants it, and how tight a spring takes it there.
    let target: Quat;
    let place: Vec3 = [0, 0, 0];
    let omega: number;
    let zeta: number;
    if (fixed) {
      target = fixed;
      omega = 7;
      zeta = 0.6;
    } else if (this.state === 'spinning') {
      // Round the vertical like a coin, tipped a touch so it shows its depth.
      target = facing(this.turn / DEG, 7);
      place = [0, s.bob * 0.5 * Math.sin(1.3 * t), 0.12];
      omega = 15;
      zeta = 0.95;
    } else if (drifting) {
      // Turning slowly round the vertical, tipped as in a spin, with a little
      // of the idle sway in how far it is tipped.
      const pitch = 7 + 0.15 * s.idleSway * Math.sin(0.23 * s.idleSpeed * t + 2.1);
      target = facing(this.turn / DEG, pitch);
      place = [0, s.bob * 0.6 * Math.sin(0.8 * s.idleSpeed * t), 0];
      omega = 9;
      zeta = 0.95;
    } else if (this.state === 'listening') {
      this.roll += dt * 0.25;
      // Above zero as a syllable lands, below as it dies away: it nods and
      // comes forward on the beat rather than leaning for as long as the
      // voice lasts.
      const beat = voice.level - voice.energy;
      const yaw = -4 + 0.3 * s.idleSway * Math.sin(0.9 * t) + 0.8 * s.listenNod * (voice.bands[0] - voice.bands[2]);
      const pitch = -3 + 0.25 * s.idleSway * Math.sin(0.7 * t + 1) + 1.5 * s.listenNod * beat;
      target = facing(yaw, pitch, this.roll);
      place = [0, s.bob * Math.sin(1.1 * t), s.listenPunch * (0.45 * voice.energy + 0.9 * Math.max(beat, 0))];
      omega = 11;
      zeta = 0.42;
    } else {
      // Idle, or on its way to rest: looking slowly about, by less and less.
      const k = s.idleSpeed;
      const e = this.ease;
      this.roll += dt * 0.1 * k * e;
      const yaw = HOME_YAW + e * s.idleSway * (0.8 * Math.sin(0.31 * k * t) + 0.2 * Math.sin(0.83 * k * t + 1.3));
      const pitch = HOME_PITCH + e * 0.5 * s.idleSway * Math.sin(0.23 * k * t + 2.1);
      target = facing(yaw, pitch, this.roll);
      place = [e * 0.5 * s.bob * Math.sin(0.47 * k * t + 0.6), e * s.bob * Math.sin(0.8 * k * t), 0];
      omega = e > 0 ? 5 : 7;
      zeta = e > 0 ? 0.85 : 1;
    }
    // It looks at the pointer, on top of whatever else it is doing, and
    // straightens up, slowly, once the pointer has been still a while, so a
    // pointer parked in a corner doesn't leave it askew.
    this.glanced += dt;
    const watching = this.glanced < GAZE_HOLD && s.pointerTilt > 0;
    for (let a = 0; a < 2; a++) {
      const aim = watching ? this.gazeTo[a] : 0;
      this.gaze[a] += (aim - this.gaze[a]) * (1 - Math.exp(-dt / (watching ? 0.12 : 0.8)));
      if (Math.abs(aim - this.gaze[a]) < 1e-5) this.gaze[a] = aim; // arrive, so it can come to a dead stop
    }
    if (!fixed && this.state !== 'spinning' && (this.gaze[0] !== 0 || this.gaze[1] !== 0)) {
      // It turns its face to the pointer: to the side the pointer is on,
      // and down as the pointer drops below it.
      const lean = s.pointerTilt * DEG;
      target = qMul(qMul(qAxisAngle(Y, this.gaze[0] * lean), qAxisAngle(X, this.gaze[1] * lean)), target);
      const shift = 0.004 * s.pointerTilt;
      place = [place[0] + this.gaze[0] * shift, place[1] - this.gaze[1] * shift, place[2]];
      if (this.glanced < 0.5) {
        // A livelier spring while the pointer is on the move: it follows
        // closely and settles with one small overshoot, not a wobble.
        omega = Math.max(omega, 9);
        zeta = Math.min(zeta, 0.7);
      }
    }
    if (this.entering < 1) {
      // The entrance rides on top of that: it starts turned away and further
      // off, already slowing, and arrives as the light comes up.
      const { seconds, turns, depth } = this.entrance;
      this.entering = Math.min(1, this.entering + dt / seconds);
      const away = (1 - this.entering) ** 3;
      target = qMul(qAxisAngle(Y, -away * turns * TAU), target);
      place = [place[0], place[1], place[2] - away * depth];
      omega = 20;
      zeta = 1;
      this.reveal = smooth(Math.min(1, this.entering / 0.8));
      if (this.entrance.fresh) {
        // It starts there, out of sight, already turning.
        this.entrance.fresh = false;
        this.q = target;
        this.w = [0, (3 * turns * TAU) / seconds, 0];
        this.pos = [place[0], place[1], place[2]];
        this.vel = [0, 0, (3 * depth) / seconds];
      }
    } else if (this.once < 1) {
      // The single turn rides on top of that.
      this.once = Math.min(1, this.once + dt / this.onceSeconds);
      if (this.once < 1) target = qMul(qAxisAngle(Y, TAU * smooth(this.once)), target);
      omega = Math.max(omega, 16);
      zeta = 0.9;
    } else if (this.settling > 0) {
      this.settling -= dt;
      omega = 7.5;
      zeta = 0.4;
    }
    // More bounce means less damping.
    zeta *= 1.4 - 0.8 * Math.max(0, Math.min(1, s.bounce));
    const blend = Math.min(1, dt * 6);
    this.omega += (omega - this.omega) * blend;
    this.zeta += (zeta - this.zeta) * blend;

    if (this.held) {
      // The pointer sets the pose; remember how fast, for when it lets go.
      const now: Vec3 = [this.pull[0] / dt, this.pull[1] / dt, 0];
      this.w = [0.5 * (this.w[0] + now[0]), 0.5 * (this.w[1] + now[1]), 0];
      this.pull = [0, 0, 0];
    }
    const speed = Math.hypot(...this.w);
    if (speed > MAX_SPIN) this.w = this.w.map((v) => (v * MAX_SPIN) / speed) as Vec3;

    // Small steps keep the stiff springs stable when a frame runs long.
    const steps = Math.max(1, Math.ceil(dt * 240));
    const h = dt / steps;
    const k = this.omega * this.omega;
    const c = 2 * this.zeta * this.omega;
    for (let i = 0; i < steps; i++) {
      if (this.coasting > 0) {
        // Thrown: it turns freely against a little drag until it has nearly
        // stopped, then heads home.
        const drag = Math.exp(-1.1 * h);
        this.w = [this.w[0] * drag, this.w[1] * drag, this.w[2] * drag];
        this.coasting -= h;
        if (this.coasting <= 0 || Math.hypot(...this.w) < 0.9) {
          this.coasting = 0;
          this.settling = 1.8;
        }
      } else if (!this.held) {
        const e = qRotationVector(qMul(target, qConj(this.q)));
        for (let a = 0; a < 3; a++) this.w[a] += (k * e[a] - c * this.w[a]) * h;
      }
      if (!this.held) {
        const turn = Math.hypot(...this.w) * h;
        if (turn > 1e-10) this.q = qNormalize(qMul(qAxisAngle(this.w, turn), this.q));
      }
      for (let a = 0; a < 3; a++) {
        this.vel[a] += (k * (place[a] - this.pos[a]) - c * this.vel[a]) * h;
        this.pos[a] += this.vel[a] * h;
      }
    }

    // At rest it comes to a dead stop once it has arrived, so the picture
    // stops changing and can build up.
    const resting = fixed !== null || (this.state === 'rest' && this.ease === 0);
    if (resting && !this.loose && this.once >= 1) {
      const off = Math.hypot(...qRotationVector(qMul(target, qConj(this.q))));
      if (off < 1e-4 && Math.hypot(...this.w) < 1e-3) {
        this.q = target;
        this.w = [0, 0, 0];
      }
      const away = Math.hypot(place[0] - this.pos[0], place[1] - this.pos[1], place[2] - this.pos[2]);
      if (away < 1e-5 && Math.hypot(...this.vel) < 1e-4) {
        this.pos = [place[0] + 0, place[1] + 0, place[2] + 0]; // (+ 0: no negative zeros)
        this.vel = [0, 0, 0];
      }
    }
  }
}
