"""Flight recorder: every flight (arm -> disarm) saved for replay and the
post-flight report.

flights        one row per flight: start/end, the next-mission plan and the
               simulator's mission as they were at takeoff (JSON), and the
               summary computed when it ends (stats_json)
flight_points  the track, at most POINT_HZ per second: time since takeoff,
               position, altitude, heading, speeds, phase, waypoint, battery, wind

Fed from the telemetry loop (app.py). A flight starts when the vehicle reports
armed and ends after it has been disarmed for END_AFTER_S, or when the link has
been gone for LINK_END_S (then it is marked `lost`).
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS flights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    result      TEXT,                       -- landed | lost (link gone) | NULL while flying
    plan_json   TEXT,                       -- /api/plan at takeoff
    mission_json TEXT,                      -- /api/mission at takeoff (what the autopilot flies)
    stats_json  TEXT                        -- summary, filled when the flight ends
);
CREATE TABLE IF NOT EXISTS flight_points (
    flight_id   INTEGER NOT NULL REFERENCES flights(id),
    t           REAL NOT NULL,              -- s since takeoff (arming)
    lat REAL, lon REAL, alt REAL, heading REAL, groundspeed REAL, airspeed REAL,
    phase TEXT, wp INTEGER, battery REAL, wind REAL
);
CREATE INDEX IF NOT EXISTS idx_points ON flight_points (flight_id, t);
"""
POINT_HZ = 2.0
END_AFTER_S = 3.0
LINK_END_S = 30.0
COLS = ("lat", "lon", "alt", "heading", "groundspeed", "airspeed", "phase", "wp", "battery", "wind")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dist(a, b) -> float:
    dn = (b[0] - a[0]) * 111_320.0
    de = (b[1] - a[1]) * 111_320.0 * math.cos(math.radians(a[0]))
    return math.hypot(dn, de)


class Recorder:
    def __init__(self, con: sqlite3.Connection, snapshot, clock=time.monotonic):
        """snapshot() -> (plan dict, mission dict) taken at takeoff."""
        self.con, self.snapshot, self.clock = con, snapshot, clock
        con.executescript(SCHEMA)
        self.active: int | None = None
        self.t0 = self.last_point = self.disarmed_since = self.lost_since = None
        # a flight left open by a crash or restart is closed as lost
        for (fid,) in con.execute("SELECT id FROM flights WHERE ended_at IS NULL").fetchall():
            self._finish(fid, "lost")

    def feed(self, tel: dict) -> int | None:
        """Telemetry message in; returns a flight id when that flight just ended."""
        now = self.clock()
        if self.active is None:
            if not (tel.get("connected") and tel.get("armed")):
                return None
            plan, mission = self.snapshot()          # takeoff: start a flight; this message is its first point
            cur = self.con.execute("INSERT INTO flights (started_at, plan_json, mission_json) VALUES (?,?,?)",
                                   (now_iso(), json.dumps(plan), json.dumps(mission)))
            self.active, self.t0, self.last_point = cur.lastrowid, now, None
            self.disarmed_since = self.lost_since = None
        if not tel.get("connected"):
            self.lost_since = self.lost_since or now
            if now - self.lost_since >= LINK_END_S:
                return self._end("lost")
            return None
        self.lost_since = None
        if not tel.get("armed"):
            self.disarmed_since = self.disarmed_since or now
            if now - self.disarmed_since >= END_AFTER_S:
                return self._end("landed")
        else:
            self.disarmed_since = None
        if tel.get("armed") and tel.get("lat") is not None and (self.last_point is None or now - self.last_point >= 1.0 / POINT_HZ):
            self.last_point = now
            row = (tel["lat"], tel["lon"], tel.get("alt"), tel.get("heading"), tel.get("groundspeed"),
                   tel.get("airspeed"), tel.get("phase"), tel.get("wp"), tel.get("battery"), tel.get("wind_speed"))
            self.con.execute(f"INSERT INTO flight_points (flight_id, t, {', '.join(COLS)}) VALUES (?,?,{', '.join('?' * len(COLS))})",
                             (self.active, round(now - self.t0, 2), *row))
        return None

    def _end(self, result: str) -> int:
        fid, self.active = self.active, None
        self._finish(fid, result)
        return fid

    def _finish(self, fid: int, result: str) -> None:
        # the flight ends at its last recorded point, not when it is closed (a
        # lost link is only declared 30 s later, a restart can be hours later)
        ended = now_iso()
        last = self.con.execute("SELECT t, alt, groundspeed FROM flight_points WHERE flight_id=? ORDER BY t DESC LIMIT 1",
                                (fid,)).fetchone()
        if last:
            (started,) = self.con.execute("SELECT started_at FROM flights WHERE id=?", (fid,)).fetchone()
            ended = (datetime.fromisoformat(started) + timedelta(seconds=last[0])).isoformat(timespec="seconds")
            if result == "lost" and last[1] is not None and last[1] < 1.0 and (last[2] or 0.0) < 1.0:
                result = "landed"       # the link went after touchdown (e.g. the simulator was shut down)
        self.con.execute("UPDATE flights SET ended_at=?, result=? WHERE id=?", (ended, result, fid))
        self.con.execute("UPDATE flights SET stats_json=? WHERE id=?", (json.dumps(stats(self.con, fid)), fid))


def _points(con, fid) -> list[dict]:
    return [dict(zip(("t", *COLS), r)) for r in
            con.execute(f"SELECT t, {', '.join(COLS)} FROM flight_points WHERE flight_id=? ORDER BY t", (fid,))]


def _events(con, f) -> list[dict]:
    end = f["ended_at"] or now_iso()
    return [dict(r) for r in con.execute(
        "SELECT id, tree_id, ts, kind, status, maturity, label, confidence, model, image, source FROM tree_events"
        " WHERE ts >= ? AND ts <= ? AND kind IN ('status','visit','detection') ORDER BY ts", (f["started_at"], end))]


def stats(con, fid: int) -> dict:
    """Post-flight summary: planned vs flown."""
    f = dict(con.execute("SELECT * FROM flights WHERE id=?", (fid,)).fetchone())
    pts = _points(con, fid)
    plan = json.loads(f["plan_json"] or "null") or {}
    mission = json.loads(f["mission_json"] or "null") or {}
    track = [(p["lat"], p["lon"]) for p in pts if p["lat"] is not None]
    dist = sum(_dist(a, b) for a, b in zip(track, track[1:]))
    stops = [r for r in (mission.get("route") or []) if r.get("tree")]
    max_wp = max((p["wp"] or 0 for p in pts), default=0)
    reached = [s["tree"] for s in stops if s["seq"] < max_wp]          # the autopilot moved past it
    evs = _events(con, f)
    batt = [p["battery"] for p in pts if p["battery"] is not None]
    gaps = sum(1 for a, b in zip(pts, pts[1:]) if b["t"] - a["t"] > 3.0)
    phases = {}
    for a, b in zip(pts, pts[1:]):
        phases[a["phase"] or "unknown"] = phases.get(a["phase"] or "unknown", 0) + (b["t"] - a["t"])
    return {
        "duration_s": round(pts[-1]["t"], 1) if pts else 0.0,
        "distance_m": round(dist),
        "max_alt_m": round(max((p["alt"] or 0 for p in pts), default=0), 1),
        "max_groundspeed": round(max((p["groundspeed"] or 0 for p in pts), default=0), 1),
        "max_wind": round(max((p["wind"] or 0 for p in pts), default=0), 1),
        "battery_start": batt[0] if batt else None, "battery_end": batt[-1] if batt else None,
        "phase_s": {k: round(v, 1) for k, v in phases.items()},
        "stops_planned": len(stops), "stops_reached": len(reached), "stops_missed": [s["tree"] for s in stops if s["tree"] not in reached],
        "planned_distance_m": plan.get("distance_m"), "planned_energy_wh": plan.get("energy_wh"),
        "photos": sum(1 for e in evs if e["image"]),
        "detections": sum(1 for e in evs if e["kind"] == "detection"),
        "tender_found": sorted({e["tree_id"] for e in evs if e["maturity"] == "tender" or e["label"] == "pre-mature"}),
        "targets_flagged": sorted({e["tree_id"] for e in evs if e["kind"] == "status" and e["status"] == "target"}),
        "link_gaps": gaps,
        "result": f["result"],
    }


def list_flights(con) -> list[dict]:
    out = []
    for r in con.execute("SELECT id, started_at, ended_at, result, stats_json FROM flights ORDER BY id DESC"):
        d = dict(r)
        d["stats"] = json.loads(d.pop("stats_json") or "null")
        out.append(d)
    return out


def get_flight(con, fid: int) -> dict | None:
    r = con.execute("SELECT * FROM flights WHERE id=?", (fid,)).fetchone()
    if not r:
        return None
    f = dict(r)
    return {"id": f["id"], "started_at": f["started_at"], "ended_at": f["ended_at"], "result": f["result"],
            "plan": json.loads(f["plan_json"] or "null"), "mission": json.loads(f["mission_json"] or "null"),
            "stats": json.loads(f["stats_json"] or "null") or stats(con, fid),
            "points": _points(con, fid), "events": _events(con, f)}
