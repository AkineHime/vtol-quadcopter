"""Step 3: MAVLink telemetry bridge, against a fake vehicle on a local TCP port."""
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.telemetry import Telemetry
from fake_vehicle import FakeVehicle

LAT, LON = 10.6611, 77.0049


def wait_for(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_reads_vehicle_state():
    v = FakeVehicle()
    v.start()
    got = []
    tel = Telemetry(f"tcp:127.0.0.1:{v.port}")
    tel.start(got.append)
    try:
        assert wait_for(lambda: tel.snapshot().get("lat") is not None)
        s = tel.snapshot()
        assert s["connected"] and s["armed"] and s["mode"] == "AUTO"
        assert s["lat"] == pytest.approx(LAT, abs=1e-4) and s["lon"] == pytest.approx(LON, abs=1e-6)
        assert s["alt"] == pytest.approx(30.0) and s["heading"] == pytest.approx(90.0)
        assert wait_for(lambda: tel.snapshot().get("battery") == 87 and tel.snapshot().get("wp") == 7)
        assert tel.snapshot()["voltage"] == pytest.approx(15.8)
        assert wait_for(lambda: tel.snapshot().get("wp_total") == 29), "MISSION_COUNT minus home"
        assert tel.snapshot()["phase"] == "fixed-wing"                  # pusher on, lift rotors off
        assert v.got_gcs_heartbeat.wait(5), "bridge should send GCS heartbeats"
        n = len(got)
        time.sleep(1.0)
        assert 2 <= len(got) - n <= 7, "push rate should be throttled to ~5 Hz"
        v.stop.set()                                   # vehicle goes away
        assert wait_for(lambda: not tel.snapshot()["connected"], 8)
    finally:
        v.stop.set()
        tel.stop()


def test_phase_from_motor_outputs():
    from backend.telemetry import phase
    assert phase(True, False, 10) == "vtol" and phase(True, True, 20) == "transition"
    assert phase(False, True, 30) == "fixed-wing" and phase(False, False, 0.2) == "ground"


def test_waits_for_sitl_then_connects():
    v = FakeVehicle()                                  # port bound, nothing listening yet
    tel = Telemetry(f"tcp:127.0.0.1:{v.port}")
    tel.start(lambda m: None)
    try:
        time.sleep(1.0)
        assert not tel.snapshot()["connected"]
        v.start()
        assert wait_for(lambda: tel.snapshot()["connected"], 10)
    finally:
        v.stop.set()
        tel.stop()


def test_telemetry_reaches_dashboard_websocket():
    v = FakeVehicle()
    v.start()
    with TestClient(create_app(telemetry=Telemetry(f"tcp:127.0.0.1:{v.port}"))) as client:
        with client.websocket_connect("/ws") as ws:
            for _ in range(60):
                msg = ws.receive_json()
                if msg["type"] == "telemetry" and msg.get("lat"):
                    break
            assert msg["type"] == "telemetry" and msg["mode"] == "AUTO"
        assert client.get("/api/telemetry").json()["connected"]
    v.stop.set()
