# Ripeness detection

A baseline coconut-maturity detector (Ultralytics YOLO26s) and the pipeline that
turns nose-camera frames plus the flight log into per-palm observations for the
dashboard (`documents/dashboard/DASHBOARD_SPEC.md`, table `observations`).

Run everything in WSL (`source ~/venv-ardupilot/bin/activate`; CUDA via the RTX 3050).

| Script | What it does |
|---|---|
| `prepare_ripeness.py` | Roboflow export (`dataset/Coconut*.zip`) → `dataset/ripeness3/`: 3 classes, split by source video |
| `train_ripeness.py` | Trains YOLO26s. Writes `models/ripeness_yolo26s.pt` and its **held-out test** metrics `models/ripeness_yolo26s_test.json` |
| `detect_pipeline.py` | Frames + `track.json` → `RUN/detections/` (`observations.json`, `trees.csv`, annotated frames). With `--post`, each palm's best frame and a `detection` event go to the ground-station dashboard, and palms passing the rule become `target` (so they join the next mission) |
| `check_projection.py` | Checks the pipeline's crown projection against the boxes Blender saved for the ESP32 shots |

```bash
python ml/prepare_ripeness.py
python ml/train_ripeness.py
python ml/detect_pipeline.py flight_software/demo/runs/js_demo_v4 --sim-shots s1_esp,s3_esp
python ml/detect_pipeline.py RUN --frames manifest.csv      # real flight: CSV with path,t (log clock)
python ml/detect_pipeline.py RUN --frames manifest.csv --post https://<laptop>:8443 --insecure   # -> dashboard
```

## Decisions (2026-10-27)

- **Classes:** the export's 6 classes become 3. The 2 `objects` boxes are dropped.
  - `pre-mature` ← pre-mature + unripe
  - `mature` ← mature + ripe
  - `over-mature`
- **Harvest target = `pre-mature`** (tender coconut). A palm becomes a target when
  **≥ 2 frames** see that class at confidence ≥ 0.35. The 2-frame rule comes from
  the sim study.
- **Split by source video.** Frames of one clip (`test5_*`, `trian1_12_*`, ...) all
  go to the same split, 70/15/15. Roboflow's random split puts near-duplicate
  frames in both train and test, which inflates the scores.

## Results (YOLO26s, 640 px, 74 epochs with early stopping, 18 min on the RTX 3050)

Held-out **test** split (whole source videos never seen in training), from
`models/ripeness_yolo26s_test.json`:

| | mAP50 | mAP50-95 | precision | recall |
|---|---|---|---|---|
| all classes | 0.55 | 0.40 | 0.59 | 0.52 |
| **pre-mature (harvest target)** | **0.72** | | | |
| mature | 0.66 | | | |
| over-mature | 0.29 | | | |

- Validation mAP50 was 0.72, against 0.55 on test. The by-source split removes
  the optimism a random split would give.
- `over-mature` is weak: only 241 boxes in train.

**Pipeline checks on the review run (`js_demo_v4`):**
- **Sim ESP32 frames** (`--sim-shots s1_esp,s3_esp`, 315 frames): 0 detections on
  palms, 0 targets. Correct: from the drone's angle the sim nuts are hidden under
  the crown.
  - The one false positive, a whole-frame `pre-mature` box, is rejected by the
    containment rule.
- **Positive test:** a real tender-bunch test image pasted into P0612's crown in
  10 frames. Detected as `pre-mature` at up to 0.84 in all 9 frames where P0612
  is in view, assigned to **P0612** only, and flagged `target`.

## How a detection becomes a palm

For each frame:
1. Look up the aircraft pose at the frame time in `track.json`.
2. Find the palms wholly in view with `flight_software/analysis.py`'s camera model
   (60 × 46°, 60° down), adding the aircraft pitch.
3. Project each palm's crown to an image box.
4. A detection belongs to the palm whose box holds at least half of it. Centre-only
   matching let a whole-frame false positive on the sim frames "hit" the middle palm.

`check_projection.py` checked this against Blender's rendered camera on the
review run: IoU 0.87–0.88, crown centre within ~3% of the image. That's ample at
7.5 m palm spacing.

## Caveat: this is a baseline, not the flight model

The dataset is **ground-level close-ups**: 416 px images of bunches filling the
frame, hand-held nuts, a few stock photos. From a confirm stop, the ESP32-CAM is
13–15 m from the crown, so a nut is about 13 px at 800×600, or about 26 px at
1600×1200. The test score below measures close-up performance only. **Expect far
lower recall from the aircraft** until we train on real oblique crown photos
taken from ~25 m.
- Capture the confirm-stop frames at the OV2640's full 1600×1200; the aircraft is
  stationary then.
- Label them in the same 3 classes.
- Re-run `train_ripeness.py`.
