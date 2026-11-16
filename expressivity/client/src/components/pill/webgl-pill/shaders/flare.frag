#version 300 es
// Light that spills past the glass, the way a lens and a little haze in the
// air would show it: shafts fanning out from the light inside the pill, and a
// streak across its brightest parts. Drawn small; it is all soft.
precision highp float;
uniform sampler2D uSrc;    // the picture, blurred (a bloom level)
uniform vec2 uTexel;       // one texel of it
uniform vec2 uCentre;      // where the light inside sits on screen, 0..1
uniform float uShafts;
uniform float uShaftReach; // how far they run, as a share of the way out from the centre
uniform float uSourceSize; // radius of the light inside, in screen heights
uniform float uAspect;
uniform float uStreak;
in vec2 vUv;
out vec4 fragColor;

void main() {
  // Shafts: walk from here towards the centre, gathering what is bright on
  // the way, so the light in the middle is smeared outwards along rays. Only
  // the light inside counts; a highlight on the rim would smear into a
  // smudge.
  vec3 shafts = vec3(0.0);
  if (uShafts > 0.0) {
    const int N = 28;
    vec2 stride = (uCentre - vUv) * (uShaftReach / float(N));
    vec2 p = vUv;
    float weight = 1.0;
    for (int i = 0; i < N; i++) {
      p += stride;
      vec2 off = (p - uCentre) * vec2(uAspect, 1.0) / uSourceSize;
      shafts += max(textureLod(uSrc, p, 0.0).rgb - 1.2, 0.0) * (weight * exp(-dot(off, off)));
      weight *= 0.955;
    }
    shafts *= uShafts / float(N);
  }

  // Streak: only what is very bright, drawn out sideways.
  vec3 streak = vec3(0.0);
  if (uStreak > 0.0) {
    float total = 0.0;
    for (int i = -14; i <= 14; i++) {
      float x = float(i);
      float w = exp(-x * x / 70.0);
      vec2 at = vUv + vec2(x * 2.5 * uTexel.x, 0.0);
      vec2 off = (at - uCentre) * vec2(uAspect, 1.0) / uSourceSize;
      streak += max(textureLod(uSrc, at, 0.0).rgb - 2.5, 0.0) * (w * exp(-dot(off, off)));
      total += w;
    }
    streak *= uStreak / total;
  }
  fragColor = vec4(shafts + streak, 1.0);
}
