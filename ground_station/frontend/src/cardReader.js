// Colour-card reader: a stand-in classifier while the phone plays the drone
// camera. A coloured shape on white paper held in view tells the maturity:
//   green = tender (pre-mature, the harvest target)   light green = young
//   yellow = mature                                    brown = over-mature
// Only colour is read. Shape would carry health (circle healthy, triangle
// frond damage, square pest), but nothing detects health yet, so it is left out.
//
// classifyPixels() is pure (RGBA bytes in, result out) so it can be unit-tested
// without a browser; readCard() runs it on a canvas.

export const CARD_MODEL = "colour-card-v1";
const MIN_AREA = 0.02;     // the card colour must cover >= 2% of the frame
const FULL_AREA = 0.06;    // ...and is fully trusted from 6%
const MIN_PAPER = 0.15;    // white paper must fill >= 15% (a busy scene is not a card)
const MIN_CONF = 0.6;      // below this the photo is kept as a plain visit, not a reading

function hsv(r, g, b) {
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0;
  if (d) {
    if (mx === r) h = ((g - b) / d) % 6;
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h = (h * 60 + 360) % 360;
  }
  return [h, mx ? d / mx : 0, mx / 255];
}

// one pixel -> stage, or null for paper, shadows and other colours
export function stageOf(r, g, b) {
  const [h, s, v] = hsv(r, g, b);
  if (s < 0.2 || v < 0.18) return null;                   // white paper (s ~0.05), grey, black
  if (h >= 10 && h < 45 && v < 0.62) return "over-mature";  // brown = dark orange
  if (h >= 38 && h < 70) return "mature";                  // yellow
  if (h >= 70 && h < 170) return v > 0.72 && s < 0.5 ? "young" : "tender";
  return null;
}

const LABEL = { tender: "pre-mature", young: "young", mature: "mature", "over-mature": "over-mature" };

export function classifyPixels(data, w, h) {
  const counts = {};
  let coloured = 0, paper = 0;
  for (let i = 0; i < w * h; i++) {
    const r = data[4 * i], g = data[4 * i + 1], b = data[4 * i + 2];
    const st = stageOf(r, g, b);
    if (st) { counts[st] = (counts[st] || 0) + 1; coloured++; }
    else {
      const [, sat, val] = hsv(r, g, b);
      if (sat < 0.2 && val > 0.7) paper++;
    }
  }
  const best = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
  const area = best ? counts[best] / (w * h) : 0;
  if (!best || area < MIN_AREA || paper / (w * h) < MIN_PAPER) return null;
  const purity = counts[best] / coloured;
  const confidence = +(purity * Math.min(1, area / FULL_AREA)).toFixed(2);
  if (confidence < MIN_CONF) return null;              // mixed colours or a far-off card: no reading
  return { stage: best, label: LABEL[best], area: +area.toFixed(3), confidence };
}

export function readCard(canvas) {
  const w = 160, h = Math.max(1, Math.round((160 * canvas.height) / canvas.width));
  const small = document.createElement("canvas");
  small.width = w;
  small.height = h;
  const ctx = small.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(canvas, 0, 0, w, h);
  return classifyPixels(ctx.getImageData(0, 0, w, h).data, w, h);
}
