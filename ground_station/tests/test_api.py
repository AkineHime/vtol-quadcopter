"""Step 2: REST API + live WebSocket."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.app import create_app


def recv(ws, kind):
    """Next message of a given type (the socket also sends the photo pattern on connect)."""
    while True:
        msg = ws.receive_json()
        if msg["type"] == kind:
            return msg


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def test_layout(client):
    r = client.get("/api/layout").json()
    assert r["layout"]["grid"] == 13 and len(r["field"]) == 4
    assert r["dock"] == pytest.approx([r["layout"]["home"]["lat"], r["layout"]["home"]["lon"]])


def test_trees(client):
    trees = client.get("/api/trees").json()
    assert len(trees) == 169
    assert {"id", "row", "col", "n", "e", "height", "condition", "status", "lat", "lon",
            "confidence", "last_visit", "notes"} <= set(trees[0])


def test_tree_detail_and_404(client):
    r = client.get("/api/trees/P0612").json()
    assert r["tree"]["id"] == "P0612" and r["history"][0]["kind"] == "seed"
    assert client.get("/api/trees/P9999").status_code == 404


def test_event_broadcast(client):
    with client.websocket_connect("/ws") as ws:
        r = client.post("/api/trees/P0005/events", json={"kind": "status", "status": "target"})
        assert r.status_code == 200 and r.json()["status"] == "target"
        msg = recv(ws, "tree")
        assert msg["tree"]["id"] == "P0005" and msg["tree"]["status"] == "target"
    hist = client.get("/api/trees/P0005").json()["history"]
    assert hist[0]["kind"] == "status" and hist[0]["status"] == "target"


def test_event_validation(client):
    assert client.post("/api/trees/P0005/events", json={"kind": "status", "status": "gone"}).status_code == 422
    assert client.post("/api/trees/P0005/events", json={"kind": "seed"}).status_code == 422
    assert client.post("/api/trees/P0005/events", json={"kind": "detection", "confidence": 2}).status_code == 422
    assert client.post("/api/trees/P9999/events", json={"kind": "note", "note": "x"}).status_code == 404


def test_external_write_pushed(client):
    """A teammate's script writing straight to SQLite reaches the dashboard."""
    with client.websocket_connect("/ws") as ws:
        other = sqlite3.connect(config.DB_PATH)
        other.execute("UPDATE trees SET status='cleared' WHERE id='P1212'")
        other.commit()
        other.close()
        msg = recv(ws, "trees")
        assert next(t for t in msg["trees"] if t["id"] == "P1212")["status"] == "cleared"
