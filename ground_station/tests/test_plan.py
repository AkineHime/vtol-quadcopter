"""Ripeness prediction, the database mission planner, and the endpoints around them."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend import db, planner, ripeness
from backend.app import create_app

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def ev(kind, days_ago, **kw):
    base = dict(kind=kind, ts=(NOW - timedelta(days=days_ago)).isoformat(), status=None, condition=None,
                label=None, confidence=None)
    return {**base, **kw}


def tree(status="unscouted", health="healthy"):
    return {"status": status, "health": health}


def test_ripeness_rules():
    assert ripeness.score(tree(), [], NOW)[0] == ripeness.UNKNOWN_P
    assert ripeness.score(tree("confirmed"), [], NOW)[0] == 1.0
    # a fresh tender sighting scores its confidence; it fades after the tender window
    fresh = ripeness.score(tree(), [ev("detection", 3, label="pre-mature", confidence=0.84)], NOW)
    stale = ripeness.score(tree(), [ev("detection", 70, label="pre-mature", confidence=0.84)], NOW)
    assert fresh[0] == 0.84 and "tender (detection, 3 d ago" in fresh[1]
    assert stale[0] < 0.5
    # harvested: not due right after, due one bunch interval later
    just = ripeness.score(tree(), [ev("status", 2, status="harvested")], NOW)[0]
    due = ripeness.score(tree(), [ev("status", 45, status="cleared")], NOW)[0]      # old name still read
    assert just < 0.1 < 0.5 < due
    # a detection older than the last harvest no longer counts
    s = ripeness.score(tree(), [ev("status", 2, status="harvested"), ev("detection", 10, label="pre-mature", confidence=0.9)], NOW)
    assert s[0] < 0.1
    # poor health lowers the score; the survey's "ripe" (seeded as tender) counts as a sighting
    ripe = ripeness.score(tree(), [ev("seed", 1, maturity="tender")], NOW)[0]
    ripe_frond = ripeness.score(tree(health="frond-damage"), [ev("seed", 1, maturity="tender")], NOW)[0]
    assert ripe == ripeness.SEED_TENDER_CONF and ripe_frond < ripe
    # a mature or young sighting, and a person logging tender on a visit
    assert ripeness.score(tree(), [ev("detection", 2, label="mature", confidence=0.8)], NOW)[0] == ripeness.STAGE_P["mature"]
    assert ripeness.score(tree(), [ev("visit", 2, maturity="young")], NOW)[0] < 0.5
    assert ripeness.score(tree(), [ev("visit", 2, maturity="tender")], NOW)[0] == ripeness.VISIT_CONF


def test_planner_battery_cap_and_order():
    con = db.connect()
    db.init_db(con)
    db.add_event(con, "P0606", "status", status="target", source="ml")
    p = planner.plan(con)
    assert p["stops"][0]["tree"] and p["n_targets"] >= 1
    assert len(p["stops"]) <= planner.max_stops()
    assert p["battery_pct"] <= p["budget_pct"]                       # the 80% rule holds
    ids = [s["tree"] for s in p["stops"]]
    assert "P0606" in ids                                           # targets always go first
    assert sorted(s["order"] for s in p["stops"]) == list(range(1, len(ids) + 1))
    stops_in_route = [r["tree"] for r in p["route"] if r["tree"]]
    assert sorted(stops_in_route) == sorted(ids)
    wpl = planner.waypoints(p).splitlines()
    assert wpl[0] == "QGC WPL 110" and len(wpl) == 2 + len(p["_items"])
    # confirmed and cleared palms are not revisited
    db.add_event(con, "P0606", "status", status="confirmed")
    assert "P0606" not in [s["tree"] for s in planner.plan(con)["stops"]]


def test_plan_endpoints_and_ml_fields():
    with TestClient(create_app()) as client:
        p = client.get("/api/plan").json()
        assert p["stops"] and "_items" not in p
        r = client.get("/api/plan.waypoints")
        assert r.status_code == 200 and r.text.startswith("QGC WPL 110") and "attachment" in r.headers["content-disposition"]
        t = client.get("/api/trees").json()[0]
        assert 0 <= t["ripe_score"] <= 1 and t["ripe_reason"]
        # ML pipeline: upload the best frame, then post the detection with model + label
        img = client.post("/api/trees/P1010/image", content=b"\xff\xd8 fake jpeg",
                          headers={"Content-Type": "image/jpeg"}).json()["image"]
        r = client.post("/api/trees/P1010/events", json={
            "kind": "detection", "label": "pre-mature", "model": "ripeness-yolo26s", "confidence": 0.84,
            "image": img, "source": "ml"})
        assert r.status_code == 200
        body = r.json()
        assert body["label"] == "pre-mature" and body["confidence"] == 0.84 and body["ripe_score"] == 0.84
        h = client.get("/api/trees/P1010").json()["history"][0]
        assert h["model"] == "ripeness-yolo26s" and h["image"] == img
        assert client.post("/api/trees/P1010/events", json={"kind": "status", "status": "confirmed"}).json()["status"] == "confirmed"
        assert client.post("/api/trees/P1010/image", content=b"nope").status_code == 422
        # the re-plan reflects the change: a confirmed palm leaves the next mission
        assert "P1010" not in [s["tree"] for s in client.get("/api/plan").json()["stops"]]


def test_migration_to_maturity_health(tmp_path):
    """A database from before the classification (survey condition only, status
    'cleared') opens with maturity/health derived and 'cleared' -> 'harvested'."""
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE trees (id TEXT PRIMARY KEY, row INTEGER NOT NULL, col INTEGER NOT NULL, n REAL NOT NULL,
          e REAL NOT NULL, height REAL, condition TEXT NOT NULL DEFAULT 'healthy', status TEXT NOT NULL DEFAULT 'unscouted'
          CHECK (status IN ('unscouted','target','cleared')), lat REAL NOT NULL, lon REAL NOT NULL, confidence REAL,
          last_visit TEXT, notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
        CREATE TABLE tree_events (id INTEGER PRIMARY KEY AUTOINCREMENT, tree_id TEXT NOT NULL REFERENCES trees(id),
          ts TEXT NOT NULL, kind TEXT NOT NULL, status TEXT, condition TEXT, confidence REAL, image TEXT, note TEXT,
          source TEXT NOT NULL DEFAULT 'dashboard');
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO trees VALUES ('P0001',0,1,15,-40,13,'ripe+frond','cleared',10.66,77.0,NULL,NULL,'','2026-10-01');
        INSERT INTO tree_events (tree_id,ts,kind,status,condition,source) VALUES ('P0001','2026-10-01','seed','unscouted','ripe+frond','seed');
        INSERT INTO tree_events (tree_id,ts,kind,status,source) VALUES ('P0001','2026-10-02','status','cleared','dashboard');""")
    old.commit()
    old.close()
    con = db.connect(path)
    db.init_db(con)
    t = db.get_tree(con, "P0001")
    assert (t["maturity"], t["health"], t["status"]) == ("tender", "frond-damage", "harvested")
    hist = db.history(con, "P0001")
    assert hist[0]["status"] == "harvested" and hist[1]["maturity"] == "tender"
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_photo_with_card_reading():
    """The colour-card reader's result arrives with the photo and is logged as a
    detection: maturity set, prediction updated, plan re-made."""
    with TestClient(create_app()) as client:
        assert client.post("/api/pattern", json={"every": 1}).status_code == 200   # every palm due (fresh round)
        cap = client.app.state.capture
        tree = db.get_tree(client.app.state.con, "P1111")
        req = cap.check({"connected": True, "lat": tree["lat"], "lon": tree["lon"]})
        assert req["tree_id"] == "P1111"
        url = f"/api/trees/P1111/photo?capture_id={req['capture_id']}&label=pre-mature&confidence=0.93&model=colour-card-v1"
        r = client.post(url, content=b"\xff\xd8 jpeg", headers={"Content-Type": "image/jpeg"})
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["maturity"] == "tender" and t["label"] == "pre-mature" and t["ripe_score"] == 0.93
        h = client.get("/api/trees/P1111").json()["history"][0]
        assert h["kind"] == "detection" and h["model"] == "colour-card-v1" and h["image"]
        assert "P1111" in [s["tree"] for s in client.get("/api/plan").json()["stops"]]
        bad = client.post(f"/api/trees/P1111/photo?capture_id=x&label=pre-mature", content=b"\xff\xd8",
                          headers={"Content-Type": "image/jpeg"})
        assert bad.status_code == 422                       # a label needs a confidence


def test_manual_wind():
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws") as ws:
            r = client.post("/api/wind", json={"speed": 4.5, "gust": 7.0})
            assert r.status_code == 200 and r.json()["speed"] == 4.5
            while (m := ws.receive_json())["type"] != "wind" or not m["wind"]:
                pass
            assert m["wind"]["gust"] == 7.0
        assert client.get("/api/wind").json()["speed"] == 4.5
        assert client.post("/api/wind", json={"speed": 5, "gust": 3}).status_code == 422   # gust below mean
        assert client.post("/api/wind", json={"speed": 99}).status_code == 422
        assert client.post("/api/wind", json={"speed": None}).json() is None             # cleared
        assert client.get("/api/wind").json() is None
