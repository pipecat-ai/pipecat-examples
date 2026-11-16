// Minimal 3x3 matrix helpers. Column-major, matching GLSL / uniformMatrix3fv.
export type Mat3 = Float32Array;
export type Vec3 = [number, number, number];

export const DEG = Math.PI / 180;

export function identity(): Mat3 {
  return new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1]);
}

export function mul(a: Mat3, b: Mat3): Mat3 {
  const out = new Float32Array(9);
  for (let j = 0; j < 3; j++) {
    for (let i = 0; i < 3; i++) {
      out[j * 3 + i] = a[i] * b[j * 3] + a[3 + i] * b[j * 3 + 1] + a[6 + i] * b[j * 3 + 2];
    }
  }
  return out;
}

export function rotX(a: number): Mat3 {
  const c = Math.cos(a), s = Math.sin(a);
  return new Float32Array([1, 0, 0, 0, c, s, 0, -s, c]);
}

export function rotY(a: number): Mat3 {
  const c = Math.cos(a), s = Math.sin(a);
  return new Float32Array([c, 0, -s, 0, 1, 0, s, 0, c]);
}

export function rotZ(a: number): Mat3 {
  const c = Math.cos(a), s = Math.sin(a);
  return new Float32Array([c, s, 0, -s, c, 0, 0, 0, 1]);
}

export function axisAngle(axis: Vec3, angle: number): Mat3 {
  const [x, y, z] = normalize(axis);
  const c = Math.cos(angle), s = Math.sin(angle), t = 1 - c;
  return new Float32Array([
    t * x * x + c, t * x * y + s * z, t * x * z - s * y,
    t * x * y - s * z, t * y * y + c, t * y * z + s * x,
    t * x * z + s * y, t * y * z - s * x, t * z * z + c,
  ]);
}

// Rotation taking unit vector `from` onto unit vector `to`.
export function fromTo(from: Vec3, to: Vec3): Mat3 {
  const f = normalize(from), t = normalize(to);
  const d = dot(f, t);
  if (d > 0.99999) return identity();
  if (d < -0.99999) return axisAngle(Math.abs(f[0]) < 0.9 ? cross(f, [1, 0, 0]) : cross(f, [0, 1, 0]), Math.PI);
  return axisAngle(cross(f, t), Math.acos(d));
}

export function dot(a: Vec3, b: Vec3) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

export function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

export function normalize(v: Vec3): Vec3 {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
}

// Direction from yaw (around +Y, 0 = towards the camera at +Z) and pitch.
export function dirFromAngles(yawDeg: number, pitchDeg: number): Vec3 {
  const y = yawDeg * DEG, p = pitchDeg * DEG;
  return [Math.sin(y) * Math.cos(p), Math.sin(p), Math.cos(y) * Math.cos(p)];
}

export function srgbToLinear(hex: string): Vec3 {
  const n = parseInt(hex.replace('#', ''), 16);
  const ch = (v: number) => {
    const c = v / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return [ch((n >> 16) & 255), ch((n >> 8) & 255), ch(n & 255)];
}

// Small seeded random number generator, 0..1.
export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Cloud noise that tiles: three octaves of value noise, `cells` lattice cells
// across at the coarsest, as bytes for a size x size texture.
export function cloudNoise(size: number, cells: number, seed: number) {
  const rand = mulberry32(seed);
  const octaves = [1, 2, 4].map((k) => {
    const n = cells * k;
    return { n, lattice: Float32Array.from({ length: n * n }, rand) };
  });
  const out = new Uint8Array(size * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let sum = 0;
      let amp = 0.5;
      for (const { n, lattice } of octaves) {
        const fx = (x / size) * n, fy = (y / size) * n;
        const x0 = Math.floor(fx), y0 = Math.floor(fy);
        const x1 = (x0 + 1) % n, y1 = (y0 + 1) % n;
        let tx = fx - x0, ty = fy - y0;
        tx = tx * tx * (3 - 2 * tx);
        ty = ty * ty * (3 - 2 * ty);
        const a = lattice[y0 * n + x0] * (1 - tx) + lattice[y0 * n + x1] * tx;
        const b = lattice[y1 * n + x0] * (1 - tx) + lattice[y1 * n + x1] * tx;
        sum += amp * (a * (1 - ty) + b * ty);
        amp *= 0.5;
      }
      out[y * size + x] = Math.round((sum / 0.875) * 255);
    }
  }
  return out;
}

// ------------------------------------------------------------------ quaternions

export type Quat = [number, number, number, number]; // x, y, z, w

// The rotation b followed by the rotation a.
export function qMul(a: Quat, b: Quat): Quat {
  return [
    a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
    a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
    a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
    a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2],
  ];
}

export function qConj(q: Quat): Quat {
  return [-q[0], -q[1], -q[2], q[3]];
}

export function qNormalize(q: Quat): Quat {
  const l = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
  return [q[0] / l, q[1] / l, q[2] / l, q[3] / l];
}

export function qAxisAngle(axis: Vec3, angle: number): Quat {
  const [x, y, z] = normalize(axis);
  const s = Math.sin(angle / 2);
  return [x * s, y * s, z * s, Math.cos(angle / 2)];
}

// The shortest rotation taking unit vector `from` onto unit vector `to`.
export function qFromTo(from: Vec3, to: Vec3): Quat {
  const d = dot(from, to);
  if (d < -0.99999) return qAxisAngle(Math.abs(from[0]) < 0.9 ? cross(from, [1, 0, 0]) : cross(from, [0, 1, 0]), Math.PI);
  const c = cross(from, to);
  return qNormalize([c[0], c[1], c[2], 1 + d]);
}

// The rotation as a vector along its axis, as long as its angle (the short way round).
export function qRotationVector(q: Quat): Vec3 {
  const sign = q[3] < 0 ? -1 : 1;
  const x = q[0] * sign, y = q[1] * sign, z = q[2] * sign, w = q[3] * sign;
  const s = Math.hypot(x, y, z);
  if (s < 1e-9) return [2 * x, 2 * y, 2 * z];
  const k = (2 * Math.atan2(s, w)) / s;
  return [x * k, y * k, z * k];
}

export function qToMat3([x, y, z, w]: Quat): Mat3 {
  return new Float32Array([
    1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
    2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
    2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y),
  ]);
}
