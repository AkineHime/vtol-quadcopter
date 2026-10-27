// Colours shared by the map, legend, side panel and detail card.
export const STATUS = {
  unscouted: { label: "Unscouted", color: "#7d9686" },
  target: { label: "Target", color: "#d4894f" },
  cleared: { label: "Cleared", color: "#5cc486" },
};

export const CONDITION = {
  healthy: { label: "Healthy", color: "#4fa96c" },
  ripe: { label: "Ripe", color: "#e3bb4c" },
  frond: { label: "Frond issue", color: "#de6a55" },
  "ripe+frond": { label: "Ripe + frond", color: "#c47ad6" },
};

export const colorOf = (tree, by) =>
  (by === "condition" ? CONDITION[tree.condition] : STATUS[tree.status])?.color || "#888";

export const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString() : "—");
export const fmtNum = (v, digits = 1, unit = "") =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${Number(v).toFixed(digits)}${unit}`;
