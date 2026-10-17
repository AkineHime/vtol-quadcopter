#!/usr/bin/env python3
"""
analysis.py -- turn an ArduPilot dataflash log (.BIN) from a plantation flight
into deployment metrics.

    python analysis.py LOG.BIN [--fps 3] [--json out.json]

Metrics
  * imaging: the nose ESP32-CAM (OV2640, ~60 x 46 deg FOV) fixed 60 deg
    below the horizon looking forward, triggered at --fps; a palm counts as
    imaged in a frame when its whole crown (radius from layout.json) is in
    the FOV within CAM_RANGE. Reports frames per palm (we want a few good
    frames per tree, not dozens).
  * clearance: closest approach of the airframe (0.75 m radius) to any crown
    sphere (crown at the palm's height, radius crown_radius_m).
  * energy: momentum-theory hover power for the lift rotors (thrust from
    throttle^2 scaled so hover throttle carries the weight), pusher power
    from drag x speed, divided by efficiencies; integrated over the flight
    and compared with a 3S 4000 mAh pack (44.4 Wh, 80 % usable).
  * transitions/turbulence: for every in-flight lift-motor start or stop
    (any lift output crossing 1060 us while airspeed > 6 m/s) the peak
    attitude error and rate in the following 3 s.
All model constants are at the top so the assumptions are explicit.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
from pathlib import Path

from pymavlink import mavutil

HERE = Path(__file__).resolve().parent
DEMO = HERE / "demo"

# ---- assumptions -----------------------------------------------------------
MASS_KG = 1.84              # printed build, LW-PLA skins (airframe/out/mass_properties.json)
G = 9.81
RHO = 1.13                  # 35 C at ~300 m
ROTOR_A = math.pi * 0.127 ** 2
FM_ETA = 0.45               # figure of merit 0.6 x motor/ESC 0.75
PUSHER_ETA = 0.50
CD0_AREA = 0.0196 * 0.30    # C_D0 * S (aero/RESULTS.md), m^2
BATT_WH = 44.4
USABLE = 0.80
HFOV, VFOV = math.radians(60), math.radians(46)
CAM_DOWN = math.radians(60)   # optical axis 60 deg below the horizon, looking forward
CAM_RANGE = 30.0              # beyond this the crown is < ~2.2 cm/px: not useful
AIRFRAME_R = 0.75


def in_frame(dn, de, ddown, yaw, cr):
    """Is a crown (centre offset dn/de north/east, ddown below the camera,
    radius cr) wholly inside the fixed forward-down camera's FOV?"""
    along = dn * math.cos(yaw) + de * math.sin(yaw)
    cross = -dn * math.sin(yaw) + de * math.cos(yaw)
    zc = along * math.cos(CAM_DOWN) + ddown * math.sin(CAM_DOWN)
    yc = -along * math.sin(CAM_DOWN) + ddown * math.cos(CAM_DOWN)
    dist = math.sqrt(along ** 2 + cross ** 2 + ddown ** 2)
    if zc <= 1.0 or dist > CAM_RANGE:
        return False
    marg = math.atan2(cr, dist)
    return (abs(math.atan2(cross, zc)) + marg <= HFOV / 2
            and abs(math.atan2(yc, zc)) + marg <= VFOV / 2)


def lift_power_w(throttles, hover_thr):
    """Each lift rotor: T = (t/t_h)^2 * W/4 ; P = T^1.5/sqrt(2 rho A)/eta."""
    w4 = MASS_KG * G / 4
    p = 0.0
    for t in throttles:
        if t <= 0.02:
            continue
        thrust = (t / max(hover_thr, 0.2)) ** 2 * w4
        p += thrust ** 1.5 / math.sqrt(2 * RHO * ROTOR_A) / FM_ETA
    return p


def pusher_power_w(thr, airspeed):
    if thr <= 0.02:
        return 0.0
    drag = 0.5 * RHO * airspeed ** 2 * CD0_AREA * 1.6 + (MASS_KG * G) ** 2 / (
        0.5 * RHO * max(airspeed, 6) ** 2 * math.pi * 0.79 * 5.63 * 0.30)
    return max(drag * airspeed / PUSHER_ETA, 25.0 * thr)


def load_log(path):
    m = mavutil.mavlink_connection(str(path))
    d = {k: [] for k in ("ATT", "RCOU", "POS", "CTUN", "MSG", "RATE")}
    while True:
        x = m.recv_match(type=list(d))
        if x is None:
            break
        d[x.get_type()].append(x)
    return d


def nearest(series, t):
    ts = [s.TimeUS for s in series]
    i = min(bisect.bisect(ts, t), len(series) - 1)
    return series[i]


def _alt_span(pos, t, win):
    alts = [p[3] for p in pos if t <= p[0] <= t + win]
    return (max(alts) - min(alts)) if alts else 0.0


def analyse(path, fps=3.0):
    d = load_log(path)
    layout = json.loads((DEMO / "layout.json").read_text())
    trees = list(csv.DictReader((DEMO / "trees.csv").open()))
    home = layout["home"]
    sx = 111_320.0 * math.cos(math.radians(home["lat"]))
    cr = layout["crown_radius_m"]

    pos = [(p.TimeUS / 1e6, (p.Lat - home["lat"]) * 111_320.0, (p.Lng - home["lon"]) * sx, p.RelHomeAlt)
           for p in d["POS"]]
    if not pos:
        return {"error": "no POS"}
    t0, t1 = pos[0][0], pos[-1][0]
    airborne = [p for p in pos if p[3] > 1.0]
    flight_s = (airborne[-1][0] - airborne[0][0]) if airborne else 0.0
    dist = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(airborne, airborne[1:]))

    # hover throttle estimate: median lift output while slow and level
    rc = d["RCOU"]
    lift = [[(getattr(r, f"C{c}") - 1000) / 1000 for c in (5, 6, 7, 8)] for r in rc]
    hov = sorted(sum(l) / 4 for l in lift if sum(l) / 4 > 0.3)
    hover_thr = hov[len(hov) // 2] if hov else 0.5

    # energy
    ctun = d["CTUN"]
    e_wh, e_lift, e_push = 0.0, 0.0, 0.0
    for a, b, l in zip(rc, rc[1:], lift):
        dt = (b.TimeUS - a.TimeUS) / 1e6
        if dt <= 0 or dt > 1:
            continue
        asp = getattr(nearest(ctun, a.TimeUS), "As", 0.0) if ctun else 0.0
        pl = lift_power_w(l, hover_thr)
        pp = pusher_power_w((a.C3 - 1000) / 1000, asp)
        e_lift += pl * dt / 3600
        e_push += pp * dt / 3600
    e_wh = e_lift + e_push + 6.0 * flight_s / 3600          # + avionics/camera ~6 W

    # imaging: frames at fps along the flight
    att = d["ATT"]
    frames, k = [], 0
    t = airborne[0][0] if airborne else t0
    end = airborne[-1][0] if airborne else t1
    ptimes = [p[0] for p in pos]
    while t < end:
        i = min(bisect.bisect(ptimes, t), len(pos) - 1)
        _, n, e, alt = pos[i]
        yaw = math.radians(nearest(att, t * 1e6).Yaw)
        frames.append((n, e, alt, yaw))
        t += 1.0 / fps
    per_tree = {}
    min_clear = (1e9, None)
    for tr in trees:
        tn, te, th = float(tr["n"]), float(tr["e"]), float(tr["height"])
        cnt = 0
        for n, e, alt, yaw in frames:
            if in_frame(tn - n, te - e, alt - th, yaw, cr):
                cnt += 1
        per_tree[tr["id"]] = cnt
        for _, n, e, alt in pos[::5]:
            c = math.sqrt((n - tn) ** 2 + (e - te) ** 2 + (alt - th) ** 2) - cr - AIRFRAME_R
            if c < min_clear[0]:
                min_clear = (c, tr["id"])

    # in-flight lift-motor start/stop events
    events = []
    on_prev = None
    for r, l in zip(rc, lift):
        on = max(l) > 0.06
        if on_prev is not None and on != on_prev:
            asp = getattr(nearest(ctun, r.TimeUS), "As", 0.0) if ctun else 0.0
            if asp > 6.0:
                win = [a for a in att if r.TimeUS <= a.TimeUS <= r.TimeUS + 3e6]
                if win:
                    events.append({
                        "t": round(r.TimeUS / 1e6, 1), "type": "lift_start" if on else "lift_stop",
                        "airspeed": round(asp, 1),
                        "max_roll_err": round(max(abs(a.DesRoll - a.Roll) for a in win), 1),
                        "max_pitch_err": round(max(abs(a.DesPitch - a.Pitch) for a in win), 1),
                        "max_pitch_dev": round(max(abs(a.Pitch) for a in win), 1),
                        # a large commanded change means a turn coincided with the event
                        "des_roll_span": round(max(a.DesRoll for a in win) - min(a.DesRoll for a in win), 1),
                        "alt_change_m": round(_alt_span(pos, r.TimeUS / 1e6, 3.0), 1)})
        on_prev = on

    # baseline: how well roll tracks in ordinary fixed-wing flight (lift off,
    # > 10 m/s, away from any event) -- the event roll error minus this is
    # what the motor start/stop itself adds
    ev_t = [e["t"] for e in events]
    lift_off_t = [r.TimeUS for r, l in zip(rc, lift) if max(l) <= 0.06]
    errs = []
    if lift_off_t and ctun:
        lo, hi = lift_off_t[0], lift_off_t[-1]
        for a in att[::5]:
            if lo <= a.TimeUS <= hi and all(abs(a.TimeUS / 1e6 - t) > 6 for t in ev_t) \
                    and getattr(nearest(ctun, a.TimeUS), "As", 0.0) > 10:
                errs.append(abs(a.DesRoll - a.Roll))
    errs.sort()
    base_p95 = errs[int(0.95 * (len(errs) - 1))] if errs else None
    for e in events:
        e["roll_err_excess_over_cruise_p95"] = round(e["max_roll_err"] - base_p95, 1) if base_p95 is not None else None

    vals = list(per_tree.values())
    plan_p = Path(path).parent / "plan.json"
    plan_p = plan_p if plan_p.exists() else DEMO / "plan.json"
    tgt = sorted({it["tree"] for it in json.loads(plan_p.read_text())["mission"] if it.get("tree")}) \
        if plan_p.exists() else []
    tv = [per_tree.get(t, 0) for t in tgt]
    return {
        "targets": len(tgt), "targets_imaged_2plus": sum(v >= 2 for v in tv),
        "target_frames_min": min(tv) if tv else None,
        "target_frames_median": sorted(tv)[len(tv) // 2] if tv else None,
        "log": str(path), "flight_s": round(flight_s, 1), "distance_m": round(dist),
        "energy_wh": round(e_wh, 1), "energy_lift_wh": round(e_lift, 1), "energy_pusher_wh": round(e_push, 1),
        "battery_used_pct": round(100 * e_wh / BATT_WH, 1),
        "within_usable": e_wh <= BATT_WH * USABLE,
        "hover_throttle": round(hover_thr, 3),
        "frames_total": len(frames), "fps": fps,
        "trees_imaged": sum(v >= 1 for v in vals), "trees_imaged_2plus": sum(v >= 2 for v in vals),
        "trees_total": len(vals),
        "frames_per_tree_median": sorted(vals)[len(vals) // 2] if vals else 0,
        "frames_per_tree_max": max(vals) if vals else 0,
        "per_tree_frames": per_tree,
        "min_crown_clearance_m": round(min_clear[0], 2), "closest_tree": min_clear[1],
        "lift_on_off_events_in_flight": events,
        "cruise_roll_err_p95": round(base_p95, 1) if base_p95 is not None else None,
        "max_abs_roll": round(max(abs(a.Roll) for a in att), 1) if att else None,
        "max_abs_pitch": round(max(abs(a.Pitch) for a in att), 1) if att else None,
        "messages": [m.Message for m in d["MSG"] if any(k in m.Message for k in (
            "Transition", "Mission", "Land", "assist", "Assist", "Crash", "crash", "EKF", "GPS"))],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--fps", type=float, default=3.0)
    ap.add_argument("--json")
    a = ap.parse_args()
    res = analyse(a.log, a.fps)
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))
    short = {k: v for k, v in res.items() if k not in ("per_tree_frames", "messages")}
    print(json.dumps(short, indent=1))


if __name__ == "__main__":
    main()
