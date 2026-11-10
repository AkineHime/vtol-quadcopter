#!/usr/bin/env python3
"""
prepare_ripeness.py -- Roboflow export -> 3-class YOLO dataset with a leakage-safe split.

    python ml/prepare_ripeness.py [--zip dataset/Coconut*.zip] [--out dataset/ripeness3]

Class map (decided 2026-10-27): the export's 6 classes become 3 maturity classes
    pre-mature  <- 'pre-mature coconut', 'unripe'
    mature      <- 'mature coconut', 'ripe'
    over-mature <- 'over-mature coconut'
    (the 2 'objects' boxes are dropped)
Harvest target for the crew = pre-mature (tender coconut).

Split: many images are frames of the same video (test5_16_png, test5_17_png, ...).
Roboflow's random split puts near-duplicate frames on both sides, which inflates
test scores, so all frames of one source go to the same split (70/15/15 by image,
deterministic). The original split is ignored.
"""
from __future__ import annotations

import argparse
import collections
import random
import re
import shutil
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NAMES = ["pre-mature", "mature", "over-mature"]
SRC_NAMES = ['mature coconut', 'objects', 'over-mature coconut', 'pre-mature coconut', 'ripe', 'unripe']
REMAP = {"pre-mature coconut": 0, "unripe": 0, "mature coconut": 1, "ripe": 1, "over-mature coconut": 2}
SPLIT = (("train", 0.70), ("valid", 0.15), ("test", 0.15))


def source_of(stem):
    """'test5_16_png' -> 'test5' (video frames); otherwise the image itself."""
    m = re.match(r"^(.*?)_\d+_png$", stem)
    return m.group(1) if m else stem


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path, default=next((REPO / "dataset").glob("Coconut*.zip"), None))
    ap.add_argument("--out", type=Path, default=REPO / "dataset" / "ripeness3")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    z = zipfile.ZipFile(a.zip)
    imgs = sorted(x for x in z.namelist() if "/images/" in x)
    groups = collections.defaultdict(list)
    for x in imgs:
        groups[source_of(Path(x).name.split(".rf.")[0])].append(x)
    keys = sorted(groups)
    random.Random(a.seed).shuffle(keys)
    keys.sort(key=lambda k: -len(groups[k]))      # place the big video groups first
    total = len(imgs)
    want = {s: f * total for s, f in SPLIT}
    have = {s: 0 for s, _ in SPLIT}
    assign = {}
    for k in keys:                                  # greedy: the split furthest below its target
        s = max(want, key=lambda s: (want[s] - have[s]) / want[s])
        assign[k] = s
        have[s] += len(groups[k])
    if a.out.exists():
        shutil.rmtree(a.out)
    counts = {s: collections.Counter() for s in want}
    for k, files in groups.items():
        s = assign[k]
        for x in files:
            lab = x.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
            lines = []
            if lab in z.namelist():
                for ln in z.read(lab).decode().splitlines():
                    p = ln.split()
                    if not p:
                        continue
                    src = SRC_NAMES[int(p[0])]
                    if src in REMAP:
                        lines.append(" ".join([str(REMAP[src])] + p[1:]))
                        counts[s][NAMES[REMAP[src]]] += 1
            name = Path(x).name
            (a.out / s / "images").mkdir(parents=True, exist_ok=True)
            (a.out / s / "labels").mkdir(parents=True, exist_ok=True)
            (a.out / s / "images" / name).write_bytes(z.read(x))
            (a.out / s / "labels" / (name.rsplit(".", 1)[0] + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
    (a.out / "data.yaml").write_text(
        f"path: {a.out.resolve().as_posix()}\ntrain: train/images\nval: valid/images\ntest: test/images\n"
        f"nc: {len(NAMES)}\nnames: {NAMES}\n")
    for s in want:
        print(f"[data] {s:5s}: {have[s]:4d} images  {dict(counts[s])}")
    print(f"[data] {len(groups)} sources; largest groups: "
          + ", ".join(f"{k}={len(groups[k])}->{assign[k]}" for k in sorted(groups, key=lambda k: -len(groups[k]))[:4]))


if __name__ == "__main__":
    main()
