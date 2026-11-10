"""Step 1: schema + seed."""
import csv
import json

import pytest

from backend import config, db


@pytest.fixture()
def con(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    return c


def test_seed_matches_csv(con):
    rows = list(csv.DictReader(config.TREES_CSV.open()))
    assert len(rows) == 169
    trees = {t["id"]: t for t in db.list_trees(con)}
    assert len(trees) == 169
    for r in rows:
        t = trees[r["id"]]
        for k in ("row", "col"):
            assert t[k] == int(r[k])
        for k in ("n", "e", "height"):
            assert t[k] == pytest.approx(float(r[k]))
        assert (t["condition"], t["status"]) == (r["condition"], r["status"])


def test_csv_columns_kept(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info(trees)")]
    header = next(csv.reader(config.TREES_CSV.open()))
    assert cols[:len(header)] == header          # the planner's column names, same order


def test_latlon_from_dock(con):
    home = json.loads(config.LAYOUT_JSON.read_text())["home"]
    t = db.get_tree(con, "P0000")                 # 20 m N, 45 m W of the dock
    assert t["lat"] == pytest.approx(home["lat"] + 20 / 111_320, abs=1e-7)
    assert t["lon"] < home["lon"]


def test_seed_is_idempotent(con):
    assert db.init_db(con) == 0
    assert len(db.list_trees(con)) == 169
    assert len(db.history(con, "P0000")) == 1


def test_event_updates_tree_and_history(con):
    t = db.add_event(con, "P0005", "detection", condition="ripe", confidence=0.91,
                     image="P0005/1.jpg", source="ml")
    assert (t["condition"], t["confidence"]) == ("ripe", 0.91) and t["last_visit"]
    t = db.add_event(con, "P0005", "status", status="target")
    assert t["status"] == "target"
    t = db.add_event(con, "P0005", "note", note="bunch low on east side")
    assert "bunch low" in t["notes"]
    kinds = [h["kind"] for h in db.history(con, "P0005")]
    assert kinds == ["note", "status", "detection", "seed"]


@pytest.mark.parametrize("kw", [{"status": "bogus"}, {"condition": "dead"}, {"confidence": 1.5}])
def test_bad_values_rejected(con, kw):
    with pytest.raises(ValueError):
        db.add_event(con, "P0001", "status", **kw)


def test_unknown_tree(con):
    with pytest.raises(KeyError):
        db.add_event(con, "P9999", "note", note="x")
