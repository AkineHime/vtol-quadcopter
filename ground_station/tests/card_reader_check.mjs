// Node check for frontend/src/cardReader.js (run by test_card_reader.py):
// synthetic frames of a coloured disc on white paper -> expected stage.
import { classifyPixels } from "../frontend/src/cardReader.js";

function frame(rgb, frac, w = 160, h = 120, paper = [235, 232, 225]) {
  const d = new Uint8ClampedArray(w * h * 4);
  const r = Math.sqrt((frac * w * h) / Math.PI), cx = w / 2, cy = h / 2;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const c = (x - cx) ** 2 + (y - cy) ** 2 < r * r ? rgb : paper;
    d.set([...c, 255], 4 * (y * w + x));
  }
  return [d, w, h];
}

const cases = [
  ["green card", [40, 160, 60], 0.12, "tender", "pre-mature"],
  ["light green card", [190, 235, 170], 0.12, "young", "young"],
  ["yellow card", [235, 205, 40], 0.12, "mature", "mature"],
  ["brown card", [120, 75, 35], 0.12, "over-mature", "over-mature"],
];
const out = [];
for (const [name, rgb, frac, stage, label] of cases) {
  const r = classifyPixels(...frame(rgb, frac));
  out.push({ name, ok: r && r.stage === stage && r.label === label && r.confidence > 0.9, got: r });
}
const tiny = classifyPixels(...frame([40, 160, 60], 0.005));                 // too small to trust
out.push({ name: "tiny card ignored", ok: tiny === null, got: tiny });
const blank = classifyPixels(...frame([235, 232, 225], 0.2));                // just paper
out.push({ name: "blank paper", ok: blank === null, got: blank });
const small = classifyPixels(...frame([40, 160, 60], 0.045));                // partial confidence
out.push({ name: "small card lower confidence", ok: small && small.confidence < 0.9 && small.confidence >= 0.6, got: small });
const far = classifyPixels(...frame([40, 160, 60], 0.03));                   // too far off to trust
out.push({ name: "far card ignored", ok: far === null, got: far });
const noPaper = classifyPixels(...frame([40, 160, 60], 0.12, 160, 120, [40, 44, 42]));   // dark screen, no paper
out.push({ name: "no white paper ignored", ok: noPaper === null, got: noPaper });
// a busy scene: green and yellow patches of similar size on paper -> mixed, no reading
const [mix, mw, mh] = frame([40, 160, 60], 0.08);
for (let y = 0; y < 30; y++) for (let x = 0; x < 50; x++) mix.set([235, 205, 40, 255], 4 * (y * mw + x));
const mixed = classifyPixels(mix, mw, mh);
out.push({ name: "mixed colours ignored", ok: mixed === null, got: mixed });
console.log(JSON.stringify(out));
process.exit(out.every((o) => o.ok) ? 0 : 1);
