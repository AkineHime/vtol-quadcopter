#!/usr/bin/env python3
"""
flight_test.py -- staged bring-up tests for the Gazebo CoconutQuadplane.

Run with Gazebo + SITL already up (run_demo.sh --no-fly), from this folder:

    python flight_test.py hover        # VTOL takeoff 15 m, hover 20 s, VTOL land
    python flight_test.py transition   # takeoff, fly 300 m out and back fixed-wing, land

Prints attitude/position stats so the model and gains can be tuned stage by
stage before the full plantation mission (route_planner.py).
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymavlink import mavutil  # noqa: E402

import sitl_verify as sv  # noqa: E402
import upload_mission as gcs  # noqa: E402
from upload_mission import Waypoint, _meters_to_deg  # noqa: E402

MAV = mavutil.mavlink


def mission(kind: str, home) -> list[Waypoint]:
    lat0, lon0 = home

    def at(n, e, alt, cmd=MAV.MAV_CMD_NAV_WAYPOINT, p1=0.0):
        dlat, dlon = _meters_to_deg(n, e, lat0)
        return Waypoint(lat0 + dlat, lon0 + dlon, alt, command=cmd, param1=p1)

    if kind == "hover":
        # without the explicit MC transition ArduPlane flies the loiter fixed-wing
        stay_vtol = Waypoint(0.0, 0.0, 0.0, command=MAV.MAV_CMD_DO_VTOL_TRANSITION,
                             param1=3.0)
        return [at(0, 0, 15, MAV.MAV_CMD_NAV_VTOL_TAKEOFF), stay_vtol,
                at(0, 0, 15, MAV.MAV_CMD_NAV_LOITER_TIME, 20),
                # slow VTOL sidestep: forces a yaw to face east at low speed
                at(0, 20, 15, MAV.MAV_CMD_NAV_LOITER_TIME, 10),
                at(0, 0, 0, MAV.MAV_CMD_NAV_VTOL_LAND)]
    return [at(0, 0, 30, MAV.MAV_CMD_NAV_VTOL_TAKEOFF),
            at(150, 0, 40), at(300, 0, 40), at(300, -150, 40), at(100, -150, 40),
            at(-90, 0, 40), at(0, 0, 0, MAV.MAV_CMD_NAV_VTOL_LAND)]


def run(m, wps, timeout=600) -> None:
    sv.set_mode(m, "QLOITER")
    time.sleep(1)
    if not sv.arm(m):
        raise SystemExit("arm failed")
    sv.set_mission_current(m, 1)
    sv.set_mode(m, "AUTO")
    t0 = time.time()
    seq = 0
    roll_max = pitch_max = asp_max = 0.0
    home = None
    last_pos = -10.0
    while time.time() - t0 < timeout:
        msg = m.recv_match(type=["ATTITUDE", "GLOBAL_POSITION_INT", "VFR_HUD",
                                 "MISSION_CURRENT", "STATUSTEXT", "HEARTBEAT"],
                           blocking=True, timeout=5)
        if msg is None:
            continue
        t = msg.get_type()
        if t == "STATUSTEXT":
            print(f"[fc] {msg.text}")
        elif t == "ATTITUDE":
            roll_max = max(roll_max, abs(math.degrees(msg.roll)))
            pitch_max = max(pitch_max, abs(math.degrees(msg.pitch)))
        elif t == "VFR_HUD":
            asp_max = max(asp_max, msg.airspeed)
        elif t == "MISSION_CURRENT" and msg.seq != seq:
            seq = msg.seq
            print(f"[seq] {seq}  t={time.time() - t0:.0f}s  max roll {roll_max:.0f} "
                  f"pitch {pitch_max:.0f} asp {asp_max:.1f}")
        elif t == "GLOBAL_POSITION_INT" and msg.lat:
            if home is None:
                home = (msg.lat, msg.lon)
            if msg.time_boot_ms / 1000 - last_pos >= 5:
                last_pos = msg.time_boot_ms / 1000
                dn = (msg.lat - home[0]) / 1e7 * 111320
                de = (msg.lon - home[1]) / 1e7 * 111320 * math.cos(math.radians(msg.lat / 1e7))
                print(f"[pos] t={time.time() - t0:5.0f}  n={dn:7.1f} e={de:7.1f} "
                      f"alt={msg.relative_alt / 1000:5.1f}")
        elif (t == "HEARTBEAT" and msg.type != MAV.MAV_TYPE_GCS and seq >= len(wps)
              and not msg.base_mode & MAV.MAV_MODE_FLAG_SAFETY_ARMED):
            print("[done] landed & disarmed")
            break
    print(f"[stats] max roll {roll_max:.0f} deg, max pitch {pitch_max:.0f} deg, "
          f"max airspeed {asp_max:.1f} m/s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["hover", "transition"])
    ap.add_argument("--connect", default="tcp:127.0.0.1:5760")
    args = ap.parse_args()
    m = gcs.connect(args.connect)
    if not sv.wait_ready(m):
        raise SystemExit("not ready")
    home = gcs.get_home(m)
    wps = mission(args.kind, home)
    gcs.upload_mission(m, wps)
    run(m, wps)


if __name__ == "__main__":
    main()
