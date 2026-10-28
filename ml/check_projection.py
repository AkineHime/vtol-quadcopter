#!/usr/bin/env python3
"""
check_projection.py -- validate detect_pipeline's crown projection against Blender.

    python ml/check_projection.py RUN_DIR s1_esp s3_esp

For each ESP32 shot rendered by blender_replay.py --shots, Blender saved the target
crown's box in the image (boxes.json, from the real camera incl. aircraft pitch/roll).
This compares it with detect_pipeline.project_crown (flat-attitude pinhole model used
for assigning detections to palms) and prints the IoU per shot.
"""
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect_pipeline as dp  # noqa: E402


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


run = Path(sys.argv[1])
tr = json.loads((run / "track.json").read_text())
shots = {s["name"]: s for s in json.loads((run / "shots.json").read_text())}
cr = tr["layout"]["crown_radius_m"]
for name in sys.argv[2:]:
    s = shots[name]
    tree = next(t for t in tr["trees"] if t["id"] == s["tree"])
    boxes = json.loads((run / "shots" / name / "boxes.json").read_text())
    fr = [f for f in tr["frames"] if s["t0"] <= f["t"] < s["t1"]]
    ious, centre_err = [], []
    for j, f in enumerate(fr):
        b = boxes.get(str(j))
        if b is None:
            continue
        p = dp.project_crown(float(tree["n"]) - f["n"], float(tree["e"]) - f["e"],
                             f["up"] - float(tree["height"]), math.radians(f["yaw"]), cr,
                             math.radians(f["pitch"]))
        if p is None:
            continue
        ious.append(iou(p, b))
        centre_err.append(math.hypot((p[0] + p[2] - b[0] - b[2]) / 2, (p[1] + p[3] - b[1] - b[3]) / 2))
    print(f"{name} {s['tree']}: {len(ious)} frames, IoU median {statistics.median(ious):.2f} "
          f"min {min(ious):.2f}; centre offset median {100 * statistics.median(centre_err):.1f}% of the image")
