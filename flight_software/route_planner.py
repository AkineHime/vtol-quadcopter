#!/usr/bin/env python3
"""
route_planner.py -- plan (and optionally fly) a plantation mission from the dock.

Layout: demo/trees.csv + demo/layout.json (make_plantation.py): a 1 ha,
13 x 13 coconut block on 7.5 m spacing, dock 15 m south of the field.

Strategies (--strategy):
  fw_sweep    VTOL takeoff -> fixed-wing lanes over every other tree column
              (15 m lane spacing, interleaved order so each turn-around is
              45-60 m wide, turning outside the field) -> VTOL land. Imaging
              on the move; no stops.
  vtol_sweep  the same lanes flown in multicopter mode at Q_WP_SPEED.
  hover       VTOL hops to every palm whose status is "target" with a short
              inspection stop at --hover-s (confirm flights).
  hybrid      fw_sweep lanes, then back-transition over the field and
              VTOL-hop to the targets, then land.

    python route_planner.py --strategy fw_sweep                 # plan only
    python route_planner.py --strategy fw_sweep --connect tcp:127.0.0.1:5760 --fly

Outputs demo/plan.json (read by the Gazebo world generator) and
demo/mission.waypoints (QGroundControl). --fly additionally runs the mission
and writes demo/captures/ (telemetry, track plot, results).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from pymavlink import mavutil

from upload_mission import Waypoint, _meters_to_deg

HERE = Path(__file__).resolve().parent
DEMO = HERE / "demo"
CAP = DEMO / "captures"
MAV = mavutil.mavlink
VTOL_MC, VTOL_FW = 3, 4

TAKEOFF_ALT = 30.0
SWEEP_ALT = 36.0          # crowns 12-16 m; whole crown in frame from a lane 7.5 m off
HOVER_ABOVE_TALLEST = 10.0  # all stops at (tallest palm + this): hops clear every crown by > 5 m
CAM_DOWN_DEG = 60.0         # fixed nose camera, below the horizon (analysis.py)
APPROACH_MIN = 15.0         # final leg into a stop: long enough for ArduPlane's POSITION1
                            # approach, which turns the nose along the leg (toward the palm)
LEAD = 40.0               # fixed-wing lead-in/out beyond the field edge
TURN_R = 35.0            # fixed-wing U-turn radius (33 m at 15 m/s, 35 deg bank)
BACK_TRANS_D = 75.0      # back-transition starts this far before the first stop's palm (Q_TRANS_DECEL stop ~56 m from 15 m/s)
RETURN_D = 60.0           # last waypoint before VTOL_LAND: ArduPlane pre-arm wants >= its stopping distance (42 m at cruise 15)

HOVER_RADIUS_M = 3.0
HOVER_GS_MAX = 1.0


@dataclass
class Tree:
    id: str
    n: float
    e: float
    height: float
    condition: str
    status: str


@dataclass
class Item:
    wp: Waypoint
    label: str
    n: float | None = None
    e: float | None = None
    tree: str | None = None


def load_layout():
    layout = json.loads((DEMO / "layout.json").read_text())
    trees = [Tree(r["id"], float(r["n"]), float(r["e"]), float(r["height"]), r["condition"], r["status"])
             for r in csv.DictReader((DEMO / "trees.csv").open())]
    return layout, trees


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def order_route(start, targets, end=None):
    """Nearest-neighbour seed + 2-opt (open path from a fixed start, optionally to a fixed end)."""
    left, route, cur = list(targets), [], start
    while left:
        nxt = min(left, key=lambda t: _d(cur, (t.n, t.e)))
        route.append(nxt)
        left.remove(nxt)
        cur = (nxt.n, nxt.e)

    def length(r):
        pts = [start] + [(t.n, t.e) for t in r] + ([end] if end else [])
        return sum(_d(a, b) for a, b in zip(pts, pts[1:]))
    improved = True
    while improved:
        improved = False
        for i in range(len(route) - 1):
            for j in range(i + 1, len(route)):
                cand = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
                if length(cand) + 1e-6 < length(route):
                    route, improved = cand, True
    return route


class Builder:
    def __init__(self, home):
        self.lat0, self.lon0 = home
        self.items: list[Item] = []

    def nav(self, n, e, alt, label, cmd=MAV.MAV_CMD_NAV_WAYPOINT, p1=0.0, tree=None):
        dlat, dlon = _meters_to_deg(n, e, self.lat0)
        self.items.append(Item(Waypoint(self.lat0 + dlat, self.lon0 + dlon, alt, command=cmd, param1=p1),
                               label, n, e, tree))

    def transition(self, state, label):
        self.items.append(Item(Waypoint(0.0, 0.0, 0.0, command=MAV.MAV_CMD_DO_VTOL_TRANSITION,
                                        param1=float(state)), label))


def racetrack_orders(k):
    """Lane index orders for a racetrack sweep of k parallel lanes: consecutive lanes are
    >= k//2 lanes apart (45-60 m: wider than the fixed-wing turn) and every turn is in the
    same direction. Standard (start at an outside lane) and centre-start variants, mirrored."""
    half = (k + 1) // 2
    std = []
    for i in range(half):
        std.append(i)
        if i + half < k:
            std.append(i + half)
    mid = k // 2
    centre = [mid]
    for i in range(mid):
        centre += [i, mid + 1 + i] if mid + 1 + i < k else [i]
    orders = []
    for o in (std, centre):
        for cand in (o, [k - 1 - i for i in o]):
            if sorted(cand) == list(range(k)) and cand not in orders:
                orders.append(cand)
    return orders


def lanes(trees, axis="ns", order=None):
    """Lane cross-positions (every other row/column), flown in racetrack `order`."""
    cols = sorted({t.e for t in trees} if axis == "ns" else {t.n for t in trees})
    lane_x = cols[::2]                        # 7 lanes, 15 m apart
    order = order or racetrack_orders(len(lane_x))[0]
    return [lane_x[i] for i in order]


def lane_axis(wind_n, wind_e):
    """Fly the lanes along the wind: a crosswind makes the aircraft crab, which
    turns the fixed nose camera off the lane (8 m/s across N-S lanes: ~32 deg
    crab, 15 palms never in frame). Square grid, so either axis covers it."""
    return "ew" if abs(wind_e) > abs(wind_n) else "ns"


def lane_segments(trees, lead, axis, order=None, flip=False):
    """(start, end) of each lane in flying order; lane 1 runs low->high along the axis
    (high->low with flip), then the direction alternates."""
    along = [t.n for t in trees] if axis == "ns" else [t.e for t in trees]
    lo, hi = min(along) - 5 - lead, max(along) + 5 + lead
    segs = []
    for i, x in enumerate(lanes(trees, axis, order)):
        a, z = (lo, hi) if (i % 2 == 0) != flip else (hi, lo)
        segs.append(((a, x), (z, x)) if axis == "ns" else ((x, a), (x, z)))
    return segs


def sweep_plan(trees, axis, dock):
    """Racetrack order + direction whose lane 1 starts nearest the dock: the aircraft takes off,
    transitions straight along lane 1 and is scanning at once (no line-up detour)."""
    k = len(lanes(trees, axis))
    best = None
    for order in racetrack_orders(k):
        for flip in (False, True):
            (p0, p1) = lane_segments(trees, LEAD, axis, order, flip)[0]
            # distance from the dock to lane 1's line, plus how far behind the dock it starts
            un, ue = (p1[0] - p0[0]), (p1[1] - p0[1])
            L = math.hypot(un, ue)
            un, ue = un / L, ue / L
            along = (dock[0] - p0[0]) * un + (dock[1] - p0[1]) * ue
            cross = abs(-(dock[0] - p0[0]) * ue + (dock[1] - p0[1]) * un)
            cost = cross + max(0.0, -along)
            if best is None or cost < best[0]:
                best = (cost, order, flip, math.degrees(math.atan2(ue, un)) % 360)
    return best[1], best[2], best[3]


def add_lanes(b, layout, trees, alt, lead, label, axis="ns", order=None, flip=False, dock=None):
    for i, (p0, p1) in enumerate(lane_segments(trees, lead, axis, order, flip)):
        if not (i == 0 and dock is not None and _d(dock, p0) < lead + 10):   # lane 1 straight from the dock
            b.nav(p0[0], p0[1], alt, f"{label} lane {i + 1} start")
        b.nav(p1[0], p1[1], alt, f"{label} lane {i + 1} end")


def lineup_point(trees, axis, back=45.0, order=None, flip=False):
    """A point `back` m before the first lane's start, on its line."""
    (n0, e0), (n1, e1) = lane_segments(trees, LEAD, axis, order, flip)[0]
    L = math.hypot(n1 - n0, e1 - e0)
    return n0 - back * (n1 - n0) / L, e0 - back * (e1 - e0) / L


def reentry(end, heading_in, targets):
    """Plan the turn back after the last lane: a fixed-wing U-turn (TURN_R semicircle, left or
    right) whose exit heading points straight at one of the stops, so the back-transition
    decelerates along a straight line onto it (a stop off that line made the aircraft overshoot
    and backtrack while slowing to a hover). Returns (q1, exit, first stop)."""
    h = math.radians(heading_in)
    fwd = (math.cos(h), math.sin(h))
    best = None
    for side in ((math.sin(h), -math.cos(h)), (-math.sin(h), math.cos(h))):
        q1 = (end[0] + TURN_R * (fwd[0] + side[0]), end[1] + TURN_R * (fwd[1] + side[1]))
        x = (end[0] + 2 * TURN_R * side[0], end[1] + 2 * TURN_R * side[1])
        for t in targets:
            dn, de = t.n - x[0], t.e - x[1]
            along = -(dn * fwd[0] + de * fwd[1])
            lateral = abs(dn * fwd[1] - de * fwd[0])
            if along < BACK_TRANS_D + 15:
                continue
            cost = lateral + 0.1 * along
            if best is None or cost < best[0]:
                best = (cost, q1, x, t)
    if best is None:
        raise ValueError("no stop far enough ahead of the U-turn exit")
    return best[1:]


def add_hops(b, route, hover_s, start, trees):
    """Inspection stops for a fixed forward camera pointing CAM_DOWN_DEG down.

    The nose can't be commanded in VTOL auto, but ArduPlane points it along the
    airspeed vector on legs long enough for a POSITION1 approach and then holds
    it through the stop. So each stop sits short of its palm by
    d = dh / tan(60 deg), which centres the crown in the frame, and is
    approached from a lead-in point APPROACH_MIN back along the palm direction."""
    alt = max(t.height for t in trees) + HOVER_ABOVE_TALLEST
    cur = start
    for t in route:
        d = (alt - t.height) / math.tan(math.radians(CAM_DOWN_DEG))
        un, ue = t.n - cur[0], t.e - cur[1]
        L = math.hypot(un, ue) or 1.0
        un, ue = un / L, ue / L
        stop = (t.n - d * un, t.e - d * ue)
        # always via a lead-in (on the straight path when the leg is long):
        # stops entered straight from a previous hover on 16-21 m legs kept the
        # old heading (hover_ripe: 3 of 6 missed by 77-131 deg), lead-ins aligned
        b.nav(t.n - (d + APPROACH_MIN) * un, t.e - (d + APPROACH_MIN) * ue, alt, f"lead-in {t.id}")
        b.nav(stop[0], stop[1], alt, f"inspect {t.id} ({t.condition})",
              cmd=MAV.MAV_CMD_NAV_LOITER_TIME, p1=hover_s, tree=t.id)
        cur = stop


def build_mission(strategy, home, layout, trees, hover_s=3.0, wind_ne=(0.0, 0.0)):
    axis = lane_axis(*wind_ne)
    b = Builder(home)
    dock = (layout["dock"]["n"], layout["dock"]["e"])
    targets = [t for t in trees if t.status == "target"]
    if strategy in ("fw_sweep", "hybrid"):
        order, flip, hdg = sweep_plan(trees, axis, dock)
        layout["dock"]["heading_deg"] = round(hdg, 1)        # face the dock along lane 1
        b.nav(dock[0], dock[1], SWEEP_ALT, "VTOL takeoff (dock)", cmd=MAV.MAV_CMD_NAV_VTOL_TAKEOFF)
        b.transition(VTOL_FW, "transition -> fixed-wing")
        p0 = lane_segments(trees, LEAD, axis, order, flip)[0][0]
        if _d(dock, p0) > LEAD + 10:                          # dock off the lane line: line up first
            ln, le = lineup_point(trees, axis, order=order, flip=flip)
            b.nav(ln, le, SWEEP_ALT, "line-up before lane 1")
        add_lanes(b, layout, trees, SWEEP_ALT, LEAD, "FW", axis, order, flip, dock)
        if strategy == "hybrid" and targets:
            end = (b.items[-1].n, b.items[-1].e)
            p_prev = (b.items[-2].n, b.items[-2].e)
            hdg_in = math.degrees(math.atan2(end[1] - p_prev[1], end[0] - p_prev[0]))
            alt = max(t.height for t in trees) + HOVER_ABOVE_TALLEST
            q1, x, first = reentry(end, hdg_in, targets)
            b.nav(q1[0], q1[1], alt, "U-turn after the sweep")
            b.nav(x[0], x[1], alt, "U-turn exit")
            L = _d(x, (first.n, first.e))
            a_ = (first.n + (x[0] - first.n) * BACK_TRANS_D / L, first.e + (x[1] - first.e) * BACK_TRANS_D / L)
            b.nav(a_[0], a_[1], alt, "approach first stop")
            b.transition(VTOL_MC, "transition -> VTOL over the field")
            ret = (dock[0] + RETURN_D, dock[1])
            route = [first] + order_route((first.n, first.e), [t for t in targets if t is not first], end=ret)
            add_hops(b, route, hover_s, a_, trees)
            b.nav(dock[0] + RETURN_D, dock[1], TAKEOFF_ALT, "return to dock (VTOL)")
        else:
            b.nav(dock[0] + 90, dock[1], SWEEP_ALT, "landing approach")
        b.nav(dock[0], dock[1], 0.0, "VTOL land (dock)", cmd=MAV.MAV_CMD_NAV_VTOL_LAND)
        return b.items
    b.nav(dock[0], dock[1], TAKEOFF_ALT, "VTOL takeoff (dock)", cmd=MAV.MAV_CMD_NAV_VTOL_TAKEOFF)
    if strategy == "vtol_sweep":
        b.transition(VTOL_MC, "stay VTOL")
        add_lanes(b, layout, trees, SWEEP_ALT, 0.0, "VTOL", axis)
        b.nav(dock[0] + RETURN_D, dock[1], TAKEOFF_ALT, "return to dock")
    elif strategy == "hover":
        b.transition(VTOL_MC, "stay VTOL")
        add_hops(b, order_route(dock, targets), hover_s, dock, trees)
        b.nav(dock[0] + RETURN_D, dock[1], TAKEOFF_ALT, "return to dock")
    else:
        raise ValueError(strategy)
    b.nav(dock[0], dock[1], 0.0, "VTOL land (dock)", cmd=MAV.MAV_CMD_NAV_VTOL_LAND)
    return b.items


def write_plan(strategy, home, layout, trees, items):
    DEMO.mkdir(exist_ok=True)
    plan = {"strategy": strategy, "home": {"lat": home[0], "lon": home[1]}, "layout": layout,
            "trees": [t.__dict__ for t in trees],
            "mission": [{"seq": i + 1, "label": it.label, "cmd": it.wp.command, "n": it.n, "e": it.e,
                         "alt": it.wp.alt, "tree": it.tree} for i, it in enumerate(items)]}
    (DEMO / "plan.json").write_text(json.dumps(plan, indent=1))
    lines = ["QGC WPL 110", f"0\t1\t0\t16\t0\t0\t0\t0\t{home[0]:.7f}\t{home[1]:.7f}\t0\t1"]
    for i, it in enumerate(items, start=1):
        w = it.wp
        frame = 2 if w.command == MAV.MAV_CMD_DO_VTOL_TRANSITION else 3
        lines.append(f"{i}\t0\t{frame}\t{w.command}\t{w.param1:g}\t0\t0\t0\t{w.lat:.7f}\t{w.lon:.7f}\t{w.alt:g}\t1")
    (DEMO / "mission.waypoints").write_text("\n".join(lines) + "\n")


def _fire(m, ev):
    """Inject one disturbance event: an ArduPilot param change (GPS glitch,
    motor failure, ...) or a Gazebo force/torque pulse on the airframe
    (bird strike / gust impact)."""
    import subprocess
    if ev["action"] == "param":
        for name, val in ev["params"].items():
            m.mav.param_set_send(m.target_system, m.target_component, name.encode(), float(val),
                                 MAV.MAV_PARAM_TYPE_REAL32)
    elif ev["action"] == "wrench":
        f, tq = ev.get("force", [0, 0, 0]), ev.get("torque", [0, 0, 0])
        msg = ('entity: {name: "coconut_quadplane::base_link", type: LINK}, wrench: {'
               f'force: {{x: {f[0]}, y: {f[1]}, z: {f[2]}}}, torque: {{x: {tq[0]}, y: {tq[1]}, z: {tq[2]}}}}}')
        subprocess.run(["gz", "topic", "-t", "/world/coconut_plantation/wrench/persistent",
                        "-m", "gz.msgs.EntityWrench", "-p", msg], check=False)
        time.sleep(ev.get("duration", 0.2))
        subprocess.run(["gz", "topic", "-t", "/world/coconut_plantation/wrench/clear",
                        "-m", "gz.msgs.Entity", "-p", 'name: "coconut_quadplane::base_link", type: LINK'],
                       check=False)
    print(f"[event] {ev.get('name', ev['action'])} fired", flush=True)


def fly(m, items, timeout=1800.0, events=None):
    """Arm, run AUTO, stream phases; returns when landed + disarmed.
    events: [{"at_seq": k | "after_s": t, "action": "param"|"wrench", ...}]"""
    import sitl_verify as sv
    pending = list(events or [])
    sv.set_mode(m, "QLOITER")
    time.sleep(1)
    if not sv.arm(m):
        return {"ok": False, "reason": "arm failed"}
    sv.set_mission_current(m, 1)
    sv.set_mode(m, "AUTO")
    m.mav.command_long_send(m.target_system, m.target_component, MAV.MAV_CMD_MISSION_START,
                            0, 1, len(items), 0, 0, 0, 0, 0)
    seq, crashed, landed, t0 = 0, False, False, time.time()
    inverted_since = None
    while time.time() - t0 < timeout:
        msg = m.recv_match(type=["MISSION_CURRENT", "HEARTBEAT", "STATUSTEXT", "ATTITUDE",
                                 "GLOBAL_POSITION_INT"], blocking=True, timeout=1)
        for ev in list(pending):
            if ("at_seq" in ev and seq >= ev["at_seq"]) or ("after_s" in ev and time.time() - t0 >= ev["after_s"]):
                pending.remove(ev)
                _fire(m, ev)
        if msg is None:
            continue
        t = msg.get_type()
        if t == "GLOBAL_POSITION_INT":
            # ground impact faster than 6 m/s (a lift motor out: 10.5 m/s, upright)
            if msg.relative_alt < 1500 and msg.vz > 600:
                crashed = True
                print(f"[phase] CRASHED (impact {msg.vz / 100:.1f} m/s)", flush=True)
                break
            continue
        if t == "ATTITUDE":
            # the FC's own crash check needs a disarm; a VTOL on its back with a
            # motor out just sits there armed. > 100 deg roll/pitch for 5 s = crash.
            if abs(math.degrees(msg.roll)) > 100 or abs(math.degrees(msg.pitch)) > 80:
                inverted_since = inverted_since or time.time()
                if time.time() - inverted_since > 5:
                    crashed = True
                    print("[phase] CRASHED (inverted > 5 s)", flush=True)
                    break
            else:
                inverted_since = None
            continue
        if t == "STATUSTEXT":
            print(f"[fc] {msg.text}", flush=True)
            crashed |= "crash" in msg.text.lower()
        elif t == "MISSION_CURRENT":
            if msg.seq != seq and 1 <= msg.seq <= len(items):
                print(f"[phase] {msg.seq:3d}  {items[msg.seq - 1].label}", flush=True)
            seq = msg.seq
        elif t == "HEARTBEAT" and msg.type != MAV.MAV_TYPE_GCS:
            if seq >= len(items) and not msg.base_mode & MAV.MAV_MODE_FLAG_SAFETY_ARMED:
                landed = True
                print("[phase] landed & disarmed", flush=True)
                break
    return {"ok": landed and not crashed, "landed": landed, "crashed": crashed,
            "wall_s": round(time.time() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default="fw_sweep", choices=["fw_sweep", "vtol_sweep", "hover", "hybrid"])
    ap.add_argument("--hover-s", type=float, default=3.0)
    ap.add_argument("--connect")
    ap.add_argument("--fly", action="store_true")
    ap.add_argument("--result", type=Path, help="write the flight result JSON here")
    ap.add_argument("--events", type=Path, help="JSON list of disturbance events to inject")
    ap.add_argument("--wind-n", type=float, default=0.0, help="forecast wind toward north, m/s")
    ap.add_argument("--wind-e", type=float, default=0.0, help="forecast wind toward east, m/s")
    ap.add_argument("--targets", help="override targets: 'ripe' (ripe* palms) or comma-separated tree ids")
    args = ap.parse_args()

    layout, trees = load_layout()
    if args.targets:
        ids = set(args.targets.split(","))
        for t in trees:
            hit = t.condition.startswith("ripe") if args.targets == "ripe" else t.id in ids
            t.status = "target" if hit else t.status
    home = (layout["home"]["lat"], layout["home"]["lon"])
    m = None
    if args.connect:
        import sitl_verify as sv
        import upload_mission as gcs
        m = gcs.connect(args.connect)
        if not sv.wait_ready(m):
            raise SystemExit("vehicle never became ready")
        home = gcs.get_home(m)
    items = build_mission(args.strategy, home, layout, trees, args.hover_s, (args.wind_n, args.wind_e))
    write_plan(args.strategy, home, layout, trees, items)
    print(f"[plan] {args.strategy}: {len(items)} items, "
          f"{sum(1 for t in trees if t.status == 'target')} targets")
    if m is None:
        return
    import upload_mission as gcs
    wps = [it.wp for it in items]
    gcs.upload_mission(m, wps)
    ok_rt = gcs.verify_roundtrip(wps, gcs.download_mission(m))
    if not args.fly:
        return
    events = json.loads(args.events.read_text()) if args.events else None
    res = fly(m, items, events=events)
    res.update({"strategy": args.strategy, "roundtrip_ok": ok_rt, "items": len(items)})
    if args.result:
        args.result.write_text(json.dumps(res, indent=1))
    print(f"\nFLIGHT: {'OK' if res['ok'] else 'FAIL'} {json.dumps(res)}")


if __name__ == "__main__":
    main()
