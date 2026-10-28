#!/usr/bin/env python3
"""
assemble_video.py -- cut the final review video from already-rendered frames.

    python assemble_video.py RUN_DIR [--main render_A] [--shots shots] [--out NAME.mp4]

Reuses the main highlight frames (RUN/<main>/, from blender_replay.py) and splices in
the extra shots (RUN/<shots>/<name>/, rendered with blender_replay.py --shots
RUN/shots.json) in place of the main frames over the same flight time, so only the
new shots had to be rendered. Then, in one ffmpeg pass (WSL: ffmpeg with libass):
  - holds the first frame 4 s under the title card (the aircraft is still on the dock)
  - phase captions, a telemetry HUD read from the flight log (track.json), the map
    legend, ESP32 shot labels + the crown box from the camera geometry
  - holds the last frame 5 s under a summary card (numbers from summary.json)
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import make_video as mv

FPS = 30
TITLE_HOLD_S = 4.0
END_HOLD_S = 5.0
W, H = 1920, 1080


def ass_time(s):
    s = max(0.0, s)
    h, r = divmod(s, 3600)
    m, r = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{r:05.2f}"


def esc(t):
    return t.replace("{", "(").replace("}", ")")


def flight_state(f):
    lift, push = max(f["lift"]) > 0.06, f["pusher"] > 0.06
    if f["up"] < 0.4 and not lift:
        return "ON DOCK"
    if lift and push:
        return "TRANSITION"
    return "VTOL" if lift else "FIXED-WING"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--main", default="render_A")
    ap.add_argument("--shots", default="shots")
    ap.add_argument("--out")
    a = ap.parse_args()
    run = a.run
    tr = json.loads((run / "track.json").read_text())
    plan = json.loads((run / "plan.json").read_text())
    summ = json.loads((run / "summary.json").read_text())
    sched = json.loads((run / a.main / "schedule.json").read_text())
    shots = sorted(json.loads((run / "shots.json").read_text()), key=lambda s: s["t0"])
    frames = tr["frames"]
    by_t = {round(f["t"], 3): f for f in frames}
    trees = {t["id"]: t for t in plan["trees"]}
    stops = [i for i in plan["mission"] if i.get("tree")]
    stop_no = {s["tree"]: k + 1 for k, s in enumerate(stops)}
    stop_d = {s["tree"]: math.hypot(s["n"] - float(trees[s["tree"]]["n"]), s["e"] - float(trees[s["tree"]]["e"]))
              for s in stops}

    # ---- ESP32 shots: 800x600 renders -> 1920x1080 with sensor-ish noise/blur, pillarboxed
    for s in shots:
        if s["cam"] != "esp32":
            continue
        src, dst = run / a.shots / s["name"], run / a.shots / s["name"] / "post"
        dst.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src / "%06d.jpg"), "-vf",
                        "scale=1440:1080,gblur=sigma=0.8,noise=alls=10:allf=t,eq=saturation=0.85:contrast=1.05,"
                        "pad=1920:1080:240:0:black", "-q:v", "3", "-start_number", "0", str(dst / "%06d.jpg")], check=True)

    # ---- edit list: (file, track frame, speed, camera, shot or None)
    seq = []
    main_k = list(range(sched["frames"]))
    t_main = sched["t"]

    def add_main(t0, t1):
        for k in main_k:
            if t0 <= t_main[k] < t1:
                seq.append((run / a.main / f"{k:06d}.jpg", by_t[round(t_main[k], 3)], sched["speed"][k],
                            sched["cam"][k], None))
    t_prev = -1.0
    for s in shots:
        add_main(t_prev, s["t0"])
        d = run / a.shots / s["name"]
        boxes = json.loads((d / "boxes.json").read_text()) if (d / "boxes.json").exists() else {}
        idx = [f for f in frames if s["t0"] <= f["t"] < s["t1"]]
        for j, f in enumerate(idx):
            p = (d / "post" / f"{j:06d}.jpg") if s["cam"] == "esp32" else (d / f"{j:06d}.jpg")
            seq.append((p, f, 1, s["cam"], dict(s, box=boxes.get(str(j)))))
        t_prev = s["t1"]
    add_main(t_prev, 1e9)
    n_title, n_end = int(TITLE_HOLD_S * FPS), int(END_HOLD_S * FPS)
    seq = [seq[0][:4] + (None,)] * n_title + seq + [seq[-1][:4] + (None,)] * n_end
    for p, *_ in seq:
        if not Path(p).exists():
            raise SystemExit(f"missing frame {p}")

    # ---- ffconcat list (paths as ffmpeg in WSL sees them)
    lst = run / "assemble_frames.txt"
    with lst.open("w") as fh:
        fh.write("ffconcat version 1.0\n")
        for p, *_ in seq:
            fh.write(f"file '{Path(p).resolve().as_posix()}'\nduration {1 / FPS:.6f}\n")
        fh.write(f"file '{Path(seq[-1][0]).resolve().as_posix()}'\n")

    # ---- ASS overlay
    ev = []

    def add(t0, t1, style, text):
        ev.append(f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},{style},,0,0,0,,{text}")

    def runs(values, style, start=0):
        """merge consecutive equal texts into one event each."""
        k = start
        while k < len(values):
            j = k
            while j < len(values) and values[j] == values[k]:
                j += 1
            if values[k]:
                add(k / FPS, j / FPS, style, values[k])
            k = j

    t_end = frames[-1]["t"]
    map_t = [t for t, c in zip(t_main, sched["cam"]) if c == "map"]
    t_sweep_end = map_t[-1] if map_t else None
    n = len(seq)
    caps, huds, legends = [""] * n, [""] * n, [""] * n
    for i, (p, f, sp, cam, shot) in enumerate(seq):
        if i < n_title or i >= n - n_end:
            continue
        if shot is None:
            caps[i] = esc(mv.phase(f, f["t"], t_end, sp, t_sweep_end) + (f"   ({sp}x speed)" if sp > 1 else ""))
        elif shot["cam"] == "trans_side":
            caps[i] = "VTOL to fixed-wing transition: the pusher spins up, the lift rotors stop as the wing takes the load"
        elif shot["cam"] == "esp32":
            caps[i] = ("Simulated ESP32-CAM view (nose camera, 60 deg down)\\N"
                       "{\\fs24}green box = where the crown falls in the image, from camera geometry (not the ML detector)")
        else:
            tid = shot["tree"]
            caps[i] = (f"Confirm stop {stop_no[tid]}/{len(stops)}: {tid} ({trees[tid]['condition']})  -  hovering "
                       f"{stop_d[tid]:.1f} m short of the palm so the 60 deg camera centres its crown\\N"
                       "{\\fs24}wedge = nose-camera field of view; turns green when the whole crown is in frame")
        if cam == "map":
            legends[i] = ("white line = planned racetrack     orange = flown path     "
                          "blue disc = palm imaged     orange ring = palm flagged for a confirm stop")
        wh = f.get("wh", 0.0)
        huds[i] = (f"{{\\b1}}{flight_state(f)}{{\\b0}}\\N"
                   f"airspeed  {f.get('as', 0):5.1f} m/s\\N"
                   f"altitude  {f['up']:5.1f} m\\N"
                   f"lift {100 * sum(f['lift']) / 4:3.0f}%   pusher {100 * f['pusher']:3.0f}%\\N"
                   f"energy  {wh:4.1f} Wh  ({100 * wh / tr.get('batt_wh', 44.4):2.0f}% batt)\\N"
                   f"T+{f['t']:5.1f} s")
    runs(caps, "Caption")
    runs(huds, "HUD")
    runs(legends, "Legend")
    for i, (p, f, sp, cam, shot) in enumerate(seq):     # crown box on the ESP32 frames
        if shot and shot["cam"] == "esp32" and shot.get("box"):
            x0, y0, x1, y1 = shot["box"]
            X0, Y0, X1, Y1 = (240 + x0 * 1440, y0 * 1080, 240 + x1 * 1440, y1 * 1080)
            add(i / FPS, (i + 1) / FPS, "Box",
                f"{{\\an7\\pos(0,0)\\p1}}m {X0:.0f} {Y0:.0f} l {X1:.0f} {Y0:.0f} l {X1:.0f} {Y1:.0f} l {X0:.0f} {Y1:.0f}{{\\p0}}")
    add(0.3, TITLE_HOLD_S + 1.0, "Title",
        "{\\fad(500,700)}CoconutQuadplane\\N{\\fs40}simulated plantation inspection\\N"
        "{\\fs30}ArduPilot QuadPlane firmware (SITL)  +  JSBSim flight physics   |   1 ha, 169 palms")
    t_fin = n / FPS
    add(t_fin - END_HOLD_S + 0.3, t_fin, "Summary",
        "{\\fad(600,0)}{\\b1}Mission summary{\\b0}\\N"
        f"flight {summ['flight_s']:.0f} s   |   {summ['distance_m'] / 1000:.2f} km   |   "
        f"{summ['energy_wh']:.1f} Wh ({summ['battery_used_pct']:.0f}% of the battery)\\N"
        f"palms imaged in >= 2 frames: {summ['trees_imaged_2plus']}/{len(plan['trees'])}   |   "
        f"ripe targets confirmed: {summ['targets_imaged_2plus']}/{summ['n_targets']}\\N"
        f"min crown clearance {summ['min_crown_clearance_m']:.1f} m   |   landed on the dock")
    ass = run / "assemble_overlay.ass"
    ass.write_text("\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        "Style: Caption,DejaVu Sans,32,&H00FFFFFF,&H00FFFFFF,&H90000000,&H90000000,0,0,0,0,100,100,0,0,3,10,0,1,40,40,40,1",
        "Style: HUD,DejaVu Sans Mono,25,&H00FFFFFF,&H00FFFFFF,&HA0000000,&HA0000000,0,0,0,0,100,100,0,0,3,10,0,9,40,40,40,1",
        "Style: Legend,DejaVu Sans,24,&H00FFFFFF,&H00FFFFFF,&H90000000,&H90000000,0,0,0,0,100,100,0,0,3,8,0,7,40,40,40,1",
        "Style: Box,DejaVu Sans,20,&HFF000000,&HFF000000,&H0033FF66,&HFF000000,0,0,0,0,100,100,0,0,1,4,0,7,0,0,0,1",
        "Style: Title,DejaVu Sans,64,&H00FFFFFF,&H00FFFFFF,&H90000000,&H90000000,1,0,0,0,100,100,0,0,3,18,0,5,40,40,40,1",
        "Style: Summary,DejaVu Sans,36,&H00FFFFFF,&H00FFFFFF,&H90000000,&H90000000,0,0,0,0,100,100,0,0,3,20,0,5,40,40,40,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *ev, ""]),
        encoding="utf-8")
    out = run / (a.out or f"{run.name}_review.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", f"fps={FPS},ass={ass.as_posix()}", "-c:v", "libx264", "-crf", "23", "-preset", "medium",
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    print(f"[video] {out}  ({n / FPS:.0f} s, {n} frames: {sum(1 for s in seq if s[4]) } from inserted shots)")


if __name__ == "__main__":
    main()
