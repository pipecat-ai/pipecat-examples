#version 300 es
// Glass tracer for a single petri-dish shaped "pill" with a light living
// inside it.
//
// Every camera ray spawns a tree of reflect / refract branches (Fresnel
// weighted). The tree is traced once, carrying red, green and blue together.
// Dispersion comes from also carrying how each ray's direction changes with
// the index of refraction: where a path leaves the glass the three colours
// look up the lights in slightly different directions. Lights are soft
// rectangles at infinity that the camera can't see directly, only through the
// glass.
//
// The "soul" is a light in the hollow of the dish, driven by a voice: a core
// that flares with the voice's spectrum, ripples that carry each syllable
// outwards, slow wisps wound round the axis and a few drifting motes. It is a
// real emitter in the scene: every stretch of a path that crosses the hollow
// gathers it, so the glass reflects and refracts it like anything else, and
// the glass body, scratches and smudges pick its light up too.
//
// The glass carries a thin coating, a fraction of a micron thick, that tints
// its reflections by interference the way oil on water does.
//
// Apart from the sub-pixel jitter the shading is deterministic, so frames in
// motion are clean and the TAA pass only has aliasing left to resolve. Still
// frames (uStochastic) also jitter wavelengths and surface roughness, which
// the progressive accumulation averages out.
precision highp float;
precision highp int;
precision highp sampler2D;

#include "geometry.glsl"

uniform vec2 uResolution;
uniform uint uFrame;
// Samples per pixel this frame: xy is the sub-pixel position, z where in each
// wavelength band the sample sits (still frames pick that at random instead).
#define MAX_SAMPLES 16
uniform int uSpp;
uniform vec3 uSamples[MAX_SAMPLES];
uniform bool uStochastic;

uniform mat3 uObjRot;     // object -> world
uniform vec3 uCamPos;
uniform mat3 uCamBasis;   // columns: right, up, back
uniform float uTanHalfFov;

uniform float uIor;
uniform float uDispersion;
uniform vec3 uSigma;
uniform float uRoughness;
uniform vec3 uGlow;        // light scattered towards the camera per unit length inside the glass
uniform vec3 uEmit;        // light the glass gives off itself, which rises with the voice
uniform float uGlowDensity;

uniform float uScratchDensity;
uniform float uWallScratches;
uniform float uScratchWidth;
uniform float uScratchSlope;
uniform float uScratchScale;
uniform float uScratchLength;
uniform float uScratchStrength;
uniform float uSmudge;
uniform float uSmudgeScale;
uniform sampler2D uSmudgeNoise; // tileable cloud noise, 8 lattice cells across
uniform float uHaze;
// x: how strongly the coating tints reflections, y: its thickness in microns,
// z: how much that varies across the glass, w: reflectance it adds.
uniform vec4 uFilm;

uniform int uMaxDepth;
uniform int uMaxSegments;
uniform float uMinWeight;
uniform int uDebug; // 1: world direction of the strongest escaping path, 2: first-hit mirror direction

#define NUM_LIGHTS 8
uniform vec3 uLightDir[NUM_LIGHTS];
uniform vec3 uLightRight[NUM_LIGHTS];
uniform vec3 uLightUp[NUM_LIGHTS];
uniform vec2 uLightSize[NUM_LIGHTS];
uniform vec3 uLightColA[NUM_LIGHTS];
uniform vec3 uLightColB[NUM_LIGHTS];
uniform vec3 uLightIrr[NUM_LIGHTS];
uniform float uLightIntensity[NUM_LIGHTS];
uniform float uLightSoft[NUM_LIGHTS];
uniform float uLightGrad[NUM_LIGHTS];
uniform vec3 uBackground;

// The soul. uWave's top row holds the voice's loudness over the last moments,
// newest first; it is read by distance from the axis, so what was said a
// moment ago is further out. Its bottom row holds the voice's spectrum, low
// to high, which the core's edge is bent by.
uniform int uSoulSteps;     // samples along each stretch of a path through it; 0 turns it off
uniform sampler2D uWave;
uniform vec4 uSoulBox;      // x: centre height, y: half height, z: radius, w: 1 / core radius^2
uniform vec3 uSoulCore;     // light given off per unit length, core
uniform vec3 uSoulAura;     // ... and everything round it
uniform vec4 uSoulWarp;     // xy, zw: two- and three-fold bends of the ripple fronts
uniform vec4 uSoulStir;     // x: how far the wisps have turned, y: extra turn towards the axis, z: wisp strength, w: flare reach
uniform vec4 uSoulFlare;    // xy, zw: where the two- and three-fold flare patterns point (cos, sin)
uniform vec4 uSoulDrift;    // where the two layers of wisp noise have slid to
#define NUM_MOTES 16
uniform int uMoteCount;
uniform vec4 uMotes[NUM_MOTES]; // xyz: where each mote is, w: how bright
uniform vec3 uMoteColor;
uniform float uMoteFalloff;     // 1 / mote radius^2
uniform float uSoulGlass;   // how much of the soul's light the glass body picks up
uniform float uSoulSurface; // ... and scratches / smudges on its surface

out vec4 fragColor;

// ---------------------------------------------------------------- random

uint pcg(uint v) {
  uint state = v * 747796405u + 2891336453u;
  uint word = ((state >> ((state >> 28u) + 4u)) ^ state) * 277803737u;
  return (word >> 22u) ^ word;
}

uint rngState;
float rand() {
  rngState = pcg(rngState);
  return float(rngState) * (1.0 / 4294967296.0);
}

// ---------------------------------------------------------------- lights

// What light i sends along direction d (which needn't be unit length).
vec3 lightAlong(int i, vec3 d) {
  float c = dot(d, uLightDir[i]);
  if (c <= 0.0) return vec3(0.0);
  vec2 uv = vec2(dot(d, uLightRight[i]), dot(d, uLightUp[i])) / c;
  vec2 q = abs(uv) / uLightSize[i];
  // Rounded-rectangle falloff on k = (qx^6 + qy^6)^(1/6), worked in k^6 so
  // the root is only taken inside the soft edge band.
  vec2 q2 = q * q;
  vec2 q6 = q2 * q2 * q2;
  float k6 = q6.x + q6.y;
  if (k6 >= 1.0) return vec3(0.0);
  float lo = 1.0 - uLightSoft[i];
  float lo2 = lo * lo;
  float m = 1.0;
  if (lo <= 0.0 || k6 > lo2 * lo2 * lo2) m = 1.0 - smoothstep(lo, 1.0, pow(k6, 1.0 / 6.0));
  float g = clamp(0.5 + 0.5 * uv.y / (uLightSize[i].y * uLightGrad[i]), 0.0, 1.0);
  g = g * g * (3.0 - 2.0 * g);
  return mix(uLightColB[i], uLightColA[i], g) * (uLightIntensity[i] * m);
}

vec3 lights(vec3 d) {
  vec3 L = vec3(0.0);
  for (int i = 0; i < NUM_LIGHTS; i++) {
    if (uLightIntensity[i] > 0.0) L += lightAlong(i, d);
  }
  return L;
}

// How far each colour's index of refraction sits from the base index for the
// sample being traced, and the largest of the three.
vec3 gDn;
float gDnMax;

// The lights seen along d (object space), where dd is how d changes with the
// index of refraction. When the colours part by less than a soft light edge
// could show, one lookup serves all three; otherwise each colour looks along
// its own direction, but only at the lights the ray passes near.
vec3 lightsDispersed(vec3 d, vec3 dd) {
  vec3 dW = uObjRot * d;
  float spread2 = dot(dd, dd) * gDnMax * gDnMax;
  if (spread2 < 1e-6) return lights(dW);
  // Close to the critical angle the first-order estimate runs away.
  float spread = min(sqrt(spread2), 0.12);
  vec3 ddW = uObjRot * dd * (spread / sqrt(spread2));
  vec3 dR = dW + ddW * gDn.r;
  vec3 dG = dW + ddW * gDn.g;
  vec3 dB = dW + ddW * gDn.b;
  vec3 L = vec3(0.0);
  for (int i = 0; i < NUM_LIGHTS; i++) {
    if (uLightIntensity[i] <= 0.0) continue;
    float c = dot(dW, uLightDir[i]);
    if (c <= 0.0) continue;
    vec2 uv = vec2(dot(dW, uLightRight[i]), dot(dW, uLightUp[i])) / c;
    // On the light's plane the colours land within this of the middle ray.
    float reach = spread * (1.0 + dot(uv, uv)) * 1.5;
    vec2 q = (abs(uv) - reach) / uLightSize[i];
    if (max(q.x, q.y) >= 1.0) continue;
    L += vec3(lightAlong(i, dR).r, lightAlong(i, dG).g, lightAlong(i, dB).b);
  }
  return L;
}

// Cheap diffuse response to the lights, used for surface haze / smudges.
vec3 hazeLight(vec3 nWorld) {
  vec3 L = vec3(0.0);
  for (int i = 0; i < NUM_LIGHTS; i++) {
    float c = dot(nWorld, uLightDir[i]);
    L += uLightIrr[i] * (max(c, 0.0) + 0.6 * max(-c, 0.0));
  }
  return L;
}

// ---------------------------------------------------------------- soul

// The texture spans 1.5 times the trip from axis to wall, so bent fronts and
// the glass beyond the hollow still have something to read.
const float WAVE_SCALE = (63.0 / 64.0) / 1.5;
const float WAVE_BIAS = 0.5 / 64.0;

// cos / sin of two and three times the angle of a unit vector.
void harmonics(vec2 u, out vec2 u2, out vec2 u3) {
  u2 = vec2(u.x * u.x - u.y * u.y, 2.0 * u.x * u.y);
  u3 = vec2(u2.x * u.x - u2.y * u.y, u2.x * u.y + u2.y * u.x);
}

// How far above or below its average the voice's spectrum is, where the
// pattern laid round the axis by `c` (the cosine of a multiple of the angle)
// puts this direction.
float spectrumAt(float c) {
  return textureLod(uWave, vec2(0.5 - 0.5 * c, 0.75), 0.0).r;
}

// The loudness the ripple passing a point was sent out with. q: distance from
// the axis, 1 at the edge of the soul. The fronts bend more the further out
// they are; the centre stays put.
float rippleAt(float q, vec2 u2, vec2 u3) {
  float age = q * (1.0 + q * (dot(u2, uSoulWarp.xy) + dot(u3, uSoulWarp.zw)));
  return textureLod(uWave, vec2(age * WAVE_SCALE + WAVE_BIAS, 0.25), 0.0).r / (1.0 + q);
}

// The soul's light reaching the glass or its surface at a point: only its
// broad shape matters there.
vec3 soulLight(vec2 xz) {
  float r2 = dot(xz, xz);
  float r = sqrt(r2);
  vec2 u2;
  vec2 u3;
  harmonics(xz / max(r, 1e-4), u2, u3);
  return uSoulCore * exp(-r2 * uSoulBox.w) + uSoulAura * rippleAt(r / uSoulBox.z, u2, u3);
}

// Strength of the core (x) and of the light round it (y) at a point inside
// the soul, in full, and q: its distance from the axis.
vec2 soulField(vec3 p, out float q) {
  vec2 xz = p.xz;
  float r2 = dot(xz, xz);
  float r = sqrt(r2);
  q = r / uSoulBox.z;
  vec2 u2;
  vec2 u3;
  harmonics(xz / max(r, 1e-4), u2, u3);

  // Wisps: two layers of cloud noise turned opposite ways round the axis,
  // further near the middle, so the light looks stirred. Multiplying them
  // leaves thin bright strands. A little of the height goes in too, so they
  // shift against each other as the dish tilts.
  float turn = uSoulStir.x + uSoulStir.y * (1.0 - q);
  vec2 cs = vec2(cos(turn), sin(turn));
  vec2 a = vec2(xz.x * cs.x - xz.y * cs.y, xz.x * cs.y + xz.y * cs.x);
  vec2 b = vec2(xz.x * cs.x + xz.y * cs.y, xz.y * cs.x - xz.x * cs.y);
  float n = 4.0 * textureLod(uSmudgeNoise, a * 0.34 + p.y * vec2(0.25, 0.1) + uSoulDrift.xy, 0.0).r
                * textureLod(uSmudgeNoise, b * 0.62 - p.y * vec2(0.1, 0.22) + uSoulDrift.zw, 0.0).r;
  float strands = max(min(n, 2.4) - 0.9, 0.0);

  // Flares: the core reaches a little further where the voice's spectrum
  // stands above its average and less where it falls below, laid round the
  // axis two and three times over. Silent, it is round; with a voice its edge
  // is pulled gently out of round and shifts as the sound does, without
  // growing overall.
  float core = 0.0;
  float arg = r2 * uSoulBox.w;
  if (arg < 30.0) {
    float reach = 1.0;
    if (uSoulStir.w > 0.0) {
      reach += uSoulStir.w * 0.5 * (spectrumAt(dot(u2, uSoulFlare.xy)) + spectrumAt(dot(u3, uSoulFlare.zw)));
    }
    reach = clamp(reach, 0.7, 1.6);
    core = exp(-arg / (reach * reach));
  }

  // The ripples show through the wisps, and the brightest strands glow a
  // little themselves round the core.
  float around = rippleAt(q, u2, u3) * mix(1.0, n, 0.35) + uSoulStir.z * 2.0 * strands * strands * exp(-3.5 * q * q);
  return vec2(core, around);
}

// Light gathered from the soul along o + d * t, t in 0..tMax. It lives in a
// squat cylinder inside the hollow and fades to nothing at its faces.
// weight: how much the path counts for by now; faint ones (a reflection of a
// reflection) get a coarser look at it and go without the motes.
vec3 soulAlong(vec3 o, vec3 d, float tMax, float jitter, float weight) {
  float t0 = 0.0;
  float t1 = tMax;
  float yc = uSoulBox.x;
  float hh = uSoulBox.y;
  if (abs(d.y) > 1e-6) {
    float a = (yc - hh - o.y) / d.y;
    float b = (yc + hh - o.y) / d.y;
    t0 = max(t0, min(a, b));
    t1 = min(t1, max(a, b));
  } else if (abs(o.y - yc) >= hh) {
    return vec3(0.0);
  }
  if (t0 >= t1) return vec3(0.0);
  float A = dot(d.xz, d.xz);
  float B = dot(o.xz, d.xz);
  float C = dot(o.xz, o.xz) - uSoulBox.z * uSoulBox.z;
  if (A > 1e-9) {
    float disc = B * B - A * C;
    if (disc <= 0.0) return vec3(0.0);
    float s = sqrt(disc);
    t0 = max(t0, (-B - s) / A);
    t1 = min(t1, (-B + s) / A);
  } else if (C >= 0.0) {
    return vec3(0.0);
  }
  if (t0 >= t1) return vec3(0.0);

  int steps = weight > 0.2 ? uSoulSteps : max(2, uSoulSteps / 2);
  float dt = (t1 - t0) / float(steps);
  vec2 sum = vec2(0.0);
  for (int i = 0; i < steps; i++) {
    vec3 p = o + d * (t0 + dt * (float(i) + jitter));
    float v = (p.y - yc) / hh;
    float wy = max(1.0 - v * v, 0.0);
    float q;
    vec2 f = soulField(p, q);
    float wr = max(1.0 - q * q, 0.0);
    sum += f * (wy * wy * wr);
  }

  // Motes: each a small ball of light, seen as bright as the ray passes close.
  float motes = 0.0;
  int count = weight > 0.05 ? uMoteCount : 0;
  for (int i = 0; i < count; i++) {
    vec3 c = uMotes[i].xyz - o;
    vec3 e = c - d * clamp(dot(c, d), t0, t1);
    float k = dot(e, e) * uMoteFalloff;
    if (k < 8.0) motes += uMotes[i].w * exp(-k);
  }
  return (uSoulCore * sum.x + uSoulAura * sum.y) * dt + uMoteColor * motes;
}

// ---------------------------------------------------------------- surface

// Procedural hairline scratches. Returns coverage and the scratch direction
// in the surface's 2D parameterisation. Lines thinner than the pixel
// footprint are widened to it with their energy kept constant, so they stay
// anti-aliased without needing extra samples.
float scratches(vec2 uv, int surf, float density, float footprint, out vec2 tdir) {
  float cell = 0.22;
  vec2 g = floor(uv / cell);
  float best = 0.0;
  tdir = vec2(1.0, 0.0);
  // A scratch centred in a cell reaches at most its longest half-length plus
  // its widest line beyond that cell.
  float maxHalf = cell * uScratchLength;
  float maxW = max(uScratchWidth, footprint);
  float reach = maxHalf + maxW;
  // Candidate k of cell (x, y) hashes as pcg(x + pcg(y + pcg(k))); the inner
  // steps are shared by a whole row, and the innermost by every cell.
  uint k0 = uint(surf * 8);
  uvec3 zk = uvec3(pcg(k0), pcg(k0 + 1u), pcg(k0 + 2u));
  for (int j = -1; j <= 1; j++) {
    float ylo = (g.y + float(j)) * cell;
    float gy = max(max(ylo - uv.y, uv.y - (ylo + cell)), 0.0);
    if (gy > reach) continue;
    uint cy = uint(int(g.y) + j + 32768);
    uvec3 yk = uvec3(pcg(cy + zk.x), pcg(cy + zk.y), pcg(cy + zk.z));
    for (int i = -1; i <= 1; i++) {
      float xlo = (g.x + float(i)) * cell;
      float gx = max(max(xlo - uv.x, uv.x - (xlo + cell)), 0.0);
      if (gx * gx + gy * gy > reach * reach) continue;
      uint cx = uint(int(g.x) + i + 32768);
      for (int k = 0; k < 3; k++) {
        // Each hash is cut into a few short random numbers.
        uint h0 = pcg(cx + yk[k]);
        if (float(h0 >> 16) > density * 65536.0) continue;
        uint h1 = pcg(h0);
        vec2 center = vec2(xlo, ylo) + vec2(h1 & 0xffffu, h1 >> 16) * (cell / 65536.0);
        float ang = float(h0 & 0xffffu) * (6.2831853 / 65536.0);
        vec2 dir = vec2(cos(ang), sin(ang));
        vec2 d = uv - center;
        float along = dot(d, dir);
        float dist = abs(d.x * dir.y - d.y * dir.x);
        // Nearly every candidate misses by far more than any scratch's length
        // or width, so rule those out before working out the rest of its shape.
        if (dist > maxW || abs(along) > maxHalf) continue;
        uint h2 = pcg(h1);
        vec3 hB = vec3(h2 & 1023u, (h2 >> 10) & 1023u, h2 >> 22) * (1.0 / 1024.0);
        float halfLen = maxHalf * mix(0.1, 1.0, hB.x * hB.x);
        if (abs(along) > halfLen) continue;
        float width = uScratchWidth * mix(0.4, 1.0, hB.y);
        float w = max(width, footprint);
        if (dist > w) continue;
        float taper = 1.0 - pow(abs(along) / halfLen, 3.0);
        float m = (1.0 - smoothstep(0.0, w, dist)) * (width / w) * taper * mix(0.35, 1.0, hB.z);
        if (m > best) { best = m; tdir = dir; }
      }
    }
  }
  return best;
}

// Scratch coverage at a hit, with its tangent in object space.
float scratchAt(vec3 p, Hit h, float footprint, out vec3 T) {
  bool wall = h.surf == 0 || h.surf == 3;
  float density = uScratchDensity * (wall ? uWallScratches : 1.0);
  T = vec3(1.0, 0.0, 0.0);
  if (density <= 0.0 || h.surf == 5) return 0.0; // none on the rounded edges
  vec2 uv;
  vec3 T0;
  vec3 T1;
  if (wall) {
    float r = length(p.xz);
    float phi = atan(p.z, p.x);
    uv = vec2(phi * r, p.y);
    T0 = vec3(-sin(phi), 0.0, cos(phi));
    T1 = vec3(0.0, 1.0, 0.0);
  } else {
    uv = p.xz;
    T0 = vec3(1.0, 0.0, 0.0);
    T1 = vec3(0.0, 0.0, 1.0);
  }
  vec2 tdir;
  float m = scratches(uv * uScratchScale, h.surf, density, footprint * uScratchScale, tdir);
  T = normalize(T0 * tdir.x + T1 * tdir.y);
  return m;
}

// Cloud noise over the glass: a slanted slice through it, so the walls get a
// pattern of their own, shifted for each face. Greasy patches are its peaks,
// and the coating's thickness follows it.
float cloudAt(vec3 p, Hit h) {
  vec2 uv = (p.xz + p.y * vec2(0.83, 1.31)) * (uSmudgeScale / 8.0) + float(h.surf) * 0.137;
  return textureLod(uSmudgeNoise, uv, 0.0).r;
}

const float FILM_IOR = 1.38;

float fresnelDielectric(float cosi, float eta) {
  float sint2 = eta * eta * (1.0 - cosi * cosi);
  if (sint2 >= 1.0) return 1.0;
  float cost = sqrt(1.0 - sint2);
  float rs = (eta * cosi - cost) / (eta * cosi + cost);
  float rp = (cosi - eta * cost) / (cosi + eta * cost);
  return 0.5 * (rs * rs + rp * rp);
}

// How refract(d, n, eta) changes with the index of refraction, given how d
// does (dd) and how eta does (deta).
vec3 refractDeriv(vec3 d, vec3 dd, vec3 n, float eta, float deta) {
  float c = -dot(d, n);
  float dc = -dot(dd, n);
  float s2 = 1.0 - c * c;
  float k = 1.0 - eta * eta * s2;
  float dk = 2.0 * eta * (eta * c * dc - deta * s2);
  return deta * d + eta * dd + (deta * c + eta * dc - 0.5 * dk / sqrt(max(k, 1e-3))) * n;
}

// Light a scratch sends towards the camera. The groove's walls span a fan of
// normals across the scratch, so it catches light from a whole arc of
// directions, both reflected and refracted.
vec3 scratchScatter(vec3 d, vec3 nFacing, vec3 T, bool entering, float ior) {
  vec3 across = normalize(cross(nFacing, T));
  float eta = entering ? 1.0 / ior : ior;
  vec3 sum = vec3(0.0);
  for (int k = 0; k < 6; k++) {
    float s = (float(k) - 2.5) / 2.5;
    vec3 nf = normalize(nFacing + across * (s * uScratchSlope));
    float cosi = -dot(d, nf);
    if (cosi <= 0.0) continue;
    vec3 t = refract(d, nf, eta);
    float F = dot(t, t) > 0.0 ? fresnelDielectric(cosi, eta) : 1.0;
    sum += F * lights(uObjRot * reflect(d, nf));
    if (F < 1.0) {
      // Going in, assume the ray leaves again through a parallel face.
      if (entering) t = refract(t, nFacing, ior);
      if (dot(t, t) > 0.0) sum += (1.0 - F) * lights(uObjRot * t);
    }
  }
  return sum / 6.0;
}

// ---------------------------------------------------------------- tracing

#define STACK 16

float debugWeight;
vec3 debugDir;
bool touchedDetail; // set when a path meets a wall, the rim or a rounded edge early on

float maxOf(vec3 v) { return max(v.r, max(v.g, v.b)); }

// o, d: the camera ray in object space. h0, m0, s0, cloud0: its hit and the
// scratch coverage, scattered light and cloud noise there, which main() works
// out once per pixel. jitter: where in each step the soul is sampled.
vec3 trace(vec3 o0, vec3 d0, uint seed, float pixelAngle, float m0, vec3 s0, float cloud0, Hit h0, float jitter) {
  rngState = seed;

  vec3 sO[STACK];
  vec3 sD[STACK];
  vec3 sDD[STACK]; // how the direction changes with the index of refraction
  vec3 sW[STACK];
  float sKey[STACK]; // the branch's weight in its strongest colour
  float sLen[STACK];
  int sDepth[STACK];
  int sp = 1;
  sO[0] = o0;
  sD[0] = d0;
  sDD[0] = vec3(0.0);
  sW[0] = vec3(1.0);
  sKey[0] = 1.0;
  sLen[0] = 0.0;
  sDepth[0] = 0;

  bool soul = uSoulSteps > 0;
  vec3 L = vec3(0.0);

  for (int it = 0; it < uMaxSegments; it++) {
    if (sp == 0) break;
    // Follow the heaviest branch still waiting, so when the budget of
    // segments runs out it is the faintest light that goes missing.
    int top = 0;
    for (int i = 1; i < sp; i++) {
      if (sKey[i] > sKey[top]) top = i;
    }
    vec3 o = sO[top];
    vec3 d = sD[top];
    vec3 dd = sDD[top];
    vec3 w = sW[top];
    float len = sLen[top];
    int depth = sDepth[top];
    float sKeyTop = sKey[top];
    sp--;
    sO[top] = sO[sp];
    sD[top] = sD[sp];
    sDD[top] = sDD[sp];
    sW[top] = sW[sp];
    sKey[top] = sKey[sp];
    sLen[top] = sLen[sp];
    sDepth[top] = sDepth[sp];

    Hit h;
    if (it == 0) {
      h = h0;
    } else if (!intersectDish(o, d, h)) {
      // Gone for good: past whatever of the soul lies on the way, to the lights.
      if (soul) L += w * soulAlong(o, d, 1e30, jitter, sKeyTop);
      L += w * (depth == 0 ? uBackground : lightsDispersed(d, dd));
      float wMax = maxOf(w);
      if (depth > 0 && wMax > debugWeight) {
        debugWeight = wMax;
        debugDir = uObjRot * d;
      }
      continue;
    }

    vec3 p = o + d * h.t;
    len += h.t;
    if (depth <= 3 && h.surf != 1 && h.surf != 4) touchedDetail = true;
    bool entering = dot(d, h.n) < 0.0;
    if (entering) {
      // The stretch just travelled was through air, maybe through the soul.
      if (soul) L += w * soulAlong(o, d, h.t, jitter, sKeyTop);
    } else {
      // ... or inside the glass: a little haze in it glows, so long paths
      // (walls seen edge-on, light trapped in the rim) light up while thin
      // faces stay clear. The same haze catches the soul's light, and the
      // glass gives off a little of its own, so the pulse still shows where a
      // reflection lies over the hollow.
      vec3 glow = uGlow + uEmit;
      if (soul && uSoulGlass > 0.0) glow += uSoulGlass * soulLight(o.xz + d.xz * (0.5 * h.t));
      L += w * glow * (1.0 - exp(-uGlowDensity * h.t));
      w *= exp(-uSigma * h.t);
    }

    vec3 ns = h.n;
    float cloud = depth == 0 ? cloud0 : 0.5;
    if (depth == 1 && (uSmudge > 0.0 || uFilm.x > 0.0)) cloud = cloudAt(p, h);
    float smudge = smoothstep(0.52, 0.78, cloud) * uSmudge;
    if (uStochastic) {
      float rough = uRoughness + smudge * 0.03;
      if (rough > 0.0) ns = normalize(ns + (vec3(rand(), rand(), rand()) * 2.0 - 1.0) * rough);
    }
    if (dot(ns, d) * dot(h.n, d) <= 0.0) ns = h.n;

    vec3 ng = entering ? h.n : -h.n; // geometric, facing the incoming ray
    vec3 nf = entering ? ns : -ns;   // shading, facing the incoming ray
    float eta = entering ? 1.0 / uIor : uIor;
    float deta = entering ? -eta * eta : 1.0;
    float cosi = clamp(-dot(d, nf), 0.0, 1.0);

    if (depth <= 1) {
      // Marks on the surface catch the soul's light as well as the lights'.
      vec3 inner = soul && uSoulSurface > 0.0 ? uSoulSurface * soulLight(p.xz) : vec3(0.0);
      if (depth == 0) {
        if (m0 > 0.0) {
          L += w * m0 * uScratchStrength * (s0 + inner);
          w *= 1.0 - m0; // the scratch replaces that much of the smooth surface
        }
      } else {
        vec3 T;
        float m = scratchAt(p, h, len * pixelAngle, T);
        if (m > 0.0) {
          if (uScratchStrength > 0.0) L += w * m * uScratchStrength * (scratchScatter(d, nf, T, entering, uIor) + inner);
          w *= 1.0 - m;
        }
      }
      if (uHaze > 0.0) L += w * (uHaze * (0.15 + smudge)) * (hazeLight(uObjRot * ns) + inner);
    }

    if (depth >= uMaxDepth) continue;

    vec3 rfl = reflect(d, nf);
    vec3 ddRfl = dd - 2.0 * dot(dd, nf) * nf;
    if (dot(rfl, ng) <= 0.0) {
      rfl = reflect(d, ng);
      ddRfl = dd - 2.0 * dot(dd, ng) * ng;
    }
    // Whether light escapes or is trapped is the same for every colour;
    // dispersion only bends the escaping ray.
    float F = fresnelDielectric(cosi, eta);
    vec3 rfr = vec3(0.0);
    vec3 ddRfr = vec3(0.0);
    if (F < 1.0) {
      vec3 nr = nf;
      rfr = refract(d, nf, eta);
      if (dot(rfr, ng) >= 0.0) {
        nr = ng;
        rfr = refract(d, ng, eta);
      }
      if (dot(rfr, rfr) == 0.0) F = 1.0;
      else ddRfr = refractDeriv(d, dd, nr, eta, deta);
    }

    // The coating: light reflected off its two faces interferes, so how much
    // of each colour comes back depends on the angle and on how thick the
    // coating is just there. A few bounces in, its tint no longer shows.
    vec3 F3 = vec3(F);
    if (uFilm.x > 0.0 && F < 1.0 && depth <= 3) {
      float ni = entering ? 1.0 : uIor;
      float cosFilm = sqrt(max(1.0 - (1.0 - cosi * cosi) * ni * ni / (FILM_IOR * FILM_IOR), 0.0));
      float thickness = uFilm.y * (1.0 + uFilm.z * (2.0 * cloud - 1.0));
      vec3 fringe = cos((12.566371 * FILM_IOR * thickness * cosFilm) / vec3(0.65, 0.55, 0.45));
      F3 = clamp(F * (1.0 + uFilm.x * fringe) + uFilm.w * (0.5 + 0.5 * fringe) * (1.0 - F), 0.0, 1.0);
    }
    vec3 wr = w * F3;
    vec3 wt = w * (1.0 - F3);
    float kr = maxOf(wr);
    float kt = maxOf(wt);
    if (kr > uMinWeight && sp < STACK) {
      sO[sp] = p + ng * 2e-4;
      sD[sp] = rfl;
      sDD[sp] = ddRfl;
      sW[sp] = wr;
      sKey[sp] = kr;
      sLen[sp] = len;
      sDepth[sp] = depth + 1;
      sp++;
    }
    if (kt > uMinWeight && sp < STACK) {
      sO[sp] = p - ng * 2e-4;
      sD[sp] = rfr;
      sDD[sp] = ddRfr;
      sW[sp] = wt;
      sKey[sp] = kt;
      sLen[sp] = len;
      sDepth[sp] = depth + 1;
      sp++;
    }
  }
  return L;
}

vec3 cameraRay(vec2 pixel) {
  vec2 ndc = (pixel / uResolution) * 2.0 - 1.0;
  float aspect = uResolution.x / uResolution.y;
  return normalize(uCamBasis * vec3(ndc.x * aspect * uTanHalfFov, ndc.y * uTanHalfFov, -1.0));
}

void main() {
  ivec2 px = ivec2(gl_FragCoord.xy);
  float pixelAngle = 2.0 * uTanHalfFov / uResolution.y;
  mat3 toObj = transpose(uObjRot);
  vec3 o = toObj * uCamPos;

  if (uDebug > 0) {
    vec3 d = toObj * cameraRay(gl_FragCoord.xy);
    debugWeight = 0.0;
    debugDir = vec3(0.0);
    gDn = vec3(0.0);
    gDnMax = 0.0;
    Hit h;
    if (intersectDish(o, d, h)) {
      if (uDebug == 1) {
        trace(o, d, 1u, pixelAngle, 0.0, vec3(0.0), 0.5, h, 0.5);
      } else {
        debugDir = uObjRot * reflect(d, h.n);
        debugWeight = 1.0;
      }
    }
    fragColor = vec4(debugDir, debugWeight);
    return;
  }

  // Scratches and smudges are worked out once, at the pixel centre: scratch
  // coverage is already anti-aliased over the pixel's footprint.
  vec3 dC = toObj * cameraRay(floor(gl_FragCoord.xy) + 0.5);
  Hit hC;
  hC.surf = -1;
  float m0 = 0.0;
  float cloud0 = 0.5;
  vec3 s0 = vec3(0.0);
  if (intersectDish(o, dC, hC)) {
    vec3 pC = o + dC * hC.t;
    vec3 T;
    m0 = scratchAt(pC, hC, hC.t * pixelAngle, T);
    if (m0 > 0.0 && uScratchStrength > 0.0) s0 = scratchScatter(dC, hC.n, T, true, uIor);
    if (uSmudge > 0.0 || uFilm.x > 0.0) cloud0 = cloudAt(pC, hC);
  }

  // Interleaved gradient noise, stepped along each frame: neighbouring pixels
  // sample the soul at different depths and the history averages them.
  float ign = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
  float jitter = fract(ign + float(uFrame % 64u) * 0.61803399);

  // The fine filaments that need several samples are light caught in the
  // walls, rim and edges. A pixel whose first sample never meets one (most
  // of the floor) keeps that single sample, which TAA accumulates over time.
  touchedDetail = false;
  int taken = 0;
  vec3 acc = vec3(0.0);
  for (int s = 0; s < uSpp; s++) {
    if (s == 1 && !touchedDetail) break;
    taken++;
    vec3 smp = uSamples[s];
    vec3 d = toObj * cameraRay(floor(gl_FragCoord.xy) + smp.xy);
    uint seed = pcg(uint(px.x) * 1973u + uint(px.y) * 9277u + (uFrame * uint(uSpp) + uint(s)) * 26699u) | 1u;
    rngState = seed;
    // Each colour is a range of wavelengths; still frames pick one at random,
    // moving frames use the middle of each range.
    float lamJ = uStochastic ? rand() : smp.z;
    vec3 lam = mix(vec3(0.59, 0.50, 0.40), vec3(0.70, 0.59, 0.50), lamJ);
    gDn = 0.0042 * uDispersion * (1.0 / (lam * lam) - 1.0 / (0.55 * 0.55));
    gDnMax = maxOf(abs(gDn));

    // A camera ray that misses the dish only ever sees the background, and
    // the sub-pixel edge it might be missing calls for more samples.
    Hit h;
    if (!intersectDish(o, d, h)) {
      acc += uBackground;
      touchedDetail = true;
      continue;
    }
    // A sample that lands on another face than the centre (at silhouettes)
    // doesn't carry the centre's scratch.
    float m = h.surf == hC.surf ? m0 : 0.0;
    acc += trace(o, d, seed, pixelAngle, m, s0, cloud0, h, uStochastic ? rand() : jitter);
  }
  fragColor = vec4(max(acc / float(taken), 0.0), 1.0);
}
