#!/usr/bin/env python3
"""
train_ripeness.py -- train the 3-class ripeness detector (Ultralytics YOLO26s).

    python ml/train_ripeness.py [--model yolo26s.pt] [--epochs 80] [--imgsz 640]

Run in WSL (CUDA). Reads dataset/ripeness3 (ml/prepare_ripeness.py), writes the run
to ml/runs/<name>/, copies the best weights to ml/models/ripeness_<model>.pt and
the held-out TEST-split metrics to ml/models/ripeness_<model>_test.json.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ultralytics import YOLO

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "dataset" / "ripeness3"
ML = REPO / "ml"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolo26s.pt")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    a = ap.parse_args()
    # data.yaml with this machine's absolute path (the dataset may have been built on Windows)
    yaml = DATA / "data_local.yaml"
    names = (DATA / "data.yaml").read_text().split("names:")[1].strip()
    yaml.write_text(f"path: {DATA.as_posix()}\ntrain: train/images\nval: valid/images\ntest: test/images\n"
                    f"nc: 3\nnames: {names}\n")
    tag = Path(a.model).stem
    model = YOLO(a.model)
    model.train(data=str(yaml), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, patience=25, seed=7,
                project=str(ML / "runs"), name=f"ripeness_{tag}", exist_ok=True, plots=True, workers=4)
    best = ML / "runs" / f"ripeness_{tag}" / "weights" / "best.pt"
    (ML / "models").mkdir(exist_ok=True)
    out = ML / "models" / f"ripeness_{tag}.pt"
    shutil.copy(best, out)
    m = YOLO(str(out)).val(data=str(yaml), split="test", imgsz=a.imgsz, project=str(ML / "runs"),
                           name=f"ripeness_{tag}_test", exist_ok=True, plots=True)
    names_l = m.names if isinstance(m.names, dict) else dict(enumerate(m.names))
    res = {"model": out.name, "split": "test", "mAP50": round(float(m.box.map50), 4),
           "mAP50_95": round(float(m.box.map), 4), "precision": round(float(m.box.mp), 4),
           "recall": round(float(m.box.mr), 4),
           "per_class_mAP50": {names_l[i]: round(float(v), 4) for i, v in enumerate(m.box.ap50)}}
    (ML / "models" / f"ripeness_{tag}_test.json").write_text(json.dumps(res, indent=1))
    print("[test]", json.dumps(res))


if __name__ == "__main__":
    main()
