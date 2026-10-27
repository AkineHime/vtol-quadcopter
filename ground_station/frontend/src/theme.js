// Colours and vocabularies shared by the map, legend, sidebar and inspector.
// A palm has four separate things (backend/db.py):
//   maturity  what its nuts are now   unknown | young | tender | mature | over-mature
//   health    the palm itself          healthy | frond-damage | pest
//   status    the harvest workflow     unscouted | target | confirmed | harvested
//   ripe_score  predicted chance of tender nuts now (backend/ripeness.py)
// On the map one glyph shows several at once: fill = the lens colour, ring =
// harvest status, red notch = a health issue.
export const TINT = "#e3a06a";

export const MATURITY = {
  unknown: { label: "Not seen yet", color: "#59615d" },
  young: { label: "Young", color: "#b5e3a1" },
  tender: { label: "Tender · harvest", color: "#3fd46a" },
  mature: { label: "Mature", color: "#ffcc4d" },
  "over-mature": { label: "Over-mature", color: "#a8744a" },
};

export const HEALTH = {
  healthy: { label: "Healthy", color: "#3a7d52" },
  "frond-damage": { label: "Frond damage", color: "#ff453a" },
  pest: { label: "Pest", color: "#bf5af2" },
};

// ring colours (null = no ring)
export const STATUS = {
  unscouted: { label: "Unscouted", color: "#8e8e93", ring: null },
  target: { label: "Target", color: TINT, ring: TINT },
  confirmed: { label: "Confirmed", color: "#ffd60a", ring: "#ffd60a" },
  harvested: { label: "Harvested", color: "#30d158", ring: "#6e6e73" },
};

// detector labels (ml/ and the colour card) -> maturity
export const LABEL_STAGE = { "pre-mature": "tender", tender: "tender", young: "young", mature: "mature", "over-mature": "over-mature" };

export const PHOTO = {
  skip: { label: "Not in pattern", color: "#3a3a3c" },
  todo: { label: "To photograph", color: TINT },
  done: { label: "Photographed", color: "#30d158" },
};

// prediction heat: dark -> amber -> pale gold
export const PREDICT_MIN = 0.5;
const HEAT = [[0, [44, 51, 47]], [0.35, [92, 84, 58]], [0.5, [214, 140, 52]], [0.75, [255, 179, 64]], [1, [255, 226, 140]]];
export const heat = (s) => {
  const v = Math.max(0, Math.min(1, s ?? 0));
  const i = HEAT.findIndex(([x]) => x >= v);
  const [x1, c1] = HEAT[Math.max(0, i)], [x0, c0] = HEAT[Math.max(0, i - 1)];
  const t = x1 === x0 ? 0 : (v - x0) / (x1 - x0);
  return "#" + c0.map((c, k) => Math.round(c + (c1[k] - c) * t).toString(16).padStart(2, "0")).join("");
};

export const LENSES = [["harvest", "Harvest"], ["prediction", "Prediction"], ["health", "Health"], ["photos", "Photos"]];

export const GRID = 13;

export const photoState = (tree, pattern) => {
  if ((tree.row * GRID + tree.col) % (pattern.every || 1) !== 0) return "skip";
  return tree.last_photo && tree.last_photo >= (pattern.since || "") ? "done" : "todo";
};

// fill colour of a palm under a lens
export const colorOf = (tree, lens, pattern) =>
  lens === "photos" ? PHOTO[photoState(tree, pattern)].color
    : lens === "prediction" ? heat(tree.ripe_score)
      : lens === "health" ? (HEALTH[tree.health] || HEALTH.healthy).color
        : (MATURITY[tree.maturity] || MATURITY.unknown).color;

export const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso), today = new Date();
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return d.toDateString() === today.toDateString() ? `Today, ${time}`
    : `${d.toLocaleDateString([], { day: "numeric", month: "short" })}, ${time}`;
};

export const fmtNum = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(digits);

export const fmtPct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
