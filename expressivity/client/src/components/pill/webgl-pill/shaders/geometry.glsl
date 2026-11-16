// Dish geometry shared by the tracer and the TAA resolve (which re-intersects
// primary rays to find exact motion vectors).
//
// The cross-section is a "U": a floor and a wall, with rounded outer edges, a
// rounded rim and a fillet where the floor meets the wall. Revolved around
// the y axis that is three flat faces, two cylinders and four quarter-tori.
// Flat faces and cylinders are intersected analytically; each torus by sphere
// tracing inside its small bounding box. Normals are exact everywhere, so
// highlights roll smoothly over the edges.

uniform float uRadius;
uniform float uHeight;
uniform float uWall;
uniform float uFloor;
uniform float uBevel;  // radius of the rounded convex edges
uniform float uFillet; // radius of the floor / wall fillet

struct Hit {
  float t;
  vec3 n;   // geometric normal, pointing out of the glass
  int surf; // 0 outer wall, 1 base underside, 2 rim top, 3 inner wall, 4 floor top, 5 rounded edge
};

const float EPS = 1e-5;

// Flat disc / annulus at height y with r in [r0, r1].
void hitDisc(vec3 o, vec3 d, float y, float r0, float r1, float ny, int surf, inout Hit h) {
  if (abs(d.y) < 1e-12) return;
  float t = (y - o.y) / d.y;
  if (t <= EPS || t >= h.t) return;
  vec2 xz = o.xz + d.xz * t;
  float r2 = dot(xz, xz);
  if (r2 < r0 * r0 || r2 > r1 * r1) return;
  h.t = t;
  h.n = vec3(0.0, ny, 0.0);
  h.surf = surf;
}

// Cylinder of radius rad with y in [y0, y1]; s = 1 faces outwards, -1 inwards.
void hitCylinder(vec3 o, vec3 d, float rad, float y0, float y1, float s, int surf, inout Hit h) {
  float a = dot(d.xz, d.xz);
  if (a < 1e-12) return;
  float b = dot(o.xz, d.xz);
  float disc = b * b - a * (dot(o.xz, o.xz) - rad * rad);
  if (disc < 0.0) return;
  float sq = sqrt(disc);
  for (int k = 0; k < 2; k++) {
    float t = (-b + (k == 0 ? -sq : sq)) / a;
    if (t <= EPS || t >= h.t) continue;
    float y = o.y + d.y * t;
    if (y < y0 || y > y1) continue;
    vec2 xz = o.xz + d.xz * t;
    h.t = t;
    h.n = vec3(xz.x, 0.0, xz.y) * (s / rad);
    h.surf = surf;
    return;
  }
}

// First crossing of the torus (tube rho around the circle of radius rc at
// height yc) between ta and tb. Sphere tracing gets close, then Newton steps
// finish the job; plain sphere tracing crawls at grazing angles, which is
// exactly where edge highlights are. convex: the glass is inside the tube.
void marchTorus(vec3 o, vec3 d, float rc, float yc, float rho, float ta, float tb, bool convex, inout Hit h) {
  tb = min(tb, h.t);
  float t = ta;
  bool near = false;
  for (int i = 0; i < 24; i++) {
    if (t > tb) return;
    vec3 p = o + d * t;
    float g = length(vec2(length(p.xz) - rc, p.y - yc)) - rho;
    if (abs(g) < 1e-3) {
      near = true;
      break;
    }
    t += abs(g);
  }
  if (!near) return;
  vec2 q;
  vec2 radial;
  for (int i = 0; i < 5; i++) {
    vec3 p = o + d * t;
    float r = max(length(p.xz), 1e-6);
    radial = p.xz / r;
    q = vec2(r - rc, p.y - yc);
    float lq = max(length(q), 1e-9);
    float g = lq - rho;
    vec2 n2 = q / lq;
    float slope = dot(vec3(n2.x * radial.x, n2.y, n2.x * radial.y), d);
    if (abs(slope) < 1e-5) return; // the ray just grazes the tube
    t -= g / slope;
  }
  vec3 p = o + d * t;
  float r = max(length(p.xz), 1e-6);
  radial = p.xz / r;
  q = vec2(r - rc, p.y - yc);
  if (abs(length(q) - rho) > 1e-5 || t <= EPS || t < ta - 1e-4 || t > tb) return;
  vec2 n2 = normalize(q) * (convex ? 1.0 : -1.0);
  h.t = t;
  h.n = vec3(n2.x * radial.x, n2.y, n2.x * radial.y);
  h.surf = 5;
}

// The quarter of that torus inside the meridian box r in rr, y in yr.
void hitTorus(vec3 o, vec3 d, float rc, float yc, float rho, vec2 rr, vec2 yr, bool convex, inout Hit h) {
  if (rho <= 0.0) return;
  float tlo = EPS;
  float thi = h.t;
  if (abs(d.y) < 1e-12) {
    if (o.y < yr.x || o.y > yr.y) return;
  } else {
    float ta = (yr.x - o.y) / d.y;
    float tb = (yr.y - o.y) / d.y;
    tlo = max(tlo, min(ta, tb));
    thi = min(thi, max(ta, tb));
  }
  if (tlo >= thi) return;
  // r(t)^2 = A t^2 + 2 B t + C must stay within [rr.x^2, rr.y^2].
  float A = dot(d.xz, d.xz);
  float B = dot(o.xz, d.xz);
  float C = dot(o.xz, o.xz);
  // Cheap reject first: r^2 is a convex quadratic, so over [tlo, thi] its
  // largest value is at an end and its smallest at an end or the vertex.
  float r2lo = (A * tlo + 2.0 * B) * tlo + C;
  float r2hi = (A * thi + 2.0 * B) * thi + C;
  float r2min = min(r2lo, r2hi);
  if (A > 1e-12) {
    float tv = -B / A;
    if (tv > tlo && tv < thi) r2min = C - B * B / A;
  }
  if (max(r2lo, r2hi) < rr.x * rr.x || r2min > rr.y * rr.y) return;
  // Narrow to where r <= rr.y; the ray may dip inside r = rr.x part way,
  // which splits that span in two. One march call in a loop keeps the shader
  // small (it is inlined at every intersection).
  float a0 = tlo, b0 = thi, a1 = 1.0, b1 = 0.0;
  if (A > 1e-12) {
    float discOut = B * B - A * (C - rr.y * rr.y);
    if (discOut <= 0.0) return;
    float sOut = sqrt(discOut);
    a0 = max(tlo, (-B - sOut) / A);
    b0 = min(thi, (-B + sOut) / A);
    float discIn = B * B - A * (C - rr.x * rr.x);
    if (discIn > 0.0) {
      float sIn = sqrt(discIn);
      a1 = max(a0, (-B + sIn) / A);
      b1 = b0;
      b0 = min(b0, (-B - sIn) / A);
    }
  } else if (C < rr.x * rr.x || C > rr.y * rr.y) {
    return;
  }
  for (int piece = 0; piece < 2; piece++) {
    float ta = piece == 0 ? a0 : a1;
    float tb = piece == 0 ? b0 : b1;
    if (ta < tb) marchTorus(o, d, rc, yc, rho, ta, tb, convex, h);
  }
}

bool intersectDish(vec3 ro, vec3 rd, out Hit h) {
  float R = uRadius;
  float h2 = uHeight * 0.5;
  float Ri = R - uWall;
  float yf = -h2 + uFloor;
  float e = uBevel;
  float f = uFillet;

  // Everything lies inside the outer cylinder; skip rays that miss it and
  // never look past where they leave it.
  h.t = 1e30;
  h.n = vec3(0.0, 1.0, 0.0);
  h.surf = 0;
  float a = dot(rd.xz, rd.xz);
  float b = dot(ro.xz, rd.xz);
  float c = dot(ro.xz, ro.xz) - R * R;
  float tEnter = -1e30;
  float tExit = 1e30;
  if (a > 1e-12) {
    float disc = b * b - a * c;
    if (disc < 0.0) return false;
    float sq = sqrt(disc);
    tEnter = (-b - sq) / a;
    tExit = (-b + sq) / a;
  } else if (c > 0.0) {
    return false;
  }
  if (abs(rd.y) > 1e-12) {
    float ta = (-h2 - ro.y) / rd.y;
    float tb = (h2 - ro.y) / rd.y;
    tEnter = max(tEnter, min(ta, tb));
    tExit = min(tExit, max(ta, tb));
  } else if (abs(ro.y) > h2) {
    return false;
  }
  if (tExit < EPS || tEnter > tExit) return false;
  h.t = tExit + 1e-4;

  hitDisc(ro, rd, -h2, 0.0, R - e, -1.0, 1, h);
  hitCylinder(ro, rd, R, -h2 + e, h2 - e, 1.0, 0, h);
  hitDisc(ro, rd, h2, Ri + e, R - e, 1.0, 2, h);
  hitCylinder(ro, rd, Ri, yf + f, h2 - e, -1.0, 3, h);
  hitDisc(ro, rd, yf, 0.0, Ri - f, 1.0, 4, h);
  // The four rounded edges: outer bottom, outer top, rim inner edge and the
  // floor fillet (the only concave one).
  for (int k = 0; k < 4; k++) {
    float rc = k < 2 ? R - e : (k == 2 ? Ri + e : Ri - f);
    float yc = k == 0 ? -h2 + e : (k == 3 ? yf + f : h2 - e);
    float rho = k == 3 ? f : e;
    vec2 rr = k < 2 ? vec2(R - e, R) : (k == 2 ? vec2(Ri, Ri + e) : vec2(Ri - f, Ri));
    vec2 yr = k == 0 ? vec2(-h2, -h2 + e) : (k == 3 ? vec2(yf, yf + f) : vec2(h2 - e, h2));
    hitTorus(ro, rd, rc, yc, rho, rr, yr, k != 3, h);
  }

  return h.t < tExit + 1e-4;
}
