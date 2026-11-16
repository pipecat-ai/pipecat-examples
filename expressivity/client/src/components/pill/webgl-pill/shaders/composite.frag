#version 300 es
// HDR + bloom + flare -> AgX (or ACES) tone mapping -> display, with a touch
// of grain. A lens's colour fringing and a faint halo of the pill's own
// colour in the air round it go in here too.
precision highp float;
uniform sampler2D uHdr;
uniform sampler2D uBloom;
uniform sampler2D uFlare;
uniform vec2 uCentre;      // where the pill sits on screen, 0..1
uniform float uAspect;
uniform vec3 uHalo;        // the halo's colour, at its strength
uniform float uHaloSize;   // its radius, in screen heights
uniform float uAberration; // how far red and blue part at the picture's edge
uniform float uExposure;
uniform float uBloomStrength;
uniform int uToneMap;    // 0 AgX, 1 AgX punchy, 2 ACES
uniform float uGrain;
uniform bool uTransparent; // the canvas is see-through: give each pixel a coverage
uniform float uSaturation;
uniform uint uFrame;
in vec2 vUv;
out vec4 fragColor;

vec3 agxContrast(vec3 x) {
  vec3 x2 = x * x;
  vec3 x4 = x2 * x2;
  return 15.5 * x4 * x2 - 40.14 * x4 * x + 31.96 * x4 - 6.868 * x2 * x + 0.4298 * x2 + 0.1191 * x - 0.00232;
}

vec3 agx(vec3 v, bool punchy) {
  const mat3 inMat = mat3(
    0.842479062253094, 0.0423282422610123, 0.0423756549057051,
    0.0784335999999992, 0.878468636469772, 0.0784336,
    0.0792237451477643, 0.0791661274605434, 0.879142973793104);
  const mat3 outMat = mat3(
    1.19687900512017, -0.0528968517574562, -0.0529716355144438,
    -0.0980208811401368, 1.15190312990417, -0.0980434501171241,
    -0.0990297440797205, -0.0989611768448433, 1.15107367264116);
  const float minEv = -12.47393;
  const float maxEv = 4.026069;
  v = inMat * v;
  v = clamp(log2(max(v, 1e-10)), minEv, maxEv);
  v = (v - minEv) / (maxEv - minEv);
  v = agxContrast(v);
  if (punchy) {
    float luma = dot(v, vec3(0.2126, 0.7152, 0.0722));
    v = pow(max(v, 0.0), vec3(1.35));
    v = luma + 1.4 * (v - luma);
  }
  v = outMat * v;
  return clamp(v, 0.0, 1.0);
}

vec3 aces(vec3 x) {
  x *= 0.6;
  return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

vec3 linearToSrgb(vec3 c) {
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}

float hash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

void main() {
  // Red and blue are magnified a hair differently, more so away from the middle.
  vec2 fromMiddle = vUv - 0.5;
  vec2 fringe = fromMiddle * (uAberration * 4.0 * dot(fromMiddle, fromMiddle));
  vec3 hdr = vec3(texture(uHdr, vUv + fringe).r, texture(uHdr, vUv).g, texture(uHdr, vUv - fringe).b);
  vec3 bloom = texture(uBloom, vUv).rgb;
  vec2 out2 = (vUv - uCentre) * vec2(uAspect, 1.0);
  vec3 halo = uHalo * exp(-dot(out2, out2) / (uHaloSize * uHaloSize));
  vec3 c = (hdr + bloom * uBloomStrength + texture(uFlare, vUv).rgb + halo) * uExposure;
  float luma = dot(c, vec3(0.2126, 0.7152, 0.0722));
  c = max(luma + uSaturation * (c - luma), 0.0);

  vec3 outc;
  if (uToneMap == 2) {
    outc = linearToSrgb(aces(c));
  } else {
    outc = agx(c, uToneMap == 1);
  }
  // Grain only where there is a picture, so the empty background stays empty.
  float n = hash(gl_FragCoord.xy + float(uFrame % 997u) * 13.7) - 0.5;
  float lit = max(outc.r, max(outc.g, outc.b));
  outc = max(outc + n * uGrain * smoothstep(0.0, 0.03, lit), 0.0);
  // On a see-through canvas the pill covers what is behind it only as far as
  // it is bright, so its dark glass and the space round it let the page
  // show. (The colour is already "over black", which is what premultiplied
  // alpha expects.)
  fragColor = vec4(outc, uTransparent ? max(outc.r, max(outc.g, outc.b)) : 1.0);
}
