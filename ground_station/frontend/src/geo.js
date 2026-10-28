// Path smoothing for drawing routes the way the aircraft flies them: a
// fixed-wing QuadPlane can't turn on the spot, so each corner of the planned
// route is rounded with a turn of about its turn radius (~33 m at 15 m/s and
// 35 deg bank); VTOL hops between palms get only a small rounding.

const M_PER_DEG = 111320;

// waypoint labels from flight_software/route_planner.py flown as a fixed-wing
const FIXED_WING = /^(FW |U-turn|approach first stop|line-up|landing approach)/;
export const turnRadius = (label) => (FIXED_WING.test(label || "") ? 30 : 4);

// Round every interior corner of `pts` ([lat, lon]) with radius radii[i]
// (metres), as a quadratic Bezier from the tangent point before the corner to
// the one after; the tangent length is clipped to half of each leg, so short
// legs stay short. Returns a denser [lat, lon] polyline.
export function roundCorners(pts, radii, steps = 10) {
  if (pts.length < 3) return pts;
  const lat0 = pts[0][0], kx = M_PER_DEG * Math.cos((lat0 * Math.PI) / 180);
  const xy = pts.map(([la, lo]) => [lo * kx, la * M_PER_DEG]);
  const back = ([x, y]) => [y / M_PER_DEG, x / kx];
  const out = [pts[0]];
  for (let i = 1; i < xy.length - 1; i++) {
    const [a, b, c] = [xy[i - 1], xy[i], xy[i + 1]];
    const l1 = Math.hypot(b[0] - a[0], b[1] - a[1]), l2 = Math.hypot(c[0] - b[0], c[1] - b[1]);
    if (l1 < 1e-6 || l2 < 1e-6) continue;
    const u1 = [(b[0] - a[0]) / l1, (b[1] - a[1]) / l1], u2 = [(c[0] - b[0]) / l2, (c[1] - b[1]) / l2];
    const turn = Math.acos(Math.max(-1, Math.min(1, u1[0] * u2[0] + u1[1] * u2[1])));   // heading change
    if (turn < 0.02) { out.push(pts[i]); continue; }
    const t = Math.min(radii[i] * Math.tan(turn / 2), l1 / 2, l2 / 2);
    const p1 = [b[0] - u1[0] * t, b[1] - u1[1] * t], p2 = [b[0] + u2[0] * t, b[1] + u2[1] * t];
    for (let k = 0; k <= steps; k++) {
      const s = k / steps, q = 1 - s;
      out.push(back([q * q * p1[0] + 2 * q * s * b[0] + s * s * p2[0], q * q * p1[1] + 2 * q * s * b[1] + s * s * p2[1]]));
    }
  }
  out.push(pts[pts.length - 1]);
  return out;
}

// route items ({lat, lon, label}) -> rounded polyline
export const smoothRoute = (route) => roundCorners(route.map((p) => [p.lat, p.lon]), route.map((p) => turnRadius(p.label)));

// light smoothing of the flown trail (one pass of Chaikin corner cutting):
// removes the 5 Hz zig-zag without moving the track noticeably
export function chaikin(pts) {
  if (pts.length < 3) return pts;
  const out = [pts[0]];
  for (let i = 0; i < pts.length - 1; i++) {
    const [a, b] = [pts[i], pts[i + 1]];
    out.push([0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]], [0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]]);
  }
  out.push(pts[pts.length - 1]);
  return out;
}
