#!/usr/bin/env python3
"""
make_video.py -- encode Blender replay frames into a captioned MP4.

    python make_video.py RUN_DIR RENDER_SUBDIR [--out name.mp4]

Reads RUN_DIR/track.json and RUN_DIR/RENDER_SUBDIR/schedule.json (written by
blender_replay.py), labels each stretch with the flight phase (from the logged
motor outputs: lift rotors / pusher on, altitude) and the playback speed, and
adds a short title card. Runs ffmpeg (WSL: /usr/bin/ffmpeg).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def phase(f, t, t_end, speed, t_sweep_end=None):
    lift, push, up = max(f["lift"]) > 0.06, f["pusher"] > 0.06, f["up"]
    if up < 0.4:
        return "On the dock" if t < 30 else "Landed on the dock"
    if t > t_end - 25 and lift:
        return "VTOL landing on the dock"
    if lift and push:
        return "Transition (lift rotors + pusher)"
    if lift and t < 40:
        return "VTOL takeoff from the dock"
    if lift:
        return "VTOL confirm stops at flagged palms"
    if t_sweep_end is not None and t > t_sweep_end:
        return "Fixed-wing U-turn back toward the first confirm stop"
    return "Fixed-wing scout sweep - lift rotors stopped"


def segments(track, sched):
    fr, fps = track["frames"], sched["fps"]
    t_end = fr[-1]["t"]
    idx = {round(f["t"], 3): k for k, f in enumerate(fr)}
    cams = sched.get("cam", [])
    map_t = [t for t, c in zip(sched["t"], cams) if c == "map"]
    t_sweep_end = map_t[-1] if map_t else None     # the map shot ends as the last lane does
    segs = []
    for j, (t, sp) in enumerate(zip(sched["t"], sched["speed"])):
        f = fr[idx.get(round(t, 3), 0)]
        label = phase(f, t, t_end, sp, t_sweep_end) + (f"   ({sp}x speed)" if sp > 1 else "")
        if segs and segs[-1][2] == label:
            segs[-1][1] = j + 1
        else:
            segs.append([j, j + 1, label])
    # drop flickers shorter than 1.5 s by merging into the previous segment
    out = []
    for s in segs:
        if out and (s[1] - s[0]) < 1.5 * fps:
            out[-1][1] = s[1]
        else:
            out.append(s)
    return [(a / fps, b / fps, lab) for a, b, lab in out]


def esc(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("sub")
    ap.add_argument("--out")
    a = ap.parse_args()
    rd = a.run / a.sub
    track = json.loads((a.run / "track.json").read_text())
    sched = json.loads((rd / "schedule.json").read_text())
    fps = sched["fps"]
    ext = "jpg" if list(rd.glob("*.jpg")) else "png"
    segs = segments(track, sched)
    title = ("CoconutQuadplane - simulated plantation inspection",
             "ArduPilot QuadPlane firmware (SITL) + JSBSim physics  |  1 ha, 169 palms")
    vf = []
    box = "box=1:boxcolor=black@0.45:boxborderw=14"
    for t0, t1, lab in segs:
        vf.append(f"drawtext=fontfile={FONT}:text='{esc(lab)}':x=40:y=h-80:fontsize=34:fontcolor=white:{box}"
                  f":enable='between(t,{t0:.2f},{t1:.2f})'")
    vf.append(f"drawtext=fontfile={FONT_B}:text='{esc(title[0])}':x=(w-tw)/2:y=h*0.38:fontsize=56:fontcolor=white:{box}"
              f":enable='lt(t,4)'")
    vf.append(f"drawtext=fontfile={FONT}:text='{esc(title[1])}':x=(w-tw)/2:y=h*0.38+90:fontsize=30:fontcolor=white:{box}"
              f":enable='lt(t,4)'")
    # legend while the map camera shows the sweep overlays
    cams = sched.get("cam", [])
    k = 0
    while k < len(cams):
        if cams[k] != "map":
            k += 1
            continue
        j = k
        while j < len(cams) and cams[j] == "map":
            j += 1
        legend = "white line = planned racetrack     orange = flown path     blue disc = palm imaged by the nose camera"
        vf.append(f"drawtext=fontfile={FONT}:text='{esc(legend)}':x=40:y=40:fontsize=26:fontcolor=white:{box}"
                  f":enable='between(t,{k / fps:.2f},{j / fps:.2f})'")
        k = j
    out = rd / (a.out or f"{a.run.name}_{a.sub}.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(rd / f"%06d.{ext}"),
           "-vf", ",".join(vf), "-c:v", "libx264", "-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p",
           str(out)]
    subprocess.run(cmd, check=True)
    for t0, t1, lab in segs:
        print(f"  {t0:6.1f}-{t1:6.1f} s  {lab}")
    print(f"[video] {out}  ({sched['frames'] / fps:.0f} s)")


if __name__ == "__main__":
    main()
