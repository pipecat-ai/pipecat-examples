#version 300 es
// Temporal resolve.
//
// In motion it's TAA: reproject last frame's result and blend a little of
// the new frame in. The motion is known exactly, so the dish is re-intersected
// to find the surface point under each pixel and where it was last frame.
// The fine filaments that alias worst are light trapped in the rim, which
// moves with the surface, so surface motion is the right vector for them;
// reflections that slide differently are caught by variance clipping.
// Blending happens in a compressed range so bright pixels don't dominate.
//
// When nothing moves it is a plain progressive average (uAlpha = 1 / n).
precision highp float;

#include "geometry.glsl"

uniform sampler2D uCurrent;
uniform sampler2D uHistory;
uniform vec2 uResolution;
uniform float uAlpha;
uniform bool uReproject;
uniform float uClipGamma;

uniform mat3 uObjRot;
uniform mat3 uPrevObjRot;
uniform vec3 uCamPos;
uniform vec3 uPrevCamPos; // the dish shifting is the camera shifting the other way
uniform mat3 uCamBasis;
uniform float uTanHalfFov;

out vec4 fragColor;

vec3 compress(vec3 c) { return c / (1.0 + max(c.r, max(c.g, c.b))); }
vec3 expand(vec3 c) { return c / max(1.0 - max(c.r, max(c.g, c.b)), 1e-3); }

vec3 toYCoCg(vec3 c) {
  return vec3(dot(c, vec3(0.25, 0.5, 0.25)), dot(c, vec3(0.5, 0.0, -0.5)), dot(c, vec3(-0.25, 0.5, -0.25)));
}

vec3 fromYCoCg(vec3 c) {
  return vec3(c.x + c.y - c.z, c.x + c.z, c.x - c.y - c.z);
}

// Catmull-Rom filtered history fetch (9 bilinear taps), so repeated
// reprojection doesn't soften the image.
vec3 sampleHistory(vec2 uv) {
  vec2 pos = uv * uResolution;
  vec2 tc1 = floor(pos - 0.5) + 0.5;
  vec2 f = pos - tc1;
  vec2 w0 = f * (-0.5 + f * (1.0 - 0.5 * f));
  vec2 w1 = 1.0 + f * f * (-2.5 + 1.5 * f);
  vec2 w2 = f * (0.5 + f * (2.0 - 1.5 * f));
  vec2 w3 = f * f * (-0.5 + 0.5 * f);
  vec2 w12 = w1 + w2;
  vec2 tc0 = (tc1 - 1.0) / uResolution;
  vec2 tc3 = (tc1 + 2.0) / uResolution;
  vec2 tc12 = (tc1 + w2 / w12) / uResolution;
  vec3 row0 = texture(uHistory, vec2(tc0.x, tc0.y)).rgb * w0.x
            + texture(uHistory, vec2(tc12.x, tc0.y)).rgb * w12.x
            + texture(uHistory, vec2(tc3.x, tc0.y)).rgb * w3.x;
  vec3 row1 = texture(uHistory, vec2(tc0.x, tc12.y)).rgb * w0.x
            + texture(uHistory, vec2(tc12.x, tc12.y)).rgb * w12.x
            + texture(uHistory, vec2(tc3.x, tc12.y)).rgb * w3.x;
  vec3 row2 = texture(uHistory, vec2(tc0.x, tc3.y)).rgb * w0.x
            + texture(uHistory, vec2(tc12.x, tc3.y)).rgb * w12.x
            + texture(uHistory, vec2(tc3.x, tc3.y)).rgb * w3.x;
  return max(row0 * w0.y + row1 * w12.y + row2 * w3.y, 0.0);
}

// Pull p towards the box centre until it lies inside (Playdead's clip).
vec3 clipToBox(vec3 lo, vec3 hi, vec3 p) {
  vec3 c = 0.5 * (hi + lo);
  vec3 e = 0.5 * (hi - lo) + 1e-5;
  vec3 v = p - c;
  vec3 a = abs(v / e);
  float m = max(a.x, max(a.y, a.z));
  return m > 1.0 ? c + v / m : p;
}

// Where the surface seen at uv was on screen last frame (uv itself if the
// pixel misses the dish).
vec2 previousUv(vec2 uv) {
  vec2 ndc = uv * 2.0 - 1.0;
  float aspect = uResolution.x / uResolution.y;
  vec3 rd = normalize(uCamBasis * vec3(ndc.x * aspect * uTanHalfFov, ndc.y * uTanHalfFov, -1.0));
  mat3 toObj = transpose(uObjRot);
  vec3 o = toObj * uCamPos;
  vec3 d = toObj * rd;
  Hit h;
  if (!intersectDish(o, d, h)) return uv;
  vec3 q = transpose(uCamBasis) * (uPrevObjRot * (o + d * h.t) - uPrevCamPos);
  return vec2(q.x / (-q.z * uTanHalfFov * aspect), q.y / (-q.z * uTanHalfFov)) * 0.5 + 0.5;
}

void main() {
  ivec2 px = ivec2(gl_FragCoord.xy);
  vec3 cur = texelFetch(uCurrent, px, 0).rgb;
  if (uAlpha >= 1.0) {
    fragColor = vec4(cur, 1.0);
    return;
  }
  if (!uReproject) {
    fragColor = vec4(mix(texelFetch(uHistory, px, 0).rgb, cur, uAlpha), 1.0);
    return;
  }

  ivec2 maxPx = ivec2(uResolution) - 1;
  vec3 m1 = vec3(0.0);
  vec3 m2 = vec3(0.0);
  for (int j = -1; j <= 1; j++) {
    for (int i = -1; i <= 1; i++) {
      vec3 c = toYCoCg(compress(texelFetch(uCurrent, clamp(px + ivec2(i, j), ivec2(0), maxPx), 0).rgb));
      m1 += c;
      m2 += c * c;
    }
  }
  // An all-black neighbourhood clips any history to black, so skip the
  // reprojection and history fetches for the background around the dish.
  if (m2 == vec3(0.0)) {
    fragColor = vec4(0.0, 0.0, 0.0, 1.0);
    return;
  }
  m1 /= 9.0;
  m2 /= 9.0;
  vec3 sigma = sqrt(max(m2 - m1 * m1, 0.0));

  vec2 uv = gl_FragCoord.xy / uResolution;
  vec2 uvPrev = previousUv(uv);
  bool onScreen = all(greaterThanEqual(uvPrev, vec2(0.0))) && all(lessThanEqual(uvPrev, vec2(1.0)));
  vec3 hist = toYCoCg(compress(sampleHistory(onScreen ? uvPrev : uv)));
  hist = clipToBox(m1 - uClipGamma * sigma, m1 + uClipGamma * sigma, hist);

  vec3 c = fromYCoCg(mix(hist, toYCoCg(compress(cur)), uAlpha));
  fragColor = vec4(expand(clamp(c, 0.0, 0.999)), 1.0);
}
