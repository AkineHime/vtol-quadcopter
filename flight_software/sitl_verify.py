#!/usr/bin/env python3
"""
sitl_verify.py -- automated bring-up + flight check for the coconut-surveillance
QuadPlane in ArduPilot SITL.

It:
  1. loads coconut_quadplane.param and verifies every value took,
  2. reboots the flight controller and waits for it to come back healthy,
  3. uploads a small survey grid (via upload_mission.py),
  4. flies it in AUTO: VTOL takeoff -> transition -> waypoints -> VTOL land,
  5. logs telemetry to captures/telemetry.csv, draws captures/track.png,
  6. writes captures/results.json and prints a PASS/FAIL summary.

Usage (from WSL, with SITL already running on tcp:5760):
    python sitl_verify.py --connect tcp:127.0.0.1:5760

Requires: pymavlink, matplotlib (matplotlib optional -- skipped if missing).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

from pymavlink import mavutil

import upload_mission as gcs  # connect / make_grid_mission / upload_mission / ...

HERE = Path(__file__).resolve().parent
PARAM_FILE = HERE / "coconut_quadplane.param"
CAP = HERE / "captures"
CAP.mkdir(exist_ok=True)

# SITL's generic "quadplane" aero model reads roll/pitch from PWM channels 1/2
# by position (aileron, elevator), not by SERVOn_FUNCTION. Our airframe wires
# those two channels as elevons (functions 77/78) -- ArduPilot's mixing is
# identical, but the simulator's fake aero would mis-decode elevon outputs.
# So for the simulation only, put channels 1/2 back to aileron/elevator.
SITL_OVERRIDES = {"SERVO1_FUNCTION": 4.0, "SERVO2_FUNCTION": 19.0}


# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------
def parse_param_file(path: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        if len(parts) >= 2:
            try:
                out[parts[0].upper()] = float(parts[1])
            except ValueError:
                pass
    return out


def _pid(r) -> str:
    p = r.param_id
    if isinstance(p, bytes):
        p = p.decode("ascii", "ignore")
    return p.rstrip("\x00").upper()


def _get_param(m, name: str, timeout=5.0):
    """Request one param and return the PARAM_VALUE whose id actually matches."""
    want = name.upper()
    m.mav.param_request_read_send(m.target_system, m.target_component,
                                  want.encode(), -1)
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=timeout)
        if r is not None and _pid(r) == want:
            return r.param_value
    return None


def load_params(m, params: dict[str, float]) -> list[str]:
    """Set every param, read it back, return the list that failed to stick."""
    print(f"[param] applying {len(params)} parameters")
    for name, val in params.items():
        m.mav.param_set_send(m.target_system, m.target_component, name.encode(),
                             float(val), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        time.sleep(0.03)
    # drain the burst of PARAM_VALUE echoes before we start verifying
    t = time.time()
    while time.time() - t < 4:
        if m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5) is None:
            break
    bad = []
    for name, val in params.items():
        got = _get_param(m, name)
        ok = got is not None and abs(got - val) <= max(1e-4, abs(val) * 1e-3)
        print(f"[param]  {name:<20} want {val:<10g} got "
              f"{'--' if got is None else format(got, 'g'):<10} "
              f"{'OK' if ok else 'MISMATCH'}")
        if not ok:
            bad.append(name)
    return bad


# --------------------------------------------------------------------------
# vehicle state helpers
# --------------------------------------------------------------------------
def reboot(m) -> None:
    print("[boot] rebooting flight controller")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0,
        1, 0, 0, 0, 0, 0, 0)
    time.sleep(3)


def wait_ready(m, timeout=120) -> bool:
    """Wait for GPS 3D fix + EKF happy enough to arm."""
    print("[boot] waiting for GPS + EKF ...")
    m.wait_heartbeat(timeout=30)
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
    deadline = time.time() + timeout
    gps_ok = ekf_ok = False
    while time.time() < deadline:
        msg = m.recv_match(type=["GPS_RAW_INT", "EKF_STATUS_REPORT",
                                 "SYS_STATUS", "STATUSTEXT"],
                           blocking=True, timeout=5)
        if msg is None:
            continue
        t = msg.get_type()
        if t == "GPS_RAW_INT":
            gps_ok = msg.fix_type >= 3
        elif t == "EKF_STATUS_REPORT":
            ekf_ok = (msg.flags & 0x1F) == 0x1F  # attitude+velocity+pos horiz/vert
        elif t == "STATUSTEXT":
            print(f"[fc] {msg.text}")
        if gps_ok and ekf_ok:
            print("[boot] GPS+EKF ok, letting it settle ...")
            time.sleep(10)
            return True
    print("[boot] TIMEOUT waiting for readiness")
    return False


def set_mode(m, name: str) -> None:
    mode_id = m.mode_mapping()[name]
    m.mav.set_mode_send(m.target_system,
                        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                        mode_id)


def set_mission_current(m, seq: int, timeout=10) -> bool:
    """Force MISSION_CURRENT to `seq` (AP 4.5 ignores the deprecated message)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        m.mav.command_long_send(
            m.target_system, m.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_MISSION_CURRENT, 0,
            seq, 0, 0, 0, 0, 0, 0)
        cur = m.recv_match(type="MISSION_CURRENT", blocking=True, timeout=3)
        if cur is not None and cur.seq == seq:
            print(f"[mission] current set to {seq}")
            return True
        time.sleep(1)
    print(f"[mission] WARN could not confirm current == {seq}")
    return False


def arm(m, timeout=60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        m.mav.command_long_send(
            m.target_system, m.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            1, 0, 0, 0, 0, 0, 0)
        t2 = time.time() + 4
        result = None
        while time.time() < t2:
            msg = m.recv_match(type=["COMMAND_ACK", "STATUSTEXT"],
                               blocking=True, timeout=1)
            if msg is None:
                continue
            if msg.get_type() == "STATUSTEXT":
                if any(k in msg.text for k in ("Arm", "arm", "PreArm", "EKF",
                                               "GPS", "AHRS", "check")):
                    print(f"[fc] {msg.text}")
            elif msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                result = msg.result
        if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            print("[arm] armed")
            return True
        print(f"[arm] not armed yet (result={result})")
        time.sleep(3)
    return False


# --------------------------------------------------------------------------
# flight
# --------------------------------------------------------------------------
def fly_mission(m, n_items: int, wall_timeout=400) -> dict:
    """AUTO-fly the loaded mission, recording telemetry. Returns a result dict."""
    rows: list[dict] = []
    phases = {"vtol_takeoff": False, "transition_fw": False,
              "waypoints_done": False, "vtol_land": False, "disarmed": False}
    home = None
    max_alt = 0.0
    max_asp = 0.0
    last_seq = 0

    # Arm in a VTOL hold mode FIRST so the mission can't advance unobserved
    # while arm() is still retrying, then hand over to AUTO.
    set_mode(m, "QLOITER")
    time.sleep(1)
    if not arm(m):
        return {"ok": False, "reason": "arm failed", "phases": phases, "rows": rows}
    set_mission_current(m, 1)
    set_mode(m, "AUTO")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_MISSION_START, 0, 1, n_items - 1, 0, 0, 0, 0, 0)
    crashed = False

    t0 = time.time()
    print("[fly]  t     mode      alt   asp   gs   wp   note")
    while time.time() - t0 < wall_timeout:
        msg = m.recv_match(
            type=["GLOBAL_POSITION_INT", "VFR_HUD", "MISSION_CURRENT",
                  "HEARTBEAT", "STATUSTEXT"],
            blocking=True, timeout=5)
        if msg is None:
            continue
        t = msg.get_type()
        now = time.time() - t0

        if t == "STATUSTEXT":
            txt = msg.text.lower()
            print(f"[fc] {msg.text}")
            if "transition" in txt and "done" in txt:
                phases["transition_fw"] = True
            if "crash" in txt:
                crashed = True
            if "hit ground at" in txt:
                try:
                    spd = float(txt.split("hit ground at")[1].split("m/s")[0])
                    if spd > 3.0:          # a real landing touches down < 1 m/s
                        crashed = True
                except (ValueError, IndexError):
                    pass
            continue

        if t == "GLOBAL_POSITION_INT":
            lat, lon = msg.lat / 1e7, msg.lon / 1e7
            alt = msg.relative_alt / 1000.0
            if home is None and lat != 0:
                home = (lat, lon)
            max_alt = max(max_alt, alt)
            rows.append({"t": round(now, 1), "lat": lat, "lon": lon,
                         "alt": round(alt, 1)})
        elif t == "VFR_HUD":
            asp = msg.airspeed
            max_asp = max(max_asp, asp)
            if rows:
                rows[-1]["asp"] = round(asp, 1)
                rows[-1]["gs"] = round(msg.groundspeed, 1)
            if asp > 12.0:
                phases["transition_fw"] = True
            if max_alt > 8.0:
                phases["vtol_takeoff"] = True
        elif t == "MISSION_CURRENT":
            if msg.seq != last_seq:
                a = rows[-1].get("asp", 0) if rows else 0
                print(f"[fly] {now:5.1f}  AUTO   {max_alt:5.1f} {a:5.1f}   -   "
                      f"{msg.seq:>2}/{n_items}")
                last_seq = msg.seq
            if msg.seq >= n_items - 1:
                phases["waypoints_done"] = True
        elif t == "HEARTBEAT":
            armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            if phases["waypoints_done"] and not armed:
                phases["vtol_land"] = True
                phases["disarmed"] = True
                print(f"[fly] {now:5.1f}  landed & disarmed")
                break

    ok = all([phases["vtol_takeoff"], phases["transition_fw"],
              phases["waypoints_done"], phases["disarmed"]]) \
        and not crashed and max_alt >= 25.0
    return {"ok": ok, "crashed": crashed, "phases": phases, "rows": rows,
            "home": home, "max_alt_m": round(max_alt, 1),
            "max_airspeed_ms": round(max_asp, 1),
            "flight_time_s": round(time.time() - t0, 1)}


# --------------------------------------------------------------------------
# outputs
# --------------------------------------------------------------------------
def write_csv(rows: list[dict]) -> None:
    p = CAP / "telemetry.csv"
    cols = ["t", "lat", "lon", "alt", "asp", "gs"]
    with p.open("w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    print(f"[out] {p}  ({len(rows)} samples)")


def draw_track(rows: list[dict], wps) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # noqa: BLE001
        print(f"[out] matplotlib unavailable ({e}); skipping track.png")
        return
    if not rows:
        return
    lat0 = rows[0]["lat"]
    lon0 = rows[0]["lon"]
    sx = 111_320.0 * math.cos(math.radians(lat0))

    fx = [(r["lon"] - lon0) * sx for r in rows]
    fy = [(r["lat"] - lat0) * 111_320.0 for r in rows]
    wx = [(w.lon - lon0) * sx for w in wps]
    wy = [(w.lat - lat0) * 111_320.0 for w in wps]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    ax1.plot(fx, fy, "-", lw=1, color="#1f6feb", label="flown track")
    ax1.plot(wx, wy, "o--", ms=4, color="#d29922", label="mission")
    ax1.set_aspect("equal"); ax1.set_xlabel("East (m)"); ax1.set_ylabel("North (m)")
    ax1.set_title("Survey grid — planned vs flown"); ax1.legend(); ax1.grid(alpha=.3)

    t = [r["t"] for r in rows]
    alt = [r["alt"] for r in rows]
    asp = [r.get("asp", None) for r in rows]
    ax2.plot(t, alt, color="#2da44e", label="alt (m)")
    ax2.plot(t, [a if a is not None else float("nan") for a in asp],
             color="#cf222e", label="airspeed (m/s)")
    ax2.set_xlabel("t (s, sim)"); ax2.set_title("Altitude & airspeed")
    ax2.legend(); ax2.grid(alpha=.3)

    fig.tight_layout()
    out = CAP / "track.png"
    fig.savefig(out, dpi=110)
    print(f"[out] {out}")


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", default="tcp:127.0.0.1:5760")
    ap.add_argument("--rows", type=int, default=3, help="survey rows (small=fast)")
    ap.add_argument("--skip-params", action="store_true")
    ap.add_argument("--real-elevons", action="store_true",
                    help="keep SERVO1/2 as elevons (only valid with a SITL "
                         "model that de-mixes elevons, e.g. quadplane-elevon)")
    args = ap.parse_args()

    result: dict = {"param_mismatches": [], "flight": {}}

    m = gcs.connect(args.connect)

    if not args.skip_params:
        params = parse_param_file(PARAM_FILE)
        if not args.real_elevons:
            params.update(SITL_OVERRIDES)
        bad = load_params(m, params)
        result["param_mismatches"] = bad
        reboot(m)
        m = gcs.connect(args.connect)

    if not wait_ready(m):
        result["flight"] = {"ok": False, "reason": "vehicle never became ready"}
        _finish(result, [], m)
        return

    home_lat, home_lon = gcs.get_home(m)
    print(f"[home] {home_lat:.7f}, {home_lon:.7f}")
    wps = gcs.make_grid_mission(home_lat, home_lon, survey_alt=35.0,
                                box_n=70.0 * args.rows, box_e=140.0,
                                row_spacing=70.0)
    gcs.upload_mission(m, wps)
    got = gcs.download_mission(m)
    result["mission_roundtrip_ok"] = gcs.verify_roundtrip(wps, got)

    flight = fly_mission(m, len(wps) + 1)   # +1 for the FC home item at seq 0
    result["flight"] = {k: v for k, v in flight.items() if k != "rows"}
    _finish(result, flight.get("rows", []), m, wps)


def _finish(result, rows, m, wps=None):
    if rows:
        write_csv(rows)
        if wps:
            draw_track(rows, wps)
    (CAP / "results.json").write_text(json.dumps(result, indent=2))
    print("\n" + "=" * 60)
    print("RESULT SUMMARY")
    print("=" * 60)
    print(f"param mismatches : {result['param_mismatches'] or 'none'}")
    print(f"mission round-trip: {result.get('mission_roundtrip_ok')}")
    f = result.get("flight", {})
    print(f"flight phases    : {json.dumps(f.get('phases', {}))}")
    print(f"max alt / airspd : {f.get('max_alt_m')} m / "
          f"{f.get('max_airspeed_ms')} m/s")
    verdict = (not result["param_mismatches"]
               and result.get("mission_roundtrip_ok")
               and f.get("ok"))
    print(f"\nOVERALL: {'PASS' if verdict else 'FAIL'}")
    print(f"artefacts in: {CAP}")


if __name__ == "__main__":
    main()
