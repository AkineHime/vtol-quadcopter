// Pixel-art relief background, after the extruded "voxel" relief maps: the
// country around the farm as a grid of small square pyramids (lit from the
// top-left, shaded bottom-right), heights from smooth value noise, quantised
// into a few dark-green bands so it sits behind the dashboard without
// competing with the palms. Drawn once into a canvas; no tiles, works offline.

const BANDS = ["#121a15", "#15201a", "#19271f", "#1e2f24", "#233728", "#2a412d", "#324b33"];

function rng(seed) {                       // small deterministic PRNG (mulberry32)
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function valueNoise(n, seed) {             // n x n field, 4 octaves of smoothed lattice noise
  const r = rng(seed);
  const out = new Float32Array(n * n);
  let amp = 1, total = 0;
  for (let oct = 0; oct < 4; oct++) {
    const g = 4 << oct, lat = Array.from({ length: (g + 1) * (g + 1) }, r);
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      const fx = (x / n) * g, fy = (y / n) * g, x0 = Math.floor(fx), y0 = Math.floor(fy);
      const sx = (fx - x0) ** 2 * (3 - 2 * (fx - x0)), sy = (fy - y0) ** 2 * (3 - 2 * (fy - y0));
      const v = (i, j) => lat[j * (g + 1) + i];
      const a = v(x0, y0) + (v(x0 + 1, y0) - v(x0, y0)) * sx, b = v(x0, y0 + 1) + (v(x0 + 1, y0 + 1) - v(x0, y0 + 1)) * sx;
      out[y * n + x] += (a + (b - a) * sy) * amp;
    }
    total += amp;
    amp *= 0.5;
  }
  for (let i = 0; i < out.length; i++) out[i] /= total;
  return out;
}

const shade = (hex, k) => {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.max(0, Math.min(255, Math.round(v * k))));
  return `rgb(${c.join(",")})`;
};

// -> data URL of an n x n relief, `px` canvas pixels per cell. The blur and
// the faded edge are baked in here, once: CSS filters on the map would be
// re-rasterised on every frame of a pan or zoom.
export function reliefImage(n = 150, px = 10, seed = 7, { blur = 0, fade = false } = {}) {
  const h = valueNoise(n, seed);
  const c = document.createElement("canvas");
  c.width = c.height = n * px;
  const g = c.getContext("2d");
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const v = h[y * n + x];
    const band = Math.min(BANDS.length - 1, Math.max(0, Math.floor((v - 0.25) / 0.5 * BANDS.length)));
    const col = BANDS[band], x0 = x * px, y0 = y * px, m = px / 2;
    const peak = [x0 + m - band * 0.25, y0 + m - band * 0.25];       // taller bands lean the apex up-left
    const tri = (a, b, k) => { g.fillStyle = shade(col, k); g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.lineTo(...peak); g.fill(); };
    tri([x0, y0], [x0 + px, y0], 1.28);              // top face: lit
    tri([x0, y0], [x0, y0 + px], 1.12);              // left face
    tri([x0 + px, y0], [x0 + px, y0 + px], 0.86);    // right face
    tri([x0, y0 + px], [x0 + px, y0 + px], 0.72);    // bottom face: shade
  }
  if (!blur && !fade) return c.toDataURL("image/png");
  const o = document.createElement("canvas");
  o.width = o.height = c.width;
  const og = o.getContext("2d");
  og.filter = blur ? `blur(${blur}px)` : "none";
  og.drawImage(c, 0, 0);
  og.filter = "none";
  if (fade) {                                    // soft round edge into the coarse layer below
    const r = o.width / 2, gr = og.createRadialGradient(r, r, r * 0.72, r, r, r);
    gr.addColorStop(0, "#000");
    gr.addColorStop(1, "rgba(0,0,0,0)");
    og.globalCompositeOperation = "destination-in";
    og.fillStyle = gr;
    og.fillRect(0, 0, o.width, o.height);
  }
  return o.toDataURL("image/png");
}
