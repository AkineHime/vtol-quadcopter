"""Flight recorder (backend/flights.py) and the flights API."""
from fastapi.testclient import TestClient

from backend import db, flights
from backend.app import create_app


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


MISSION = {"route": [{"seq": 1, "tree": None}, {"seq": 5, "tree": "P0101"}, {"seq": 7, "tree": "P0202"},
                     {"seq": 9, "tree": "P0303"}, {"seq": 10, "tree": None}], "targets": ["P0101", "P0202", "P0303"]}


def fly(rec, clock, n, **tel):
    ended = None
    for _ in range(n):
        clock.t += 0.25
        ended = rec.feed({"connected": True, **tel}) or ended
    return ended


def test_recorder_records_one_flight():
    con = db.connect()
    db.init_db(con)
    clock = Clock()
    rec = flights.Recorder(con, snapshot=lambda: ({"distance_m": 900, "energy_wh": 12.0}, MISSION), clock=clock)
    assert fly(rec, clock, 8, armed=False, lat=10.6609, lon=77.0048) is None and rec.active is None   # on the dock
    # armed: the flight starts; 40 s heading north at ~10 m/s, through waypoint 8
    for i in range(160):
        clock.t += 0.25
        rec.feed({"connected": True, "armed": True, "lat": 10.6609 + i * 2.25e-5, "lon": 77.0048, "alt": 30.0,
                  "groundspeed": 10.0, "phase": "fixed-wing" if i > 20 else "vtol", "wp": min(8, i // 19),
                  "battery": 100 - i * 0.1, "wind_speed": 3.0})
    fid = rec.active
    assert fid
    db.add_event(con, "P0101", "detection", label="pre-mature", confidence=0.9, image="P0101/x.jpg", source="camera")
    assert fly(rec, clock, 4, armed=False, lat=10.6645, lon=77.0048) is None       # disarmed < 3 s: still open
    assert fly(rec, clock, 12, armed=False, lat=10.6645, lon=77.0048) == fid      # ended
    s = flights.get_flight(con, fid)["stats"]
    assert s["result"] == "landed" and 39 <= s["duration_s"] <= 41
    assert 350 < s["distance_m"] < 420                                               # ~0.0036 deg of latitude
    assert s["stops_planned"] == 3 and s["stops_reached"] == 2 and s["stops_missed"] == ["P0303"]
    assert s["photos"] == 1 and s["tender_found"] == ["P0101"] and s["max_wind"] == 3.0
    assert s["battery_start"] == 100 and s["battery_end"] < 85
    assert set(s["phase_s"]) == {"vtol", "fixed-wing"}
    f = flights.get_flight(con, fid)
    assert len(f["points"]) >= 75 and f["mission"]["targets"] == MISSION["targets"] and f["plan"]["energy_wh"] == 12.0


def test_link_lost_ends_flight_and_restart_closes_open_one():
    con = db.connect()
    db.init_db(con)
    clock = Clock()
    rec = flights.Recorder(con, snapshot=lambda: ({}, {}), clock=clock)
    fly(rec, clock, 4, armed=True, lat=10.661, lon=77.005)
    fid = rec.active
    ended = None
    for _ in range(int(flights.LINK_END_S / 0.25) + 2):
        clock.t += 0.25
        ended = rec.feed({"connected": False}) or ended
    assert ended == fid and flights.get_flight(con, fid)["result"] == "lost"
    fly(rec, clock, 4, armed=True, lat=10.661, lon=77.005)                          # another flight, then a crash
    open_id = rec.active
    flights.Recorder(con, snapshot=lambda: ({}, {}), clock=clock)                    # server restarts
    assert flights.get_flight(con, open_id)["result"] == "lost"


def test_flights_api():
    with TestClient(create_app()) as client:
        lst = client.get("/api/flights").json()
        assert isinstance(lst, list)
        if lst:
            f = client.get(f"/api/flights/{lst[0]['id']}").json()
            assert {"points", "events", "stats", "plan", "mission"} <= set(f)
        assert client.get("/api/flights/999999").status_code == 404
