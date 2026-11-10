#!/usr/bin/env python3
"""
extract_track.py -- flight log (.BIN) -> track.json for the Blender replay.

    python extract_track.py RUN_DIR [--fps 30]      # writes RUN_DIR/track.json

Samples, at the video frame rate: local position (n, e, up) relative to the
dock, attitude (roll, pitch, yaw), the 4 lift motors + pusher (0..1) and the
aileron/elevator servo positions (-1..1), plus the flight phase messages.
Values are linearly interpolated between log samples (the log runs slower than
30 fps; holding the last sample made the replay stutter) -- nothing else is
smoothed or invented. Also writes the planned path and the time each palm is
first imaged by the nose camera (analysis.in_frame, 5 fps) for the overlays.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from pathlib import Path

from pymavlink import mavutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analysis  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--fps", type=float, default=30.0)
    a = ap.parse_args()

    plan = json.loads((a.run / "plan.json").read_text())
    home = plan["home"]
    sx = 111_320.0 * math.cos(math.radians(home["lat"]))
    m = mavutil.mavlink_connection(str(a.run / "flight.BIN"))
    pos, att, rc, msgs, asp, modes = [], [], [], [], [], []
    while True:
        r = m.recv_match(type=["POS", "ATT", "RCOU", "MSG", "CTUN", "MODE"])
        if r is None:
            break
        t = r.TimeUS / 1e6
        k = r.get_type()
        if k == "POS":
            pos.append((t, (r.Lat - home["lat"]) * 111_320.0, (r.Lng - home["lon"]) * sx, r.RelHomeAlt))
        elif k == "ATT":
            att.append((t, r.Roll, r.Pitch, r.Yaw))
        elif k == "RCOU":
            thr = [max(0.0, min(1.0, (getattr(r, f"C{c}") - 1000) / 1000)) for c in (5, 6, 7, 8, 3)]
            srv = [max(-1.0, min(1.0, (getattr(r, f"C{c}") - 1500) / 500)) for c in (1, 2, 4)]
            rc.append((t, thr, srv))
        elif k == "MSG":
            msgs.append((t, r.Message))
        elif k == "CTUN":
            asp.append((t, float(getattr(r, "As", 0.0))))
        elif k == "MODE":
            modes.append((t, m.flightmode))

    def series_at(series):
        times = [r[0] for r in series]

        def at(t):
            i = bisect.bisect(times, t)
            if i <= 0 or i >= len(series):
                return series[min(max(i, 0), len(series) - 1)][1:]
            (ta, *va), (tb, *vb) = series[i - 1], series[i]
            w = (t - ta) / (tb - ta) if tb > ta else 0.0
            return [lerp(x, y, w) for x, y in zip(va, vb)]
        return at

    def lerp(x, y, w):
        if isinstance(x, list):
            return [lerp(a_, b_, w) for a_, b_ in zip(x, y)]
        return x + (y - x) * w

    # yaw: unwrap before interpolating so 359 -> 1 doesn't spin the long way round
    unwrapped, prev = [], None
    for t, roll, pitch, yaw in att:
        if prev is not None:
            yaw = prev + ((yaw - prev + 180) % 360 - 180)
        unwrapped.append((t, roll, pitch, yaw))
        prev = yaw
    pos_at, att_at, rc_at = series_at(pos), series_at(unwrapped), series_at(rc)
    asp_at = series_at(asp) if asp else (lambda t: [0.0])
    mode_t = [x[0] for x in modes]

    def mode_at(t):
        i = bisect.bisect(mode_t, t) - 1
        return modes[i][1] if i >= 0 else (modes[0][1] if modes else "")

    airborne = [p for p in pos if p[3] > 0.3]
    t0 = max(pos[0][0], airborne[0][0] - 3.0)       # 3 s on the pad before lift-off
    t1 = min(pos[-1][0], airborne[-1][0] + 4.0)     # 4 s after touchdown
    # cumulative energy, same model as analysis.py (lift momentum theory + pusher drag x speed + 6 W avionics)
    hov = sorted(sum(x[1][:4]) / 4 for x in rc if sum(x[1][:4]) / 4 > 0.3)
    hover_thr = hov[len(hov) // 2] if hov else 0.5
    t_air = (airborne[0][0] - 1.0, airborne[-1][0] + 1.0)
    e_t, e_cum, acc = [], [], 0.0
    for (ta, thr_a, _), (tb, _, _) in zip(rc, rc[1:]):
        dt = tb - ta
        if 0 < dt <= 1 and t_air[0] <= ta <= t_air[1]:
            acc += (analysis.lift_power_w(thr_a[:4], hover_thr) + analysis.pusher_power_w(thr_a[4], asp_at(ta)[0])
                    + 6.0) * dt / 3600
        e_t.append(tb)
        e_cum.append(acc)

    def wh_at(t):
        i = bisect.bisect(e_t, t) - 1
        return e_cum[i] if i >= 0 else 0.0

    cr = plan["layout"]["crown_radius_m"]
    tgt_ids = sorted({i["tree"] for i in plan["mission"] if i.get("tree")})
    tgt_trees = [tr for tr in plan["trees"] if tr["id"] in tgt_ids]
    frames = []
    t = t0
    while t <= t1:
        n, e, up = pos_at(t)
        roll, pitch, yaw = att_at(t)
        thr, srv = rc_at(t)
        frames.append({"t": round(t - t0, 3), "n": round(n, 3), "e": round(e, 3), "up": round(max(up, 0.0), 3),
                       "roll": round(roll, 2), "pitch": round(pitch, 2), "yaw": round(yaw % 360, 2),
                       "lift": [round(x, 3) for x in thr[:4]], "pusher": round(thr[4], 3),
                       "ail_l": round(srv[0], 3), "ail_r": round(srv[1], 3), "elev": round(srv[2], 3),
                       "as": round(asp_at(t)[0], 2), "mode": mode_at(t), "wh": round(wh_at(t), 3),
                       # targets wholly in the nose camera's frame right now (analysis.in_frame)
                       "tgt": [tr["id"] for tr in tgt_trees if analysis.in_frame(
                           float(tr["n"]) - n, float(tr["e"]) - e, up - float(tr["height"]), math.radians(yaw), cr)]})
        t += 1.0 / a.fps

    # first time each palm is wholly in the nose camera's frame (5 fps trigger, as analysis.py)
    imaged_t = {}
    cam_dt, tc = 0.2, airborne[0][0]
    while tc < airborne[-1][0]:
        n, e, up = pos_at(tc)
        yaw = math.radians(att_at(tc)[2])
        for tr in plan["trees"]:
            if tr["id"] not in imaged_t and analysis.in_frame(float(tr["n"]) - n, float(tr["e"]) - e,
                                                              up - float(tr["height"]), yaw, cr):
                imaged_t[tr["id"]] = round(tc - t0, 2)
        tc += cam_dt
    path = [(i["n"], i["e"]) for i in plan["mission"] if i["n"] is not None]
    out = {"run": a.run.name, "batt_wh": analysis.BATT_WH, "fps": a.fps, "home": home, "layout": plan["layout"],
           "trees": plan["trees"], "targets": sorted({i["tree"] for i in plan["mission"] if i.get("tree")}),
           "phases": [{"t": round(tt - t0, 2), "msg": s} for tt, s in msgs if t0 <= tt <= t1
                      and not s.startswith(("EKF", "GPS", "Field", "ArduPilot", "Param"))],
           "imaged_t": imaged_t, "path": path, "frames": frames}
    (a.run / "track.json").write_text(json.dumps(out))
    print(f"[track] {len(frames)} frames ({len(frames) / a.fps:.0f} s) -> {a.run / 'track.json'}")


if __name__ == "__main__":
    main()
