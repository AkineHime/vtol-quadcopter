#!/usr/bin/env python3
"""reanalyze.py -- re-run analysis.py on every demo/runs/*/flight.BIN (e.g. after
changing the camera trigger rate) and refresh analysis.json + summary.json.

    python reanalyze.py [--fps 5] [RUN ...]
"""
import argparse
import json
from pathlib import Path

import analysis

RUNS = Path(__file__).resolve().parent / "demo" / "runs"
KEYS = ("flight_s", "distance_m", "energy_wh", "battery_used_pct", "trees_imaged", "trees_imaged_2plus",
        "targets_imaged_2plus", "target_frames_median", "frames_per_tree_median", "frames_total",
        "min_crown_clearance_m", "max_abs_roll", "max_abs_pitch")

ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="*")
ap.add_argument("--fps", type=float, default=5.0)
a = ap.parse_args()
for d in sorted(RUNS.iterdir()):
    if (a.runs and d.name not in a.runs) or not (d / "flight.BIN").exists() or not (d / "summary.json").exists():
        continue
    res = analysis.analyse(d / "flight.BIN", a.fps)
    (d / "analysis.json").write_text(json.dumps(res, indent=1))
    s = json.loads((d / "summary.json").read_text())
    s.update({k: res.get(k) for k in KEYS})
    s["lift_events"] = len(res.get("lift_on_off_events_in_flight", []))
    (d / "summary.json").write_text(json.dumps(s, indent=1))
    print(f"{d.name:18s} fps {a.fps:g}: imaged>=2 {res['trees_imaged_2plus']}, {res['energy_wh']} Wh")
