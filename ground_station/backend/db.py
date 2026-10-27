"""Per-tree SQLite store.

SCHEMA CONTRACT -- the route planner and the ML pipeline read and write these
tables directly. Do not rename tables or columns without agreeing it with the
team (see ground_station/README.md, "Database").

trees        one row per palm; the columns of flight_software/demo/trees.csv
             (id,row,col,n,e,height,condition,status) plus lat/lon and the
             latest observation (confidence, last_visit) and free-text notes.
tree_events  append-only history: every status change, visit, detection and
             note, newest last. Writing an event also updates the tree row.
meta         key/value: 'layout' (layout.json) and 'photo_pattern'
             ({"every": N, "since": ts}), both as JSON.

Trees returned by list_trees/get_tree also carry `last_photo`, derived from
tree_events (latest event with an image); it is not a stored column.
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

CONDITIONS = ("healthy", "ripe", "frond", "ripe+frond")
STATUSES = ("unscouted", "target", "cleared")
EVENT_KINDS = ("seed", "status", "visit", "detection", "note")

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS trees (
    id          TEXT PRIMARY KEY,               -- e.g. P0712 (row 07, col 12)
    row         INTEGER NOT NULL,
    col         INTEGER NOT NULL,
    n           REAL NOT NULL,                  -- metres north of the dock
    e           REAL NOT NULL,                  -- metres east of the dock
    height      REAL,                           -- m
    condition   TEXT NOT NULL DEFAULT 'healthy' CHECK (condition IN {CONDITIONS}),
    status      TEXT NOT NULL DEFAULT 'unscouted' CHECK (status IN {STATUSES}),
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    confidence  REAL,                           -- 0..1, latest detection
    last_visit  TEXT,                           -- ISO-8601 UTC
    notes       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tree_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tree_id     TEXT NOT NULL REFERENCES trees(id),
    ts          TEXT NOT NULL,                  -- ISO-8601 UTC
    kind        TEXT NOT NULL CHECK (kind IN {EVENT_KINDS}),
    status      TEXT,                           -- status after the event, if it set one
    condition   TEXT,                           -- condition after the event, if it set one
    confidence  REAL,
    image       TEXT,                           -- path relative to ground_station/media
    note        TEXT,
    source      TEXT NOT NULL DEFAULT 'dashboard'  -- dashboard | planner | ml | seed
);
CREATE INDEX IF NOT EXISTS idx_events_tree ON tree_events (tree_id, ts);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def meters_to_latlon(n: float, e: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Same flat-earth conversion as flight_software/upload_mission.py."""
    return (lat0 + n / 111_320.0,
            lon0 + e / (111_320.0 * math.cos(math.radians(lat0))))


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")      # other processes may read while we write
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def init_db(con: sqlite3.Connection, trees_csv: Path | None = None,
            layout_json: Path | None = None) -> int:
    """Create tables; seed the trees if the table is empty. Returns rows inserted."""
    con.executescript(SCHEMA)
    if con.execute("SELECT COUNT(*) FROM trees").fetchone()[0]:
        return 0
    layout = json.loads(Path(layout_json or config.LAYOUT_JSON).read_text())
    lat0, lon0 = layout["home"]["lat"], layout["home"]["lon"]
    ts = now()
    rows = list(csv.DictReader(Path(trees_csv or config.TREES_CSV).open()))
    con.execute("BEGIN")
    con.execute("INSERT OR REPLACE INTO meta VALUES ('layout', ?)", (json.dumps(layout),))
    for r in rows:
        n, e = float(r["n"]), float(r["e"])
        lat, lon = meters_to_latlon(n, e, lat0, lon0)
        con.execute(
            "INSERT INTO trees (id,row,col,n,e,lat,lon,height,condition,status,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], int(r["row"]), int(r["col"]), n, e, round(lat, 8), round(lon, 8),
             float(r["height"]), r["condition"], r["status"], ts))
        con.execute(
            "INSERT INTO tree_events (tree_id,ts,kind,status,condition,note,source)"
            " VALUES (?,?,'seed',?,?,'Imported from farm layout','seed')",
            (r["id"], ts, r["status"], r["condition"]))
    con.execute("COMMIT")
    return len(rows)


def layout(con: sqlite3.Connection) -> dict:
    row = con.execute("SELECT value FROM meta WHERE key='layout'").fetchone()
    return json.loads(row[0]) if row else {}


# last_photo is derived from tree_events (latest event with an image), not a column
_TREE_SELECT = ("SELECT t.*, (SELECT MAX(ts) FROM tree_events ev WHERE ev.tree_id = t.id"
                " AND ev.image IS NOT NULL) AS last_photo FROM trees t")


def list_trees(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute(_TREE_SELECT + " ORDER BY t.row, t.col")]


def get_tree(con: sqlite3.Connection, tree_id: str) -> dict | None:
    r = con.execute(_TREE_SELECT + " WHERE t.id=?", (tree_id,)).fetchone()
    return dict(r) if r else None


PATTERN_STEPS = (1, 2, 4, 8)


def get_pattern(con: sqlite3.Connection) -> dict:
    """Photo pattern: every Nth palm (row-major order) is to be photographed.
    A tree counts as done once it has a photo taken at or after `since`."""
    row = con.execute("SELECT value FROM meta WHERE key='photo_pattern'").fetchone()
    return json.loads(row[0]) if row else {"every": 1, "since": ""}


def set_pattern(con: sqlite3.Connection, every: int) -> dict:
    if every not in PATTERN_STEPS:
        raise ValueError(f"every must be one of {PATTERN_STEPS}")
    p = {"every": every, "since": now()}
    con.execute("INSERT OR REPLACE INTO meta VALUES ('photo_pattern', ?)", (json.dumps(p),))
    return p


def in_pattern(tree: dict, every: int, grid: int) -> bool:
    return (tree["row"] * grid + tree["col"]) % every == 0


def history(con: sqlite3.Connection, tree_id: str) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT * FROM tree_events WHERE tree_id=? ORDER BY ts DESC, id DESC", (tree_id,))]


def add_event(con: sqlite3.Connection, tree_id: str, kind: str, *, status: str | None = None,
              condition: str | None = None, confidence: float | None = None,
              image: str | None = None, note: str | None = None,
              source: str = "dashboard") -> dict:
    """Log an event and apply it to the tree row. Returns the updated tree.

    status/condition/confidence, when given, become the tree's current values;
    'visit' and 'detection' events also set last_visit; a 'note' is appended
    to the tree's notes."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"kind must be one of {EVENT_KINDS}")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if condition is not None and condition not in CONDITIONS:
        raise ValueError(f"condition must be one of {CONDITIONS}")
    if confidence is not None and not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    tree = get_tree(con, tree_id)
    if tree is None:
        raise KeyError(tree_id)
    ts = now()
    sets = {"updated_at": ts}
    if status is not None:
        sets["status"] = status
    if condition is not None:
        sets["condition"] = condition
    if confidence is not None:
        sets["confidence"] = confidence
    if kind in ("visit", "detection"):
        sets["last_visit"] = ts
    if kind == "note" and note:
        sets["notes"] = (tree["notes"] + "\n" if tree["notes"] else "") + note
    con.execute("BEGIN")
    con.execute(
        "INSERT INTO tree_events (tree_id,ts,kind,status,condition,confidence,image,note,source)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (tree_id, ts, kind, status, condition, confidence, image, note, source))
    con.execute(f"UPDATE trees SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?",
                (*sets.values(), tree_id))
    con.execute("COMMIT")
    return get_tree(con, tree_id)


if __name__ == "__main__":       # python -m backend.db  -> create + seed, print a summary
    c = connect()
    added = init_db(c)
    counts = c.execute("SELECT status, condition, COUNT(*) FROM trees GROUP BY 1, 2").fetchall()
    print(f"{config.DB_PATH}: {added} trees seeded" if added else f"{config.DB_PATH}: already seeded")
    for s, cond, k in counts:
        print(f"  {s:10s} {cond:11s} {k}")
