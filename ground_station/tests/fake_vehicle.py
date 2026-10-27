"""A fake ArduPlane on a TCP port, for tests (and for trying the dashboard
without the simulator):   python tests/fake_vehicle.py   -> tcp:127.0.0.1:5762

It circles the plantation at 30 m and streams HEARTBEAT, GLOBAL_POSITION_INT,
VFR_HUD, SYS_STATUS and MISSION_CURRENT at 10 Hz."""
from __future__ import annotations

import math
import socket
import threading
import time

from pymavlink import mavutil

MAV = mavutil.mavlink
HOME = (10.6609, 77.0048)          # flight_software/demo/layout.json "home" (the dock)


def circle(t: float, speed: float = 8.0, radius: float = 40.0):
    """(lat, lon, heading_deg) on a circle around the field centre (65 m N of the dock)."""
    a = speed * t / radius
    n, e = 65.0 + radius * math.cos(a), radius * math.sin(a)
    heading = (math.degrees(a) + 90.0) % 360.0          # tangent, clockwise seen from above
    return (HOME[0] + n / 111_320.0,
            HOME[1] + e / (111_320.0 * math.cos(math.radians(HOME[0]))), heading)


class FakeVehicle:
    def __init__(self, port: int = 0, path=None):
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", port))
        self.port = self.srv.getsockname()[1]
        self.path = path
        self.stop = threading.Event()
        self.got_gcs_heartbeat = threading.Event()

    def start(self) -> "FakeVehicle":
        self.srv.listen(1)
        threading.Thread(target=self._serve, daemon=True).start()
        return self

    def _serve(self) -> None:
        self.srv.settimeout(0.5)
        while not self.stop.is_set():
            try:
                conn, _ = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self._stream(conn)
        self.srv.close()

    def _stream(self, conn) -> None:
        conn.settimeout(0.05)
        enc = MAV.MAVLink(None, srcSystem=1, srcComponent=1)
        dec = MAV.MAVLink(None)
        t0, k = time.monotonic(), 0
        while not self.stop.is_set():
            if self.path:
                lat, lon, hdg = self.path(time.monotonic() - t0)
            else:
                lat, lon, hdg = 10.6611 + k * 1e-6, 77.0049, 90.0
            msgs = [
                enc.heartbeat_encode(MAV.MAV_TYPE_FIXED_WING, MAV.MAV_AUTOPILOT_ARDUPILOTMEGA,
                                     MAV.MAV_MODE_FLAG_SAFETY_ARMED | MAV.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                                     10, MAV.MAV_STATE_ACTIVE),                       # 10 = AUTO
                enc.global_position_int_encode(k, int(lat * 1e7), int(lon * 1e7), 330_000, 30_000,
                                               300, 400, 0, int(hdg * 100)),
                enc.vfr_hud_encode(16.0, 5.0, int(hdg), 40, 30.0, 0.5),
                enc.sys_status_encode(0, 0, 0, 500, 15800, -1, 87, 0, 0, 0, 0, 0, 0),
                enc.mission_current_encode(7),
            ]
            try:
                conn.sendall(b"".join(m.pack(enc) for m in msgs))
                for m in dec.parse_buffer(conn.recv(4096)) or []:
                    if m.get_type() == "HEARTBEAT" and m.type == MAV.MAV_TYPE_GCS:
                        self.got_gcs_heartbeat.set()
            except socket.timeout:
                pass
            except OSError:
                break
            k += 1
            time.sleep(0.1)
        conn.close()


if __name__ == "__main__":
    v = FakeVehicle(5762, path=circle).start()
    print("fake vehicle on tcp:127.0.0.1:5762 -- Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        v.stop.set()
