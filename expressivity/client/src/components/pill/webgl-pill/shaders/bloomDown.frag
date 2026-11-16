#version 300 es
// 13-tap downsample (Jimenez, "Next Generation Post Processing in Call of Duty").
// The first pass uses a Karis average so single bright pixels don't sparkle.
precision highp float;
uniform sampler2D uSrc;
uniform vec2 uTexel;
uniform bool uKaris;
in vec2 vUv;
out vec4 fragColor;

float karisWeight(vec3 c) {
  return 1.0 / (1.0 + dot(c, vec3(0.2126, 0.7152, 0.0722)));
}

void main() {
  vec2 t = uTexel;
  vec3 a = texture(uSrc, vUv + t * vec2(-2.0, 2.0)).rgb;
  vec3 b = texture(uSrc, vUv + t * vec2(0.0, 2.0)).rgb;
  vec3 c = texture(uSrc, vUv + t * vec2(2.0, 2.0)).rgb;
  vec3 d = texture(uSrc, vUv + t * vec2(-2.0, 0.0)).rgb;
  vec3 e = texture(uSrc, vUv).rgb;
  vec3 f = texture(uSrc, vUv + t * vec2(2.0, 0.0)).rgb;
  vec3 g = texture(uSrc, vUv + t * vec2(-2.0, -2.0)).rgb;
  vec3 h = texture(uSrc, vUv + t * vec2(0.0, -2.0)).rgb;
  vec3 i = texture(uSrc, vUv + t * vec2(2.0, -2.0)).rgb;
  vec3 j = texture(uSrc, vUv + t * vec2(-1.0, 1.0)).rgb;
  vec3 k = texture(uSrc, vUv + t * vec2(1.0, 1.0)).rgb;
  vec3 l = texture(uSrc, vUv + t * vec2(-1.0, -1.0)).rgb;
  vec3 m = texture(uSrc, vUv + t * vec2(1.0, -1.0)).rgb;

  vec3 g0 = (a + b + d + e) * 0.25;
  vec3 g1 = (b + c + e + f) * 0.25;
  vec3 g2 = (d + e + g + h) * 0.25;
  vec3 g3 = (e + f + h + i) * 0.25;
  vec3 g4 = (j + k + l + m) * 0.25;

  vec3 col;
  if (uKaris) {
    float w0 = 0.125 * karisWeight(g0);
    float w1 = 0.125 * karisWeight(g1);
    float w2 = 0.125 * karisWeight(g2);
    float w3 = 0.125 * karisWeight(g3);
    float w4 = 0.5 * karisWeight(g4);
    col = (g0 * w0 + g1 * w1 + g2 * w2 + g3 * w3 + g4 * w4) / (w0 + w1 + w2 + w3 + w4);
  } else {
    col = (g0 + g1 + g2 + g3) * 0.125 + g4 * 0.5;
  }
  fragColor = vec4(max(col, 0.0), 1.0);
}
