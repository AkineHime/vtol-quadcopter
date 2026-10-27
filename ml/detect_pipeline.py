#!/usr/bin/env python3
"""
detect_pipeline.py -- nose-camera frames + flight log -> per-palm ripeness observations.

    python ml/detect_pipeline.py RUN_DIR --frames manifest.csv     # real flight: CSV path,t
    python ml/detect_pipeline.py RUN_DIR --sim-shots s1_esp,s3_esp # Blender ESP32 renders of that run

Run in WSL (ultralytics, opencv). For every frame (t on the flight-log clock,
seconds since the track start):
  1. the aircraft pose at t comes from RUN/track.json (render/extract_track.py);
  2. the palms wholly in view are found with the camera model of
     flight_software/analysis.py (nose camera 60 x 46 deg, 60 deg down) and each
     crown is projected to a box in the image;
  3. the detector (3 maturity classes) runs on the frame; each detection goes to
     the palm whose projected crown box holds at least half of it;
  4. per palm: TARGET when >= MIN_FRAMES frames see the harvest class
     (pre-mature = tender coconut, decided 2026-10-27) at >= --conf.
Writes RUN/detections/: observations.json (rows in the dashboard `observations`
format), trees.csv (per-palm summary) and annotated frames.

With --post https://localhost:8443 the results also go to the ground-station
dashboard (ground_station/): per palm seen with detections, its best frame
(POST /api/trees/{id}/image) and one `detection` event with model, label and
confidence; palms passing the target rule also get status `target`, which puts
them on the dashboard's next-mission plan.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import math
import ssl
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "flight_software"))
import analysis  # noqa: E402  (camera model: HFOV, VFOV, CAM_DOWN, in_frame)

HARVEST_CLASS = "pre-mature"
MIN_FRAMES = 2              # sim study: 2 agreeing photos per palm
MIN_INSIDE = 0.5            # share of a detection's box that must lie inside the palm's crown box


def inside_frac(d, c):
    """Fraction of box d (u0, v0, u1, v1) that lies inside box c."""
    ix = max(0.0, min(d[2], c[2]) - max(d[0], c[0]))
    iy = max(0.0, min(d[3], c[3]) - max(d[1], c[1]))
    return ix * iy / max(1e-9, (d[2] - d[0]) * (d[3] - d[1]))


def project_crown(dn, de, ddown, yaw, cr, pitch=0.0):
    """Image box (u0, v0, u1, v1; 0..1, v down) of a crown centred (dn, de) north/east
    and ddown below the camera -- pinhole model matching analysis.in_frame, with the
    aircraft's pitch (rad, nose up +) taken off the camera's 60 deg depression."""
    down = analysis.CAM_DOWN - pitch
    pts = []
    for k in range(12):
        q = k * math.pi / 6
        for dz in (-1.2, 0.4):                 # fronds hang ~1 m below the crown top
            n, e, d = dn + cr * math.cos(q), de + cr * math.sin(q), ddown - dz
            along = n * math.cos(yaw) + e * math.sin(yaw)
            cross = -n * math.sin(yaw) + e * math.cos(yaw)
            zc = along * math.cos(down) + d * math.sin(down)
            yc = -along * math.sin(down) + d * math.cos(down)
            if zc <= 0.5:
                return None
            pts.append((0.5 + cross / zc / (2 * math.tan(analysis.HFOV / 2)),
                        0.5 + yc / zc / (2 * math.tan(analysis.VFOV / 2))))
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def palms_in_view(tr, f):
    yaw = math.radians(f["yaw"])
    cr = tr["layout"]["crown_radius_m"]
    view = {}
    for tree in tr["trees"]:
        dn, de, dd = float(tree["n"]) - f["n"], float(tree["e"]) - f["e"], f["up"] - float(tree["height"])
        if analysis.in_frame(dn, de, dd, yaw, cr):
            box = project_crown(dn, de, dd, yaw, cr, math.radians(f["pitch"]))
            if box:
                view[tree["id"]] = box
    return view


def load_items(a, tr):
    items = []                                  # (image path, t)
    if a.frames:
        for r in csv.DictReader(a.frames.open()):
            items.append((Path(r["path"]), float(r["t"])))
    if a.sim_shots:
        shots = {s["name"]: s for s in json.loads((a.run / "shots.json").read_text())}
        for name in a.sim_shots.split(","):
            s = shots[name]
            ts = [f["t"] for f in tr["frames"] if s["t0"] <= f["t"] < s["t1"]]
            items += [(a.run / "shots" / name / f"{j:06d}.jpg", t) for j, t in enumerate(ts)]
    return items


def post(base: str, path: str, data: bytes, ctype: str, insecure: bool) -> dict:
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers={"Content-Type": ctype}, method="POST")
    ctx = ssl._create_unverified_context() if insecure else None      # the dashboard's self-signed local cert
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        return json.loads(r.read())


def post_results(base: str, rows: list[dict], best: dict, model: str, insecure: bool) -> int:
    """One detection event per palm with detections (+ its best frame), and status
    'target' for palms passing the rule. Returns the number of palms posted."""
    n = 0
    for r in rows:
        b = best.get(r["tree_id"])
        if not b:
            continue
        img = post(base, f"/api/trees/{r['tree_id']}/image", Path(b["frame"]).read_bytes(), "image/jpeg", insecure)["image"]
        ev = {"kind": "detection", "label": b["label"], "confidence": round(b["conf"], 3), "model": model,
              "image": img, "source": "ml", "note": f"{r['frames_harvest']} of {r['frames_in_view']} frames tender"}
        post(base, f"/api/trees/{r['tree_id']}/events", json.dumps(ev).encode(), "application/json", insecure)
        if r["status"] == "target":
            post(base, f"/api/trees/{r['tree_id']}/events",
                 json.dumps({"kind": "status", "status": "target", "source": "ml"}).encode(), "application/json", insecure)
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--frames", type=Path, help="CSV with columns path,t")
    ap.add_argument("--sim-shots", help="comma-separated ESP32 shot names in RUN/shots")
    ap.add_argument("--model", type=Path, default=REPO / "ml" / "models" / "ripeness_yolo26s.pt")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--source", default="confirm", choices=["scout", "confirm"])
    ap.add_argument("--start-utc", help="ISO-8601 time of track t=0 (default: now)")
    ap.add_argument("--post", help="ground-station URL, e.g. https://localhost:8443: send results to the dashboard")
    ap.add_argument("--insecure", action="store_true", help="accept the dashboard's self-signed certificate")
    a = ap.parse_args()
    import cv2
    from ultralytics import YOLO

    tr = json.loads((a.run / "track.json").read_text())
    times = [f["t"] for f in tr["frames"]]
    t0 = dt.datetime.fromisoformat(a.start_utc) if a.start_utc else dt.datetime.now(dt.timezone.utc)
    items = load_items(a, tr)
    if not items:
        raise SystemExit("no frames: give --frames or --sim-shots")
    model = YOLO(str(a.model))
    out = a.run / "detections"
    (out / "frames").mkdir(parents=True, exist_ok=True)
    obs, per_tree, best = [], {}, {}            # best: tree -> its highest-confidence detection + frame
    for k, (path, t) in enumerate(items):
        f = tr["frames"][min(max(bisect.bisect(times, t) - 1, 0), len(times) - 1)]
        img = cv2.imread(str(path))
        h, w = img.shape[:2]
        view = palms_in_view(tr, f)
        res = model.predict(img, conf=a.conf, verbose=False)[0]
        dets = []
        for b, c, s in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
            # a detection belongs to the palm whose projected crown holds >= MIN_INSIDE of its box
            # (centre-only matching let a whole-frame false positive "hit" the middle palm)
            nb = (b[0] / w, b[1] / h, b[2] / w, b[3] / h)
            inside = {q: inside_frac(nb, box) for q, box in view.items()}
            tid = max(inside, key=inside.get) if inside and max(inside.values()) >= MIN_INSIDE else None
            dets.append((b, model.names[int(c)], float(s), tid))
        for tid in view:
            pt = per_tree.setdefault(tid, {"frames_in_view": 0, "frames_harvest": 0, "best": {}})
            pt["frames_in_view"] += 1
            mine = [d for d in dets if d[3] == tid]
            pt["frames_harvest"] += any(d[1] == HARVEST_CLASS for d in mine)
            for _, lab, s, _ in mine:
                pt["best"][lab] = max(pt["best"].get(lab, 0.0), s)
        for tid, (u0, v0, u1, v1) in view.items():         # projected crowns: yellow
            cv2.rectangle(img, (int(u0 * w), int(v0 * h)), (int(u1 * w), int(v1 * h)), (0, 220, 255), 1)
            cv2.putText(img, tid, (int(u0 * w) + 3, int(v0 * h) + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1)
        for b, lab, s, tid in dets:                         # detections: green = harvest class
            col = (60, 255, 60) if lab == HARVEST_CLASS else (255, 160, 60)
            cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), col, 2)
            cv2.putText(img, f"{lab} {s:.2f}", (int(b[0]), int(b[1]) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
        ann = out / "frames" / f"{k:05d}.jpg"
        cv2.imwrite(str(ann), img)
        for _, lab, s, tid in dets:
            rank = (lab == HARVEST_CLASS, s)
            if tid and rank > best.get(tid, {}).get("rank", (False, -1.0)):
                best[tid] = {"rank": rank, "label": lab, "conf": s, "frame": str(ann)}
        when = (t0 + dt.timedelta(seconds=t)).isoformat()
        obs += [{"tree_id": tid, "captured_at": when, "source": a.source, "model": a.model.stem.replace("_", "-"),
                 "label": lab, "confidence": round(s, 3), "image_path": ann.relative_to(a.run).as_posix()}
                for _, lab, s, tid in dets if tid]
    rows = [{"tree_id": tid, "frames_in_view": pt["frames_in_view"], "frames_harvest": pt["frames_harvest"],
             "best_harvest_conf": round(pt["best"].get(HARVEST_CLASS, 0.0), 3),
             "labels_seen": ";".join(f"{k}:{v:.2f}" for k, v in sorted(pt["best"].items())),
             "status": "target" if pt["frames_harvest"] >= MIN_FRAMES else "seen"}
            for tid, pt in sorted(per_tree.items())]
    (out / "observations.json").write_text(json.dumps(obs, indent=1))
    with (out / "trees.csv").open("w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["tree_id", "frames_in_view", "frames_harvest", "best_harvest_conf",
                                            "labels_seen", "status"])
        wr.writeheader()
        wr.writerows(rows)
    print(f"[pipeline] {len(items)} frames, {len(obs)} detections on palms, "
          f"{sum(r['status'] == 'target' for r in rows)} targets / {len(rows)} palms in view -> {out}")
    if a.post:
        n = post_results(a.post, rows, best, a.model.stem.replace("_", "-"), a.insecure)
        print(f"[pipeline] posted {n} palms to {a.post}")


if __name__ == "__main__":
    main()
