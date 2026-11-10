// Node check for frontend/src/checks.js (run by test_checks.py).
import { diffAlerts, goNoGo, LIMITS, remaining, windNow } from "../frontend/src/checks.js";

const results = [];
const ok = (name, cond, got) => results.push({ name, ok: !!cond, got });

const tel = { connected: true, mode: "AUTO", armed: false, alt: 0, battery: 100, gps_fix: 3, gps_sats: 12, wind_speed: 0.4 };
const plan = { battery_pct: 78, budget_pct: 80, dropped: [] };

// wind source: entered value on the ground, autopilot estimate once airborne
ok("wind: entered on ground", windNow(tel, { speed: 4, gust: 6 }).source === "entered");
ok("wind: estimate airborne", windNow({ ...tel, alt: 30, wind_speed: 7 }, { speed: 4 }).speed === 7);
ok("wind: unknown", windNow({ connected: false }, null) === null);

// go / no-go
let g = goNoGo({ tel, wind: { speed: 3, gust: 5 }, plan });
ok("go in calm air", g.overall === "go", g);
g = goNoGo({ tel, wind: { speed: 5.5, gust: 6 }, plan });
ok("caution 5-6 m/s", g.overall === "caution" && g.checks[0].state === "caution", g);
g = goNoGo({ tel, wind: { speed: 6.5, gust: 8 }, plan });
ok("no-go above 6 m/s", g.overall === "no-go" && g.checks[0].state === "no-go", g);
g = goNoGo({ tel, wind: { speed: 4, gust: LIMITS.gustNoGo + 1 }, plan });
ok("no-go on gusts", g.checks[0].state === "no-go", g);
g = goNoGo({ tel: { connected: false }, wind: { speed: 2 }, plan });
ok("no-go without link", g.overall === "no-go" && g.checks.find((c) => c.key === "link").state === "no-go", g);
g = goNoGo({ tel: { ...tel, gps_sats: 6 }, wind: { speed: 2 }, plan });
ok("GPS few satellites -> caution", g.checks.find((c) => c.key === "gps").state === "caution", g);
g = goNoGo({ tel, wind: null, plan: { ...plan, dropped: ["P0001"] } });
ok("unknown wind + dropped palms -> caution", g.overall === "caution", g);

// remaining energy and landing projection
const mission = { route: [{ seq: 1 }, { seq: 5, tree: "A" }, { seq: 7, tree: "B" }, { seq: 9, tree: "C" }, { seq: 10 }] };
let r = remaining(mission, { ...tel, armed: true, wp: 6, battery: 30 });
ok("2 stops left", r.left.length === 2 && r.current.tree === "B", r);
ok("landing projection", Math.abs(r.landingPct - (30 - (100 * (2 * 1.2 + 0.9)) / 44.4)) < 1e-9, r);

// alerts
const t0 = { P1: { status: "unscouted", maturity: "unknown", row: 0, col: 1 } };
let a = diffAlerts(null, { tel, trees: t0, plan });
ok("nothing on page load", a.alerts.length === 0, a);
a = diffAlerts({ tel, trees: t0, plan }, { tel, trees: { P1: { ...t0.P1, status: "target" } }, plan });
ok("target found", a.alerts.length === 1 && a.alerts[0].title === "Target found: P1", a);
a = diffAlerts({ tel, trees: t0, plan }, { tel, trees: { P1: { ...t0.P1, maturity: "tender", label: "pre-mature", confidence: 0.9, last_visit: "x" } }, plan });
ok("tender sighting", a.alerts.length === 1 && a.alerts[0].title === "Tender nuts at P1", a);
a = diffAlerts({ tel, trees: t0 }, { tel: { connected: false }, trees: t0 });
ok("link lost is critical + sticky", a.alerts[0]?.level === "critical" && a.alerts[0].sticky, a);
a = diffAlerts({ tel: { connected: false, everConnected: true }, trees: t0 }, { tel, trees: t0 });
ok("link restored clears it", a.clear.includes("link") && a.alerts[0].title === "Drone link restored", a);
a = diffAlerts({ tel, trees: t0, plan }, { tel, trees: t0, plan: { ...plan, dropped: ["X", "Y"] } });
ok("palms left out", a.alerts[0]?.title === "Battery limit reached", a);
a = diffAlerts({ tel, trees: t0, landingPct: 35 }, { tel, trees: t0, landingPct: 15 });
ok("projected landing under reserve", a.alerts[0]?.title === "Battery over limit", a);
a = diffAlerts({ tel, trees: t0, landingPct: 15 }, { tel, trees: t0, landingPct: 15 });
ok("not repeated", a.alerts.length === 0, a);

console.log(JSON.stringify(results));
process.exit(results.every((x) => x.ok) ? 0 : 1);
