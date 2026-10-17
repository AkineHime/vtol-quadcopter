#!/usr/bin/env python3
"""
make_plantation.py -- write the 1 ha plantation layout used by the planner,
the Gazebo world and the schedule simulation.

    python make_plantation.py            # -> trees.csv + layout.json

Layout: TNAU's recommended square system for tall coconut, 7.5 m x 7.5 m
(~175 palms/ha). A 100 m x 100 m field holds a 13 x 13 grid (169 palms).
The dock sits on the southern boundary track, 15 m south of the field edge,
its pad oriented so the aircraft faces south: the first fixed-wing leg (to
the line-up point south-west of the field) then needs no turn during the
forward transition.
Local frame: dock at (0, 0), north = +n, east = +e.

trees.csv carries a seeded ground truth that the simulated "detector" in
the schedule sees with some error:
  condition  healthy | ripe | frond | ripe+frond
  status     the planner's current belief: unscouted | target | cleared
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent

SPACING = 7.5
N = 13
FIELD = 100.0                      # m, square
FIELD_N0 = 15.0                    # field south edge, m north of the dock
FIELD_E0 = -FIELD / 2
FIRST = (FIELD - (N - 1) * SPACING) / 2   # 5 m inset from the boundary
SEED = 7


def main() -> None:
    rng = random.Random(SEED)
    rows = []
    for r in range(N):
        for c in range(N):
            u = rng.random()
            cond = ("ripe" if u < 0.10 else "frond" if u < 0.16 else
                    "ripe+frond" if u < 0.18 else "healthy")
            rows.append({
                "id": f"P{r:02d}{c:02d}", "row": r, "col": c,
                "n": round(FIELD_N0 + FIRST + r * SPACING, 2),
                "e": round(FIELD_E0 + FIRST + c * SPACING, 2),
                "height": round(rng.uniform(12.0, 16.0), 1),   # tall variety, mature
                "condition": cond, "status": "unscouted"})
    with (HERE / "trees.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    layout = {"spacing": SPACING, "grid": N, "field_m": FIELD,
              "field_n0": FIELD_N0, "field_e0": FIELD_E0,
              "dock": {"n": 0.0, "e": 0.0, "heading_deg": 180.0},
              "home": {"lat": 10.6609, "lon": 77.0048},       # Pollachi coconut belt
              "crown_radius_m": 4.0, "seed": SEED}
    (HERE / "layout.json").write_text(json.dumps(layout, indent=2))
    counts = {}
    for r in rows:
        counts[r["condition"]] = counts.get(r["condition"], 0) + 1
    print(f"{len(rows)} palms, ground truth {counts}")


if __name__ == "__main__":
    main()
