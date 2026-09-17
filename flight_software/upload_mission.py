#!/usr/bin/env python3
"""
upload_mission.py  --  minimal pymavlink ground-station link for the
coconut-surveillance QuadPlane running in ArduPilot SITL.

This is the seed of the ground-station layer the route planner will sit on
top of. It does four things:

    1. connect()          -- attach to SITL / a vehicle, wait for heartbeat
    2. make_grid_mission() -- build a lawnmower survey grid over a box
    3. upload_mission()    -- push waypoints using the MAVLink mission protocol
    4. download_mission()  -- read them back for verification
    5. monitor()           -- stream position / battery / mission progress

Run it directly for a full demo (upload -> verify -> optionally fly in AUTO):

    python upload_mission.py --connect udpin:127.0.0.1:14550
    python upload_mission.py --connect udpin:127.0.0.1:14550 --fly

Start SITL so it forwards MAVLink to this script, e.g. from WSL:

    Tools/autotest/sim_vehicle.py -v ArduPlane -f quadplane --console --map \
        --out=udp:127.0.0.1:14550

(From Windows, WSL2 localhost is shared, so udpin:127.0.0.1:14550 works.)
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from pymavlink import mavutil

# ArduPilot custom mode numbers for ArduPlane (mode name -> number).
PLANE_MODES = {
    "MANUAL": 0, "FBWA": 5, "AUTO": 10, "RTL": 11, "LOITER": 12,
    "QHOVER": 18, "QLOITER": 19, "QLAND": 20, "QRTL": 21,
}


# --------------------------------------------------------------------------
# Mission building
# --------------------------------------------------------------------------
@dataclass
class Waypoint:
    lat: float          # degrees
    lon: float          # degrees
    alt: float          # metres, relative to home
    command: int = mavutil.mavlink.MAV_CMD_NAV_WAYPOINT
    param1: float = 0.0  # e.g. hold time / min-pitch for takeoff


def _meters_to_deg(dn: float, de: float, lat0: float) -> tuple[float, float]:
    """Local north/east offset in metres -> (dlat, dlon) in degrees."""
    import math
    dlat = dn / 111_320.0
    dlon = de / (111_320.0 * math.cos(math.radians(lat0)))
    return dlat, dlon


def make_grid_mission(
    home_lat: float,
    home_lon: float,
    *,
    survey_alt: float = 35.0,
    box_n: float = 210.0,      # box size north, metres
    box_e: float = 140.0,      # box size east, metres
    row_spacing: float = 70.0,  # metres between survey lines (>= fixed-wing turn radius)
) -> list[Waypoint]:
    """A VTOL-takeoff -> boustrophedon (lawnmower) grid -> VTOL-land mission,
    laid out over a plantation-sized rectangle just north-east of home."""
    wps: list[Waypoint] = [
        # VTOL climb straight up over home
        Waypoint(home_lat, home_lon, survey_alt,
                 command=mavutil.mavlink.MAV_CMD_NAV_VTOL_TAKEOFF),
    ]

    n = 0.0
    serpentine_east = True
    while n <= box_n:
        e_start, e_end = (0.0, box_e) if serpentine_east else (box_e, 0.0)
        for e in (e_start, e_end):
            dlat, dlon = _meters_to_deg(n, e, home_lat)
            wps.append(Waypoint(home_lat + dlat, home_lon + dlon, survey_alt))
        serpentine_east = not serpentine_east
        n += row_spacing

    # approach fix ~80 m south of home (ArduPilot needs a real run-in leg
    # before a VTOL land -- min 48 m), then descend-and-land at home
    dlat, dlon = _meters_to_deg(-80.0, 0.0, home_lat)
    wps.append(Waypoint(home_lat + dlat, home_lon + dlon, survey_alt))
    wps.append(Waypoint(home_lat, home_lon, 0.0,
                        command=mavutil.mavlink.MAV_CMD_NAV_VTOL_LAND))
    return wps


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------
def connect(endpoint: str, *, source_system: int = 255) -> mavutil.mavfile:
    print(f"[link] connecting to {endpoint} ...")
    m = mavutil.mavlink_connection(endpoint, source_system=source_system)
    m.wait_heartbeat(timeout=30)
    print(f"[link] heartbeat from system {m.target_system} "
          f"component {m.target_component}")
    return m


def get_home(m: mavutil.mavfile, timeout: float = 30.0) -> tuple[float, float]:
    """Block until we have a valid global position, return (lat, lon) deg."""
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
        mavutil.mavlink.MAVLINK_MSG_ID_HOME_POSITION, 0, 0, 0, 0, 0, 0)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = m.recv_match(type=["HOME_POSITION", "GLOBAL_POSITION_INT"],
                           blocking=True, timeout=5)
        if msg is None:
            continue
        if msg.get_type() == "HOME_POSITION":
            return msg.latitude / 1e7, msg.longitude / 1e7
        if msg.lat != 0:
            return msg.lat / 1e7, msg.lon / 1e7
    raise TimeoutError("no position fix from vehicle")


# --------------------------------------------------------------------------
# Mission protocol
# --------------------------------------------------------------------------
def _pack_item(m, seq: int, wp: Waypoint, total: int):
    # ArduPilot reserves mission seq 0 for HOME. Seq 0 we send as a plain
    # waypoint placeholder (the FC overwrites it with the real home); the
    # actual flight commands live at seq 1..N.
    if seq == 0:
        frame = mavutil.mavlink.MAV_FRAME_GLOBAL
        return m.mav.mission_item_int_encode(
            m.target_system, m.target_component, 0, frame,
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 1,
            0.0, 0.0, 0.0, float("nan"), 0, 0, 0.0,
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
    wp = wp  # the command at this seq
    frame = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
    return m.mav.mission_item_int_encode(
        m.target_system, m.target_component, seq, frame, wp.command,
        0, 1,                              # current, autocontinue
        wp.param1, 0.0, 0.0, float("nan"),  # param1..4
        int(wp.lat * 1e7), int(wp.lon * 1e7), wp.alt,
        mavutil.mavlink.MAV_MISSION_TYPE_MISSION)


def _drain(m, msg_type: str, secs: float = 2.0) -> None:
    """Swallow any queued messages of a type so a later recv_match isn't fooled."""
    end = time.time() + secs
    while time.time() < end:
        if m.recv_match(type=msg_type, blocking=True, timeout=0.4) is None:
            return


def upload_mission(m: mavutil.mavfile, wps: list[Waypoint]) -> None:
    """Upload `wps` as flight commands at seq 1..N (seq 0 = home placeholder)."""
    total = len(wps) + 1
    print(f"[mission] uploading {len(wps)} commands (+ home) = {total} items ...")
    m.mav.mission_clear_all_send(m.target_system, m.target_component,
                                 mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
    _drain(m, "MISSION_ACK", 2.0)          # the clear generates its own ACK
    time.sleep(0.2)
    m.mav.mission_count_send(m.target_system, m.target_component, total,
                             mavutil.mavlink.MAV_MISSION_TYPE_MISSION)

    sent: set[int] = set()
    deadline = time.time() + 30
    while time.time() < deadline:
        msg = m.recv_match(
            type=["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"],
            blocking=True, timeout=15)
        if msg is None:
            raise TimeoutError("vehicle stopped requesting mission items")
        if msg.get_type() == "MISSION_ACK":
            # only trust an ACK once every item has actually gone out
            if len(sent) >= total:
                if msg.type != mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    raise RuntimeError(f"mission rejected: type={msg.type}")
                break
            if msg.type not in (mavutil.mavlink.MAV_MISSION_ACCEPTED, 0):
                raise RuntimeError(f"mission rejected: type={msg.type}")
            continue                       # stray/early ACK — ignore
        seq = msg.seq
        if seq >= total:
            continue
        wp = None if seq == 0 else wps[seq - 1]
        m.mav.send(_pack_item(m, seq, wp, total))
        sent.add(seq)
        deadline = time.time() + 30
        cmd = "HOME" if seq == 0 else wps[seq - 1].command
        print(f"[mission]  -> sent item {seq}/{total - 1} (cmd {cmd})")
    print(f"[mission] upload accepted by vehicle ({len(sent)}/{total} items)")


def download_mission(m: mavutil.mavfile) -> list[tuple]:
    _drain(m, "MISSION_COUNT", 1.0)
    cnt_msg = None
    for _ in range(3):
        m.mav.mission_request_list_send(m.target_system, m.target_component,
                                        mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
        cnt_msg = m.recv_match(type="MISSION_COUNT", blocking=True, timeout=5)
        if cnt_msg is not None:
            break
    if cnt_msg is None:
        raise TimeoutError("no MISSION_COUNT in reply")
    count = cnt_msg.count
    items: list[tuple] = []
    for seq in range(count):
        it = None
        for _ in range(4):
            m.mav.mission_request_int_send(
                m.target_system, m.target_component, seq,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
            cand = m.recv_match(type="MISSION_ITEM_INT", blocking=True,
                                timeout=5)
            if cand is not None and cand.seq == seq:
                it = cand
                break
        if it is None:
            raise TimeoutError(f"no MISSION_ITEM_INT for seq {seq}")
        items.append((it.seq, it.command, it.x, it.y, it.z))
    m.mav.mission_ack_send(m.target_system, m.target_component,
                           mavutil.mavlink.MAV_MISSION_ACCEPTED,
                           mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
    return items


def verify_roundtrip(sent: list[Waypoint], got: list[tuple]) -> bool:
    """`got` includes the FC's home item at index 0; compare got[1:] to sent."""
    body = got[1:]
    if len(sent) != len(body):
        print(f"[verify] COUNT MISMATCH sent={len(sent)} got={len(body)} "
              f"(+home)")
        return False
    ok = True
    for wp, (seq, cmd, x, y, z) in zip(sent, body):
        dlat = abs(x / 1e7 - wp.lat)
        dlon = abs(y / 1e7 - wp.lon)
        dalt = abs(z - wp.alt)
        if cmd != wp.command or dlat > 2e-6 or dlon > 2e-6 or dalt > 0.5:
            print(f"[verify] item {seq} differs: cmd {cmd}/{wp.command} "
                  f"dlat={dlat:.2e} dlon={dlon:.2e} dalt={dalt:.2f}")
            ok = False
    print("[verify] round-trip OK" if ok else "[verify] round-trip FAILED")
    return ok


# --------------------------------------------------------------------------
# Arming / mode / telemetry
# --------------------------------------------------------------------------
def set_mode(m: mavutil.mavfile, name: str) -> None:
    mode_id = PLANE_MODES[name]
    m.mav.set_mode_send(m.target_system,
                        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                        mode_id)
    print(f"[mode] requested {name}")


def arm(m: mavutil.mavfile, arm_it: bool = True) -> None:
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
        1 if arm_it else 0, 0, 0, 0, 0, 0, 0)
    m.recv_match(type="COMMAND_ACK", blocking=True, timeout=5)
    print("[arm] armed" if arm_it else "[arm] disarmed")


def monitor(m: mavutil.mavfile, seconds: float = 60.0) -> None:
    print("[tlm] time  alt(m)  gs(m/s)  volt(V)  wp")
    end = time.time() + seconds
    alt = gs = volt = 0.0
    wp_cur = 0
    while time.time() < end:
        msg = m.recv_match(
            type=["GLOBAL_POSITION_INT", "VFR_HUD", "SYS_STATUS",
                  "MISSION_CURRENT"],
            blocking=True, timeout=5)
        if msg is None:
            continue
        t = msg.get_type()
        if t == "GLOBAL_POSITION_INT":
            alt = msg.relative_alt / 1000.0
        elif t == "VFR_HUD":
            gs = msg.groundspeed
        elif t == "SYS_STATUS":
            volt = msg.voltage_battery / 1000.0
        elif t == "MISSION_CURRENT":
            wp_cur = msg.seq
        print(f"[tlm] {time.strftime('%H:%M:%S')}  {alt:6.1f}  {gs:6.1f}  "
              f"{volt:6.2f}  {wp_cur}")


# --------------------------------------------------------------------------
# Demo driver
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--connect", default="udpin:127.0.0.1:14550",
                    help="MAVLink endpoint (default: udpin:127.0.0.1:14550)")
    ap.add_argument("--alt", type=float, default=35.0, help="survey altitude m")
    ap.add_argument("--fly", action="store_true",
                    help="after upload+verify, arm and run the mission in AUTO")
    ap.add_argument("--watch", type=float, default=0.0,
                    help="seconds to stream telemetry after (implies observe)")
    args = ap.parse_args()

    m = connect(args.connect)
    home_lat, home_lon = get_home(m)
    print(f"[home] {home_lat:.7f}, {home_lon:.7f}")

    wps = make_grid_mission(home_lat, home_lon, survey_alt=args.alt)
    upload_mission(m, wps)
    got = download_mission(m)
    verify_roundtrip(wps, got)

    if args.fly:
        set_mode(m, "AUTO")
        time.sleep(1)
        arm(m)
        monitor(m, seconds=args.watch or 240.0)
    elif args.watch:
        monitor(m, seconds=args.watch)


if __name__ == "__main__":
    main()
