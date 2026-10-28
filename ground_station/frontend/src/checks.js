// Go / no-go checks, the flight's remaining-energy projection, and alert rules.
// Pure functions (no React, no DOM) so tests/checks_check.mjs can run them in Node.
//
// Limits come from the simulation study (documents/sim_results.md): 5 m/s mean
// wind with 2 m/s gusts flew fine; 8 m/s with 3 m/s gusts stayed controllable in
// JSBSim but imaging fell to 79% (Gazebo crashed), so the operating limit is
// about 6 m/s mean. The gust limits are provisional until real flights.
export const LIMITS = {
  windGo: 5, windNoGo: 6,          // m/s mean
  gustCaution: 7, gustNoGo: 9,     // m/s
  landingReservePct: 20,           // land with >= 20% battery (the planner's 80% rule)
  gpsSats: 8,
  battWh: 44.4,
};

const RANK = { go: 0, caution: 1, "no-go": 2 };
const worst = (states) => states.reduce((a, b) => (RANK[b] > RANK[a] ? b : a), "go");

// which wind to judge: the autopilot's estimate once airborne, else what the
// operator entered, else the autopilot's estimate on the ground
export function windNow(tel, manual) {
  const airborne = tel?.connected && (tel.alt ?? 0) > 5 && tel.wind_speed != null;
  if (airborne) return { speed: tel.wind_speed, gust: null, dir: tel.wind_dir, source: "autopilot estimate" };
  if (manual) return { speed: manual.speed, gust: manual.gust, dir: null, source: "entered" };
  if (tel?.connected && tel.wind_speed != null) return { speed: tel.wind_speed, gust: null, dir: tel.wind_dir, source: "autopilot estimate" };
  return null;
}

export function goNoGo({ tel = {}, wind = null, plan = null }) {
  const checks = [];
  const w = windNow(tel, wind);
  if (!w) {
    checks.push({ key: "wind", label: "Wind", state: "caution", detail: "unknown: enter it below" });
  } else {
    let s = w.speed > LIMITS.windNoGo ? "no-go" : w.speed > LIMITS.windGo ? "caution" : "go";
    if (w.gust != null) s = worst([s, w.gust > LIMITS.gustNoGo ? "no-go" : w.gust > LIMITS.gustCaution ? "caution" : "go"]);
    checks.push({ key: "wind", label: "Wind", state: s,
      detail: `${w.speed.toFixed(1)} m/s${w.gust != null ? `, gusts ${w.gust.toFixed(1)}` : ""} (${w.source})` });
  }
  if (plan) {
    const over = plan.battery_pct > plan.budget_pct;
    checks.push({ key: "battery", label: "Battery plan", state: over ? "no-go" : plan.dropped?.length ? "caution" : "go",
      detail: `${plan.battery_pct}% of ${plan.budget_pct}% allowed` + (plan.dropped?.length ? `, ${plan.dropped.length} palms left out` : "") });
  }
  if (tel.connected && tel.battery != null && !(tel.alt > 5)) {
    checks.push({ key: "charge", label: "Battery charge", state: tel.battery >= 90 ? "go" : tel.battery >= 70 ? "caution" : "no-go",
      detail: `${tel.battery}%` });
  }
  checks.push({ key: "link", label: "Drone link", state: tel.connected ? "go" : "no-go",
    detail: tel.connected ? (tel.mode || "connected") : "no telemetry" });
  if (tel.connected) {
    const fix = tel.gps_fix ?? 0, sats = tel.gps_sats ?? 0;
    checks.push({ key: "gps", label: "GPS", state: fix < 3 ? "no-go" : sats < LIMITS.gpsSats ? "caution" : "go",
      detail: fix < 3 ? "no 3D fix" : `3D fix, ${sats} satellites` });
  }
  return { overall: worst(checks.map((c) => c.state)), checks };
}

// What is left of the mission being flown, from the JSBSim figures
// (backend/planner.py): ~18 s and 1.2 Wh per stop, 40 s / 0.9 Wh to land,
// a sweep of ~150 s / 7.3 Wh.
const STOP_S = 18, STOP_WH = 1.2, LAND_S = 40, LAND_WH = 0.9, SWEEP_S = 150, SWEEP_WH = 7.3;

export function remaining(mission, tel = {}) {
  const stops = (mission?.route || []).filter((r) => r.tree);
  if (!stops.length) return null;
  const flying = !!(tel.connected && tel.armed && tel.wp != null && tel.wp > 0);
  const wp = flying ? tel.wp : 0;
  const left = stops.filter((s) => s.seq >= wp);
  const sweepLeft = wp < stops[0].seq ? (stops[0].seq - wp) / Math.max(1, stops[0].seq - 1) : 0;
  const wh = left.length * STOP_WH + LAND_WH + sweepLeft * SWEEP_WH;
  const landingPct = flying && tel.battery != null ? tel.battery - (100 * wh) / LIMITS.battWh : null;
  return { flying, wp, stops, left, current: stops.find((s) => s.seq >= wp),
    secs: left.length * STOP_S + LAND_S + sweepLeft * SWEEP_S, wh, landingPct };
}

// Alerts from one state to the next: [{id, level: info|warn|critical, title, body, sticky}]
// plus `clear`: ids of sticky alerts that are resolved. state = {tel, trees: {id: tree},
// plan, landingPct, go}. Nothing fires on the first state (page load).
export function diffAlerts(prev, next) {
  const out = [], clear = [];
  if (!prev) return { alerts: out, clear };
  // link
  if (prev.tel?.connected && !next.tel?.connected) {
    out.push({ id: "link", level: "critical", sticky: true, title: "Drone link lost",
      body: next.tel?.error ? `No telemetry: ${next.tel.error}` : "No telemetry from the autopilot." });
  } else if (!prev.tel?.connected && next.tel?.connected && prev.tel?.everConnected) {
    clear.push("link");
    out.push({ id: "link-back", level: "info", title: "Drone link restored", body: next.tel.mode || "" });
  }
  // targets and tender sightings
  if (prev.trees && next.trees) {
    for (const [id, t] of Object.entries(next.trees)) {
      const p = prev.trees[id];
      if (!p) continue;
      const nowTarget = t.status === "target" && p.status !== "target";
      const tender = t.maturity === "tender" && t.label && (p.maturity !== "tender" || p.last_visit !== t.last_visit) && t.last_visit;
      if (nowTarget || tender) {
        out.push({ id: "tree-" + id + "-" + (t.last_visit || t.updated_at), level: "info", title: nowTarget ? `Target found: ${id}` : `Tender nuts at ${id}`,
          body: [t.label && `${t.label}${t.confidence != null ? ` ${Math.round(t.confidence * 100)}%` : ""}`,
            `row ${t.row}, col ${t.col}`].filter(Boolean).join(" · "), tree: id });
      }
    }
  }
  // battery: palms left out of the plan; projected landing below the reserve
  const d0 = prev.plan?.dropped?.length || 0, d1 = next.plan?.dropped?.length || 0;
  if (d1 > d0) {
    out.push({ id: "plan-over", level: "warn", title: "Battery limit reached",
      body: `${d1} predicted palm${d1 > 1 ? "s don't" : " doesn't"} fit the 80% battery rule and ${d1 > 1 ? "are" : "is"} left out of the next mission.` });
  }
  const r = LIMITS.landingReservePct;
  if (next.landingPct != null && next.landingPct < r && !(prev.landingPct != null && prev.landingPct < r)) {
    out.push({ id: "landing-low", level: "warn", sticky: true, title: "Battery over limit",
      body: `Projected ${Math.max(0, Math.round(next.landingPct))}% at landing (reserve ${r}%). Consider skipping stops.` });
  } else if (prev.landingPct != null && prev.landingPct < r && (next.landingPct == null || next.landingPct >= r)) {
    clear.push("landing-low");
  }
  // go / no-go turning red
  if (prev.go && next.go && prev.go.overall !== "no-go" && next.go.overall === "no-go") {
    const bad = next.go.checks.filter((c) => c.state === "no-go").map((c) => `${c.label}: ${c.detail}`).join("; ");
    out.push({ id: "nogo-" + bad, level: "warn", title: "No-go", body: bad });
  }
  return { alerts: out, clear };
}
