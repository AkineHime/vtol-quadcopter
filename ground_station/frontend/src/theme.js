// Colours (Apple dark-mode system palette + a copper tint) shared by the map,
// legend, sidebar and inspector.
export const TINT = "#e3a06a";

export const STATUS = {
  unscouted: { label: "Unscouted", color: "#8e8e93" },
  target: { label: "Target", color: TINT },
  cleared: { label: "Cleared", color: "#30d158" },
};

export const CONDITION = {
  healthy: { label: "Healthy", color: "#30d158" },
  ripe: { label: "Ripe", color: "#ffd60a" },
  frond: { label: "Frond issue", color: "#ff453a" },
  "ripe+frond": { label: "Ripe + frond", color: "#bf5af2" },
};

export const PHOTO = {
  skip: { label: "Not in pattern", color: "#3a3a3c" },
  todo: { label: "To photograph", color: TINT },
  done: { label: "Photographed", color: "#30d158" },
};

export const GRID = 13;

export const photoState = (tree, pattern) => {
  if ((tree.row * GRID + tree.col) % (pattern.every || 1) !== 0) return "skip";
  return tree.last_photo && tree.last_photo >= (pattern.since || "") ? "done" : "todo";
};

export const colorOf = (tree, by, pattern) =>
  (by === "condition" ? CONDITION[tree.condition]
    : by === "photos" ? PHOTO[photoState(tree, pattern)]
      : STATUS[tree.status])?.color || "#8e8e93";

export const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso), today = new Date();
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return d.toDateString() === today.toDateString() ? `Today, ${time}`
    : `${d.toLocaleDateString([], { day: "numeric", month: "short" })}, ${time}`;
};

export const fmtNum = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(digits);
