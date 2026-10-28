#!/usr/bin/env python3
"""
report_runs.py -- one pass/fail table from every demo/runs/*/summary.json.

    python report_runs.py [--out ../documents/sim_results_table.md]

Pass criteria (deployment, not demo):
  landed on the dock, no crash; crown clearance >= 2 m; |roll| < 60 deg;
  battery <= 80 % (usable); imaging: sweeps >= 95 % of palms with >= 2
  frames, hover/hybrid >= 90 % of targets with >= 2 frames.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "demo" / "runs"


def verdict(s):
    why = []
    if s.get("test"):                  # staged flight test (hover/transition): only safety counts
        clear = s.get("min_crown_clearance_m") or 0
        ok = (s.get("max_abs_roll") or 0) < 60 and clear >= 2 and (s.get("flight_s") or 0) > 0
        return ("TEST OK" if ok else "TEST FAIL"), f"{s['test']} test"
    fl = s.get("flight") or {}
    if not (fl.get("landed") and not fl.get("crashed")):
        why.append("no clean landing")
    if (s.get("min_crown_clearance_m") or 0) < 2:
        why.append(f"clearance {s.get('min_crown_clearance_m')} m")
    if (s.get("max_abs_roll") or 0) >= 60:
        why.append(f"roll {s.get('max_abs_roll')}")
    if (s.get("battery_used_pct") or 0) > 80:
        why.append(f"battery {s.get('battery_used_pct')} %")
    if s.get("n_targets"):
        ok = (s.get("targets_imaged_2plus") or 0) >= 0.9 * s["n_targets"]
        if not ok:
            why.append(f"targets imaged {s.get('targets_imaged_2plus')}/{s['n_targets']}")
    elif (s.get("trees_imaged_2plus") or 0) < 0.95 * 169:
        why.append(f"palms imaged {s.get('trees_imaged_2plus')}/169")
    return ("PASS" if not why else "FAIL"), "; ".join(why)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = []
    for p in sorted(RUNS.glob("*/summary.json")):
        s = json.loads(p.read_text())
        v, why = verdict(s)
        dist = s.get("events") and Path(s["events"]).stem.replace("_events", "") or ""
        if s.get("param_files"):
            dist = ",".join(Path(f).stem for f in s["param_files"])
        w = s.get("wind_ne") or [0, 0]
        wind = f"{(w[0] ** 2 + w[1] ** 2) ** 0.5:.0f} m/s" + (f" +gust {s['gust']:g}" if s.get("gust") else "")
        img = (f"{s.get('targets_imaged_2plus')}/{s['n_targets']} targets" if s.get("n_targets")
               else f"{s.get('trees_imaged_2plus')}/169 palms")
        rows.append([s["name"] + (" (jsbsim)" if s.get("physics") == "jsbsim" else ""), s.get("test") or s["strategy"], wind, dist or "-", s.get("flight_s"), s.get("energy_wh"),
                     s.get("battery_used_pct"), img, s.get("min_crown_clearance_m"), s.get("max_abs_roll"),
                     s.get("lift_events"), v, why])
    hdr = ["run", "strategy", "wind", "disturbance", "flight s", "Wh", "batt %", "imaged >=2 frames",
           "min clear m", "max roll", "lift on/off", "verdict", "why"]
    md = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    md += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    text = "\n".join(md)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
