"""Photo pattern (every Nth palm) and automatic capture when the drone is overhead."""
import pytest
from fastapi.testclient import TestClient

from backend import config, db
from backend.app import create_app
from backend.capture import Capture

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"


def tel_over(con, tree_id, offset_m=0.0):
    t = db.get_tree(con, tree_id)
    lay = db.layout(con)
    lat, lon = db.meters_to_latlon(t["n"] + offset_m, t["e"], lay["home"]["lat"], lay["home"]["lon"])
    return {"type": "telemetry", "connected": True, "lat": lat, "lon": lon}


@pytest.fixture()
def con(tmp_path):
    c = db.connect(tmp_path / "p.db")
    db.init_db(c)
    return c


@pytest.mark.parametrize("every,expected", [(1, 169), (2, 85), (4, 43), (8, 22)])
def test_pattern_membership(con, every, expected):
    assert sum(db.in_pattern(t, every, 13) for t in db.list_trees(con)) == expected


def test_capture_only_pattern_trees_overhead(con):
    db.set_pattern(con, 2)
    cap = Capture(con)
    assert cap.check(tel_over(con, "P0001")) is None          # index 1: not in every-2nd
    assert cap.check(tel_over(con, "P0000", offset_m=5.0)) is None   # outside the 4 m crown
    req = cap.check(tel_over(con, "P0000", offset_m=2.0))
    assert req["type"] == "capture" and req["tree_id"] == "P0000"
    assert cap.check(tel_over(con, "P0000")) is None, "no re-ask within the retry window"
    assert cap.check({"connected": False, "lat": 1, "lon": 1}) is None
    assert cap.claim(req["capture_id"], "P0000")
    assert not cap.claim(req["capture_id"], "P0000"), "second answer is rejected"


def test_photographed_tree_not_asked_again_until_new_round(con):
    db.set_pattern(con, 4)
    cap = Capture(con)
    db.add_event(con, "P0004", "visit", image="P0004/x.jpg", source="camera")
    cap.refresh()
    assert cap.check(tel_over(con, "P0004")) is None
    db.set_pattern(con, 4)                       # new round: photos before it don't count
    con.execute("UPDATE meta SET value=json_set(value,'$.since','9999') WHERE key='photo_pattern'")
    cap.refresh()
    assert cap.check(tel_over(con, "P0004"))["tree_id"] == "P0004"


def recv(ws, kind):
    """Next message of a given type (on connect the socket also sends the plan and mission)."""
    while True:
        msg = ws.receive_json()
        if msg["type"] == kind:
            return msg


def test_pattern_and_photo_api():
    with TestClient(create_app()) as client:
        app = client.app
        assert client.post("/api/pattern", json={"every": 3}).status_code == 422
        with client.websocket_connect("/ws") as ws:
            recv(ws, "pattern")
            recv(ws, "mission")                                  # last of the connect-time messages
            p = client.post("/api/pattern", json={"every": 8}).json()
            assert p["every"] == 8 and p["since"]
            msg = recv(ws, "pattern")
            assert msg == {"type": "pattern", "pattern": p}
        assert client.get("/api/pattern").json() == p

        con, cap = app.state.con, app.state.capture
        req = cap.check(tel_over(con, "P0008"))
        assert req["tree_id"] == "P0008"
        url = f"/api/trees/P0008/photo?capture_id={req['capture_id']}"
        hdr = {"Content-Type": "image/jpeg"}
        assert client.post(url, content=b"not a jpeg", headers=hdr).status_code == 422
        with client.websocket_connect("/ws") as ws:
            recv(ws, "mission")
            r = client.post(url, content=JPEG, headers=hdr)
            assert r.status_code == 200
            t = r.json()
            assert t["last_photo"] >= p["since"] and t["last_visit"]
            msg = recv(ws, "tree")
            assert msg["tree"]["last_photo"] == t["last_photo"]
        assert client.post(url, content=JPEG, headers=hdr).status_code == 409
        hist = client.get("/api/trees/P0008").json()["history"]
        assert hist[0]["image"].startswith("P0008/") and hist[0]["source"] == "camera"
        assert (config.MEDIA_DIR / hist[0]["image"]).read_bytes() == JPEG
        assert client.get(f"/media/{hist[0]['image']}").content == JPEG
        assert cap.check(tel_over(con, "P0008")) is None      # done for this round
