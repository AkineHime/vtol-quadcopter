#!/usr/bin/env python3
"""
bridge_mission_test.py — end-to-end test of the ArduPilot <-> JSBSim bridge.

Starts the JSBSim bridge + ArduPilot SITL (JSON backend), then:

  CHECK 1  elevon sign convention — in MANUAL mode, pulse roll/pitch stick and
           confirm the JSBSim-backed vehicle rolls/pitches the right way
           (not swapped, not inverted).
  CHECK 2  full mission through the real aero — VTOL takeoff, transition,
           survey grid at 12 m/s, VTOL land — via the same MAVLink flow as
           sitl_verify.py, but with JSBSim physics.
  CHECK 3  hover / transition scrutiny — watch for NaN, attitude blow-ups,
           and thrust anomalies specifically in the low-speed phases.

Run inside WSL:
    source ~/venv-ardupilot/bin/activate
    cd flight_software/jsbsim
    python bridge_mission_test.py            # both checks
    python bridge_mission_test.py --signs    # only check 1
"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from pymavlink import mavutil

HERE = Path(__file__).resolve().parent
AP = Path.home() / "ardupilot"
PARAM = "/mnt/e/proggramming/semester proj/flight_software/coconut_quadplane.param"
GCS = str(HERE.parent)          # for upload_mission import
sys.path.insert(0, GCS)
import upload_mission as gcs    # noqa: E402

PLANE_MODES = {"MANUAL": 0, "FBWA": 5, "AUTO": 10, "RTL": 11, "QHOVER": 18,
               "QLOITER": 19, "QLAND": 20, "QRTL": 21, "GUIDED": 15}
_procs: list[subprocess.Popen] = []


def _spawn(cmd, log, cwd=None):
    f = open(HERE / log, "w")
    p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=cwd,
                         preexec_fn=os.setsid)
    _procs.append(p)
    return p


def cleanup(*_):
    for p in _procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:
            pass
    subprocess.run(["pkill", "-x", "arduplane"], capture_output=True)
    subprocess.run(["pkill", "-f", "jsbsim_bridge.py"], capture_output=True)


def start_stack(elevon_pitch=1.0, elevon_roll=1.0):
    print(f"[stack] bridge (elevon pitch={elevon_pitch:+.0f} roll={elevon_roll:+.0f}) ...")
    _spawn([sys.executable, "-u", str(HERE / "jsbsim_bridge.py"),
            "--root", str(HERE), "--model", "CoconutQuadplane", "--rate", "400",
            "--elevon-pitch", str(elevon_pitch), "--elevon-roll", str(elevon_roll)],
           "bridge.log")
    time.sleep(2.5)
    print("[stack] arduplane (--model JSON, real JSBSim physics) ...")
    _spawn([str(AP / "build/sitl/bin/arduplane"),
            "--model", "JSON:127.0.0.1", "--defaults", PARAM, "-w",
            "--home", "-35.363261,149.165237,584,0", "-I0"],
           "sitl.log", cwd=str(Path.home() / "sitlrun"))
    print("[stack] waiting for MAVLink on tcp:5760 ...")
    m = mavutil.mavlink_connection("tcp:127.0.0.1:5760", retries=60)
    m.wait_heartbeat(timeout=90)
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 25, 1)
    print("[stack] heartbeat OK")
    return m


def wait_ready(m, timeout=120):
    print("[stack] waiting for GPS+EKF ...")
    end = time.time() + timeout
    gps = ekf = False
    while time.time() < end:
        msg = m.recv_match(type=["GPS_RAW_INT", "EKF_STATUS_REPORT", "STATUSTEXT"],
                           blocking=True, timeout=5)
        if not msg:
            continue
        t = msg.get_type()
        if t == "GPS_RAW_INT":
            gps = msg.fix_type >= 3
        elif t == "EKF_STATUS_REPORT":
            ekf = (msg.flags & 0x1F) == 0x1F
        elif t == "STATUSTEXT":
            print(f"   [fc] {msg.text}")
        if gps and ekf:
            time.sleep(3)
            print("[stack] ready")
            return True
    return False


def set_mode(m, name):
    m.mav.set_mode_send(m.target_system,
                        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                        PLANE_MODES[name])
    time.sleep(0.5)


def rc(m, ch, val):
    ov = [65535] * 18
    ov[ch - 1] = val
    m.mav.rc_channels_override_send(m.target_system, m.target_component, *ov[:18])


def rc_clear(m):
    m.mav.rc_channels_override_send(m.target_system, m.target_component,
                                   *([0] * 18))


def att(m):
    msg = m.recv_match(type="ATTITUDE", blocking=True, timeout=3)
    if not msg:
        return None
    return dict(roll=math.degrees(msg.roll), pitch=math.degrees(msg.pitch),
                yaw=math.degrees(msg.yaw), p=math.degrees(msg.rollspeed),
                q=math.degrees(msg.pitchspeed), r=math.degrees(msg.yawspeed))


# ---------------------------------------------------------------------------
# CHECK 1 — elevon signs
# ---------------------------------------------------------------------------
def _set_param(m, name, val, timeout=5):
    for _ in range(4):
        m.mav.param_set_send(m.target_system, m.target_component,
                             name.encode(), float(val),
                             mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        end = time.time() + timeout
        while time.time() < end:
            r = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=2)
            if r and r.param_id.strip("\x00") == name and abs(r.param_value - val) < 1e-3:
                return True
    return False


def _arm(m, force=True, retries=25):
    p2 = 21196.0 if force else 0.0
    for i in range(retries):
        m.mav.command_long_send(m.target_system, m.target_component,
                                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                                1, p2, 0, 0, 0, 0, 0)
        res = None
        end = time.time() + 3
        while time.time() < end:
            msg = m.recv_match(type=["COMMAND_ACK", "STATUSTEXT"],
                               blocking=True, timeout=1)
            if not msg:
                continue
            if msg.get_type() == "STATUSTEXT":
                if any(k in msg.text for k in ("Arm", "arm", "PreArm")):
                    print(f"      [fc] {msg.text}")
            elif msg.command == 400:
                res = msg.result
        if res == 0:
            return True
        if i in (3, 10):
            print(f"      arm not accepted (result={res}); retrying"
                  f"{' with force' if force else ''}")
    return False


def _settle(m, hold_ch3, seconds):
    """Hold sticks neutral (throttle only) until roll & pitch are quiet."""
    end = time.time() + seconds
    while time.time() < end:
        rc_clear(m)
        rc(m, 3, hold_ch3)
        a = att(m)
        if a and abs(a["roll"]) < 6 and abs(a["pitch"]) < 8 \
                and abs(a["p"]) < 12 and abs(a["q"]) < 12 and time.time() > end - 2:
            return True
    return False


def _pulse(m, ch, val, hold_ch3, seconds, abort_deg=35.0):
    """Gentle RC input on `ch`; measure the rate response in its first 0.6 s
    (before cross-coupling muddies it) and the net attitude change."""
    _settle(m, hold_ch3, 5.0)
    base = att(m) or {"roll": 0, "pitch": 0}
    early_p = early_q = 0.0
    peak_p = peak_q = 0.0
    diverged = False
    t0 = time.time()
    while time.time() - t0 < seconds:
        rc(m, 3, hold_ch3)
        rc(m, ch, val)
        a = att(m)
        if not a:
            continue
        if time.time() - t0 < 0.6:
            if abs(a["p"]) > abs(early_p):
                early_p = a["p"]
            if abs(a["q"]) > abs(early_q):
                early_q = a["q"]
        peak_p = a["p"] if abs(a["p"]) > abs(peak_p) else peak_p
        peak_q = a["q"] if abs(a["q"]) > abs(peak_q) else peak_q
        if abs(a["roll"]) > abort_deg or abs(a["pitch"]) > abort_deg:
            diverged = True
            break
    cur = att(m) or base
    rc_clear(m)
    return dict(d_roll=round(cur["roll"] - base["roll"], 1),
               d_pitch=round(cur["pitch"] - base["pitch"], 1),
               early_p=round(early_p, 1), early_q=round(early_q, 1),
               peak_p=round(peak_p, 1), peak_q=round(peak_q, 1),
               diverged=diverged)


def check_signs(m):
    print("\n===== CHECK 1: elevon sign convention =====")
    print(f"   ARMING_CHECK=0 set: {_set_param(m, 'ARMING_CHECK', 0)}")
    _set_param(m, "DISARM_DELAY", 0)
    if not wait_ready(m):
        return dict(passed=False, reason="never became ready")

    # VTOL up, then fixed-wing so the elevons are the only pitch/roll control
    set_mode(m, "QLOITER")
    if not _arm(m):
        return dict(passed=False, reason="arm failed")
    print("   climbing in QLOITER ...")
    t0 = time.time()
    while time.time() - t0 < 8:
        rc(m, 3, 1750)                 # climb
        m.recv_match(type="VFR_HUD", blocking=True, timeout=0.5)
    rc(m, 3, 1500)
    time.sleep(2)
    set_mode(m, "FBWA")
    print("   FBWA — commands a target ATTITUDE from the stick; settle and read it")
    t0 = time.time()
    while time.time() - t0 < 12:
        rc(m, 3, 1600)
        m.recv_match(type="VFR_HUD", blocking=True, timeout=0.5)
    hud = m.recv_match(type="VFR_HUD", blocking=True, timeout=2)
    asp = getattr(hud, "airspeed", 0.0)
    print(f"   airspeed = {asp:.1f} m/s")

    def hold_and_read(ch, val, seconds=5.0):
        end = time.time() + seconds
        last = None
        while time.time() < end:
            rc(m, 3, 1600)
            rc(m, ch, val)
            last = att(m) or last
        rc_clear(m)
        # recover to wings-level before the next command
        rec_end = time.time() + 6
        while time.time() < rec_end:
            rc(m, 3, 1600)
            a = att(m)
            if a and abs(a["roll"]) < 5 and abs(a["pitch"]) < 6:
                break
        return last

    # FBWA stick -> target angle (~ +-13 deg at +-25% stick)
    cmds = {"roll_right_stick": (1, 1625), "roll_left_stick": (1, 1375),
            "pitch_up_stick": (2, 1375), "pitch_down_stick": (2, 1625)}
    tests = {}
    for name, (ch, val) in cmds.items():
        a = hold_and_read(ch, val)
        tests[name] = dict(roll=round(a["roll"], 1), pitch=round(a["pitch"], 1)) \
            if a else dict(roll=None, pitch=None)
        print(f"   {name:16s} -> settled roll {tests[name]['roll']:+6.1f}  "
              f"pitch {tests[name]['pitch']:+6.1f}")

    rr, rl = tests["roll_right_stick"], tests["roll_left_stick"]
    pu, pd = tests["pitch_up_stick"], tests["pitch_down_stick"]
    verdict = {
        "roll_right_stick_gives_right_bank": rr["roll"] is not None and rr["roll"] > 5,
        "roll_left_stick_gives_left_bank": rl["roll"] is not None and rl["roll"] < -5,
        "pitch_up_stick_gives_nose_up": pu["pitch"] is not None and pu["pitch"] > 4,
        "pitch_down_stick_gives_nose_down": pd["pitch"] is not None and pd["pitch"] < -4,
        "roll_cmd_stays_mostly_in_roll": abs(rr["roll"]) > abs(rr["pitch"]) + 3,
        "pitch_cmd_stays_mostly_in_pitch": abs(pu["pitch"]) > abs(pu["roll"]),
    }
    for k, v in verdict.items():
        print(f"   [{'OK' if v else 'BAD'}] {k}")
    return dict(airspeed_ms=round(asp, 1), tests=tests, verdict=verdict,
               passed=all(verdict.values()))


# ---------------------------------------------------------------------------
# CHECK 2 + 3 — mission with hover/transition scrutiny
# ---------------------------------------------------------------------------
def check_mission(m):
    print("\n===== CHECK 2/3: full mission through JSBSim aero =====")
    if not wait_ready(m):
        return dict(passed=False, reason="never became ready")

    home_lat, home_lon = gcs.get_home(m)
    wps = gcs.make_grid_mission(home_lat, home_lon, survey_alt=30.0,
                                box_n=140.0, box_e=90.0, row_spacing=70.0)
    gcs.upload_mission(m, wps)
    got = gcs.download_mission(m)
    rt = gcs.verify_roundtrip(wps, got)

    n_items = len(wps) + 1
    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_DO_SET_MISSION_CURRENT, 0,
                            1, 0, 0, 0, 0, 0, 0)
    time.sleep(1)
    _set_param(m, "ARMING_CHECK", 0)
    set_mode(m, "QLOITER")
    time.sleep(1)
    if not _arm(m):
        return dict(passed=False, reason="arm failed", phases={})
    set_mode(m, "AUTO")
    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_MISSION_START, 0,
                            1, n_items - 1, 0, 0, 0, 0, 0)

    phases = dict(vtol_takeoff=False, transition_fw=False, waypoints_done=False,
                  vtol_land=False, disarmed=False)
    anomalies = []
    rows = []
    max_alt = max_asp = 0.0
    max_tilt_in_hover = 0.0
    last_seq = 0
    t0 = time.time()
    print("[fly]  t   mode  alt   asp   wp   roll pitch  note")
    while time.time() - t0 < 720:
        msg = m.recv_match(type=["GLOBAL_POSITION_INT", "VFR_HUD", "ATTITUDE",
                                 "MISSION_CURRENT", "HEARTBEAT", "STATUSTEXT"],
                           blocking=True, timeout=5)
        if not msg:
            anomalies.append("no MAVLink for 5 s")
            continue
        t = msg.get_type()
        now = time.time() - t0
        if t == "STATUSTEXT":
            print(f"   [fc] {msg.text}")
            low = msg.text.lower()
            if "transition" in low and "done" in low:
                phases["transition_fw"] = True
            if any(k in low for k in ("crash", "nan", "ekf fail", "insane")):
                anomalies.append(f"STATUSTEXT: {msg.text}")
        elif t == "GLOBAL_POSITION_INT":
            alt = msg.relative_alt / 1000.0
            if not math.isfinite(alt):
                anomalies.append("non-finite altitude")
            max_alt = max(max_alt, alt)
            if max_alt > 5:
                phases["vtol_takeoff"] = True
            rows.append(dict(t=round(now, 1), alt=round(alt, 1)))
        elif t == "VFR_HUD":
            asp = msg.airspeed
            max_asp = max(max_asp, asp)
            if asp > 10:
                phases["transition_fw"] = True
            if rows:
                rows[-1]["asp"] = round(asp, 1)
        elif t == "ATTITUDE":
            roll = abs(math.degrees(msg.roll))
            pitch = abs(math.degrees(msg.pitch))
            if rows:
                rows[-1]["roll"] = round(math.degrees(msg.roll), 1)
                rows[-1]["pitch"] = round(math.degrees(msg.pitch), 1)
            in_hover = (max_asp < 6.0) and phases["vtol_takeoff"] \
                and not phases["transition_fw"]
            if in_hover:
                max_tilt_in_hover = max(max_tilt_in_hover, max(roll, pitch))
            if max(roll, pitch) > 75 and not phases["waypoints_done"]:
                anomalies.append(
                    f"attitude blow-up {roll:.0f}/{pitch:.0f} deg at t={now:.0f}s")
        elif t == "MISSION_CURRENT":
            if msg.seq != last_seq:
                a = rows[-1] if rows else {}
                print(f"[fly] {now:5.0f} AUTO {max_alt:5.1f} {a.get('asp', 0):5.1f} "
                      f"{msg.seq:>2}/{n_items}")
                last_seq = msg.seq
            if msg.seq >= n_items - 1:
                phases["waypoints_done"] = True
        elif t == "HEARTBEAT":
            armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            if phases["waypoints_done"] and not armed:
                phases["vtol_land"] = phases["disarmed"] = True
                print(f"[fly] {now:5.0f} landed & disarmed")
                break

    # bridge NaN check
    blog = (HERE / "bridge.log").read_text(errors="ignore")
    bridge_nan = "nan" in blog.lower() or "Traceback" in blog
    if bridge_nan:
        anomalies.append("bridge.log contains nan/Traceback")

    _write_mission_artifacts(rows)

    passed = (rt and all([phases["vtol_takeoff"], phases["transition_fw"],
                          phases["waypoints_done"], phases["disarmed"]])
              and not anomalies and max_alt >= 20)
    return dict(passed=passed, mission_roundtrip=rt, phases=phases,
                bridge_nan_free=not bridge_nan,
                anomalies=anomalies, max_alt_m=round(max_alt, 1),
                max_airspeed_ms=round(max_asp, 1),
                max_tilt_in_hover_deg=round(max_tilt_in_hover, 1),
                flight_time_s=round(time.time() - t0, 1))


def _write_mission_artifacts(rows):
    cap = HERE / "captures"
    cap.mkdir(exist_ok=True)
    cols = ["t", "alt", "asp", "roll", "pitch"]
    with (cap / "bridge_mission_telemetry.csv").open("w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        t = [r["t"] for r in rows]
        fig, ax = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
        ax[0].plot(t, [r.get("alt") for r in rows]); ax[0].set_ylabel("alt AGL (m)")
        ax[1].plot(t, [r.get("asp") for r in rows], color="#cf222e")
        ax[1].axhline(12, ls="--", c="grey"); ax[1].set_ylabel("airspeed (m/s)")
        ax[2].plot(t, [r.get("roll") for r in rows], label="roll")
        ax[2].plot(t, [r.get("pitch") for r in rows], label="pitch")
        ax[2].legend(); ax[2].set_ylabel("deg"); ax[2].set_xlabel("t (s)")
        for a in ax:
            a.grid(alpha=.3)
        fig.suptitle("CoconutQuadplane — mission through ArduPilot↔JSBSim bridge")
        fig.tight_layout(); fig.savefig(cap / "bridge_mission.png", dpi=110)
        print(f"[out] {cap/'bridge_mission.png'}")
    except Exception as e:  # noqa: BLE001
        print(f"[out] plot skipped: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--signs", action="store_true", help="only check 1")
    ap.add_argument("--mission", action="store_true", help="only check 2/3")
    ap.add_argument("--stack-only", action="store_true",
                    help="just bring the stack up, report, tear down")
    ap.add_argument("--elevon-pitch", type=float, default=-1.0)
    ap.add_argument("--elevon-roll", type=float, default=-1.0)
    args = ap.parse_args()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    out = {}
    try:
        m = start_stack(args.elevon_pitch, args.elevon_roll)
        if args.stack_only:
            time.sleep(8)
            hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=5)
            att0 = att(m)
            print(f"[stack-only] mode={hb.custom_mode if hb else '?'}  att={att0}")
            blog = (HERE / "bridge.log").read_text(errors="ignore")
            print(f"[stack-only] bridge fps line: "
                  f"{[l for l in blog.splitlines() if 'fps' in l][-1:]}")
            out["stack_only"] = dict(passed=hb is not None and att0 is not None)
        if not args.mission and not args.stack_only:
            out["check1_signs"] = check_signs(m)
        if not args.signs and not args.stack_only:
            out["check23_mission"] = check_mission(m)
    finally:
        (HERE / "captures").mkdir(exist_ok=True)
        (HERE / "captures" / "bridge_test_results.json").write_text(
            json.dumps(out, indent=2, default=str))
        cleanup()

    print("\n" + "=" * 60)
    print(json.dumps(out, indent=2, default=str))
    ok = all(v.get("passed") for v in out.values())
    print(f"\nOVERALL: {'PASS' if ok else 'SEE NOTES'}")


if __name__ == "__main__":
    main()
