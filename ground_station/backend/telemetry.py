"""MAVLink -> dashboard telemetry bridge (pymavlink, runs in a background thread).

Connects to MAVLINK_URL (default tcp:127.0.0.1:5762, the SITL's second
serial port, so the route planner keeps 5760), reconnects on loss, and pushes
a compact state dict at most 5 times a second."""
from __future__ import annotations

import math
import threading
import time

from pymavlink import mavutil

MAV = mavutil.mavlink
SEND_PERIOD = 0.2          # s, max telemetry push rate to the dashboard
LINK_TIMEOUT = 3.0         # s without a vehicle heartbeat -> disconnected
SPIN_PWM = 1100            # a motor output above this counts as running
LIFT_CH, PUSHER_CH = (5, 6, 7, 8), 3     # coconut_quadplane.param: lift motors 5-8, pusher on 3


def phase(lift: bool, pusher: bool, alt: float | None) -> str:
    """QuadPlane flight phase from the motor outputs (ArduPilot has no single
    message for it): lift rotors only = VTOL, both = transition, pusher only =
    fixed-wing."""
    if lift and pusher:
        return "transition"
    if lift:
        return "vtol"
    if pusher:
        return "fixed-wing"
    return "ground" if (alt or 0.0) < 1.0 else "glide"


class Telemetry:
    def __init__(self, url: str) -> None:
        self.url = url
        self.state: dict = {"connected": False, "url": url}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._emit = None
        self._last_hb = 0.0
        self._last_send = 0.0

    # -- lifecycle -------------------------------------------------------
    def start(self, emit) -> None:
        self._emit = emit
        if self.url.lower() in ("", "none", "off"):
            return
        self._thread = threading.Thread(target=self._run, name="mavlink", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.state)

    # -- internals -------------------------------------------------------
    def _update(self, **kw) -> None:
        with self._lock:
            self.state.update(kw)

    def _push(self, force: bool = False) -> None:
        t = time.monotonic()
        if self._emit and (force or t - self._last_send >= SEND_PERIOD):
            self._last_send = t
            self._emit({"type": "telemetry", **self.snapshot()})

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                m = mavutil.mavlink_connection(self.url, source_system=255, source_component=190)
            except Exception as e:                   # SITL not up yet
                self._update(connected=False, error=str(e))
                self._stop.wait(2.0)
                continue
            try:
                self._loop(m)
            except Exception as e:
                self._update(connected=False, error=str(e))
            finally:
                try:
                    m.close()
                except Exception:
                    pass
            self._push(force=True)
            self._stop.wait(1.0)

    def _loop(self, m) -> None:
        streams_requested = False
        last_gcs_hb = 0.0
        asked_count = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_gcs_hb > 1.0:              # announce ourselves as a GCS
                m.mav.heartbeat_send(MAV.MAV_TYPE_GCS, MAV.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                last_gcs_hb = now
            if self.state["connected"] and now - self._last_hb > LINK_TIMEOUT:
                self._update(connected=False)
                self._push(force=True)
            msg = m.recv_match(blocking=True, timeout=0.5)
            if msg is None:
                continue
            t = msg.get_type()
            if t == "HEARTBEAT":
                if msg.type == MAV.MAV_TYPE_GCS or msg.autopilot == MAV.MAV_AUTOPILOT_INVALID:
                    continue
                self._last_hb = time.monotonic()
                if not streams_requested:
                    m.target_system, m.target_component = msg.get_srcSystem(), msg.get_srcComponent()
                    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                                   MAV.MAV_DATA_STREAM_ALL, 5, 1)
                    m.waypoint_request_list_send()          # -> MISSION_COUNT: wp_total
                    streams_requested = True
                was = self.state["connected"]
                self._update(connected=True, error=None, mode=mavutil.mode_string_v10(msg),
                             armed=bool(msg.base_mode & MAV.MAV_MODE_FLAG_SAFETY_ARMED))
                self._push(force=not was)
                continue
            if t == "GLOBAL_POSITION_INT":
                kw = dict(lat=msg.lat / 1e7, lon=msg.lon / 1e7, alt=msg.relative_alt / 1000.0,
                          groundspeed=round(math.hypot(msg.vx, msg.vy) / 100.0, 2))
                if msg.hdg != 65535:
                    kw["heading"] = msg.hdg / 100.0
                self._update(**kw)
            elif t == "VFR_HUD":
                self._update(airspeed=round(msg.airspeed, 2), groundspeed=round(msg.groundspeed, 2),
                             heading=float(msg.heading), climb=round(msg.climb, 2))
            elif t == "SYS_STATUS":
                self._update(battery=None if msg.battery_remaining < 0 else msg.battery_remaining,
                             voltage=None if msg.voltage_battery == 65535 else msg.voltage_battery / 1000.0)
            elif t == "MISSION_CURRENT":
                self._update(wp=msg.seq)
                # the mission may be uploaded after we connected: ask for its size again
                if msg.seq > (self.state.get("wp_total") or 0) and now - asked_count > 5.0:
                    m.waypoint_request_list_send()
                    asked_count = now
            elif t == "WIND":                        # ArduPilot's estimate; direction = where it comes from
                self._update(wind_speed=round(msg.speed, 2), wind_dir=round(msg.direction % 360, 1))
            elif t == "GPS_RAW_INT":
                self._update(gps_fix=msg.fix_type, gps_sats=msg.satellites_visible)
            elif t == "MISSION_COUNT":
                self._update(wp_total=max(0, msg.count - 1))      # item 0 is home
            elif t == "SERVO_OUTPUT_RAW":
                out = lambda ch: getattr(msg, f"servo{ch}_raw", 0) or 0
                lift = any(out(c) > SPIN_PWM for c in LIFT_CH)
                self._update(phase=phase(lift, out(PUSHER_CH) > SPIN_PWM, self.state.get("alt")))
            elif t == "STATUSTEXT":
                self._update(text=msg.text)
                self._push(force=True)
                continue
            else:
                continue
            self._push()
