"""Per-tree SQLite store.

SCHEMA CONTRACT -- the route planner and the ML pipeline read and write these
tables directly. Do not rename tables or columns without agreeing it with the
team (see ground_station/README.md, "Database").

trees        one row per palm; the columns of flight_software/demo/trees.csv
             (id,row,col,n,e,height,condition,status) plus lat/lon, the palm's
             classification and the latest observation:
               maturity  unknown | young | tender | mature | over-mature
                         (tender = 7-8 month nuts = the harvest target)
               health    healthy | frond-damage | pest
               status    unscouted | target | confirmed | harvested
               condition the farm survey's original value, kept read-only
                         (healthy | ripe | frond | ripe+frond) for trees.csv
tree_events  append-only history: every status change, visit, detection and
             note, newest last. Writing an event also updates the tree row.
             Detections carry the model name and its label; the ML labels map
             to maturity (pre-mature -> tender, mature, over-mature).
meta         key/value, JSON: 'layout' (layout.json), 'photo_pattern'
             ({"every": N, "since": ts}) and 'wind_manual' ({"speed", "gust", "ts"}).

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

CONDITIONS = ("healthy", "ripe", "frond", "ripe+frond")       # survey vocabulary (trees.csv)
MATURITIES = ("unknown", "young", "tender", "mature", "over-mature")
HEALTHS = ("healthy", "frond-damage", "pest")
STATUSES = ("unscouted", "target", "confirmed", "harvested")  # confirmed: a confirm stop saw tender nuts
EVENT_KINDS = ("seed", "status", "visit", "detection", "note")
STATUS_ALIASES = {"cleared": "harvested"}                      # the old name, still accepted
LABEL_MATURITY = {"pre-mature": "tender", "tender": "tender", "young": "young",
                  "mature": "mature", "over-mature": "over-mature"}


def from_condition(cond: str) -> tuple[str, str]:
    """Survey condition -> (maturity, health). The survey's 'ripe' marks the
    palms to harvest, i.e. tender nuts."""
    return ("tender" if cond in ("ripe", "ripe+frond") else "unknown",
            "frond-damage" if cond in ("frond", "ripe+frond") else "healthy")


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
    maturity    TEXT NOT NULL DEFAULT 'unknown' CHECK (maturity IN {MATURITIES}),
    health      TEXT NOT NULL DEFAULT 'healthy' CHECK (health IN {HEALTHS}),
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    confidence  REAL,                           -- 0..1, latest detection
    label       TEXT,                           -- latest detection label, e.g. pre-mature
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
    condition   TEXT,                           -- survey condition (seed events only)
    maturity    TEXT,                           -- maturity after the event, if it set one
    health      TEXT,                           -- health after the event, if it set one
    confidence  REAL,
    model       TEXT,                           -- detector that produced it, e.g. ripeness-yolo26s
    label       TEXT,                           -- detector label, e.g. pre-mature
    image       TEXT,                           -- path relative to ground_station/media
    note        TEXT,
    source      TEXT NOT NULL DEFAULT 'dashboard'  -- dashboard | camera | planner | ml | seed
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
    _migrate(con)
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
        mat, hea = from_condition(r["condition"])
        status = STATUS_ALIASES.get(r["status"], r["status"])
        con.execute(
            "INSERT INTO trees (id,row,col,n,e,lat,lon,height,condition,status,maturity,health,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["id"], int(r["row"]), int(r["col"]), n, e, round(lat, 8), round(lon, 8),
             float(r["height"]), r["condition"], status, mat, hea, ts))
        con.execute(
            "INSERT INTO tree_events (tree_id,ts,kind,status,condition,maturity,health,note,source)"
            " VALUES (?,?,'seed',?,?,?,?,'Imported from farm survey','seed')",
            (r["id"], ts, status, r["condition"], mat, hea))
    con.execute("COMMIT")
    return len(rows)


def _migrate(con: sqlite3.Connection) -> None:
    """Bring a database made by an older version up to SCHEMA: new columns on
    tree_events; and, when the trees table predates the maturity/health
    classification (its CHECK constraints can't be altered), rebuild it,
    deriving maturity and health from the survey condition and renaming the
    status 'cleared' to 'harvested'."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(tree_events)")}
    for c in ("model", "label", "maturity", "health"):
        if c not in cols:
            con.execute(f"ALTER TABLE tree_events ADD COLUMN {c} TEXT")
    con.execute("UPDATE tree_events SET status='harvested' WHERE status='cleared'")
    # seed events from before the classification: derive it from their survey condition
    con.execute("UPDATE tree_events SET maturity='tender' WHERE kind='seed' AND maturity IS NULL"
                " AND condition IN ('ripe','ripe+frond')")
    con.execute("UPDATE tree_events SET health='frond-damage' WHERE kind='seed' AND health IS NULL"
                " AND condition IN ('frond','ripe+frond')")
    sql = con.execute("SELECT sql FROM sqlite_master WHERE name='trees'").fetchone()[0]
    if "'harvested'" in sql and "maturity" in sql:
        return
    old = [r[1] for r in con.execute("PRAGMA table_info(trees)")]
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("PRAGMA legacy_alter_table=ON")      # keep tree_events' foreign key pointing at "trees"
    con.execute("BEGIN")
    con.execute("ALTER TABLE trees RENAME TO trees_old")
    con.execute(SCHEMA.split("CREATE TABLE IF NOT EXISTS tree_events")[0].strip().rstrip(";"))
    keep = [c for c in old if c not in ("status", "maturity", "health")]
    for r in con.execute(f"SELECT {', '.join(old)} FROM trees_old").fetchall():
        d = dict(zip(old, r))
        mat, hea = from_condition(d["condition"])
        vals = {**{c: d[c] for c in keep}, "status": STATUS_ALIASES.get(d["status"], d["status"]),
                "maturity": d.get("maturity") or mat, "health": d.get("health") or hea}
        con.execute(f"INSERT INTO trees ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})",
                    tuple(vals.values()))
    con.execute("DROP TABLE trees_old")
    con.execute("COMMIT")
    con.execute("PRAGMA legacy_alter_table=OFF")
    con.execute("PRAGMA foreign_keys=ON")


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


def get_wind(con: sqlite3.Connection) -> dict | None:
    """Wind entered by the operator (anemometer or forecast), for the go/no-go check
    before takeoff; once flying, the autopilot's own estimate is used instead."""
    row = con.execute("SELECT value FROM meta WHERE key='wind_manual'").fetchone()
    return json.loads(row[0]) if row else None


def set_wind(con: sqlite3.Connection, speed: float | None, gust: float | None = None) -> dict | None:
    if speed is None:
        con.execute("DELETE FROM meta WHERE key='wind_manual'")
        return None
    if not 0 <= speed <= 40 or (gust is not None and not speed <= gust <= 50):
        raise ValueError("wind speed 0-40 m/s; gust >= speed")
    w = {"speed": speed, "gust": gust, "ts": now()}
    con.execute("INSERT OR REPLACE INTO meta VALUES ('wind_manual', ?)", (json.dumps(w),))
    return w


def in_pattern(tree: dict, every: int, grid: int) -> bool:
    return (tree["row"] * grid + tree["col"]) % every == 0


def history(con: sqlite3.Connection, tree_id: str) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT * FROM tree_events WHERE tree_id=? ORDER BY ts DESC, id DESC", (tree_id,))]


def add_event(con: sqlite3.Connection, tree_id: str, kind: str, *, status: str | None = None,
              maturity: str | None = None, health: str | None = None, confidence: float | None = None,
              image: str | None = None, note: str | None = None, source: str = "dashboard",
              model: str | None = None, label: str | None = None, condition: str | None = None) -> dict:
    """Log an event and apply it to the tree row. Returns the updated tree.

    status/maturity/health/confidence, when given, become the tree's current
    values; a detection label that names a maturity stage sets maturity too;
    a survey `condition` (older clients) sets health, and maturity when it says
    ripe; 'visit' and 'detection' events also set last_visit; a 'note' is
    appended to the tree's notes."""
    status = STATUS_ALIASES.get(status, status)
    if label is not None and maturity is None:
        maturity = LABEL_MATURITY.get(label)
    if condition is not None:
        if condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {CONDITIONS}")
        m, h = from_condition(condition)
        health = health or h
        maturity = maturity or (m if m != "unknown" else None)
    if kind not in EVENT_KINDS:
        raise ValueError(f"kind must be one of {EVENT_KINDS}")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if maturity is not None and maturity not in MATURITIES:
        raise ValueError(f"maturity must be one of {MATURITIES}")
    if health is not None and health not in HEALTHS:
        raise ValueError(f"health must be one of {HEALTHS}")
    if confidence is not None and not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if label is not None and not (0 < len(label) <= 40):
        raise ValueError("label must be 1-40 characters")
    tree = get_tree(con, tree_id)
    if tree is None:
        raise KeyError(tree_id)
    ts = now()
    sets = {"updated_at": ts}
    for k, v in (("status", status), ("maturity", maturity), ("health", health), ("condition", condition),
                 ("confidence", confidence), ("label", label)):
        if v is not None:
            sets[k] = v
    if kind in ("visit", "detection"):
        sets["last_visit"] = ts
    if kind == "note" and note:
        sets["notes"] = (tree["notes"] + "\n" if tree["notes"] else "") + note
    con.execute("BEGIN")
    con.execute(
        "INSERT INTO tree_events (tree_id,ts,kind,status,condition,maturity,health,confidence,model,label,image,note,source)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tree_id, ts, kind, status, condition, maturity, health, confidence, model, label, image, note, source))
    con.execute(f"UPDATE trees SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?",
                (*sets.values(), tree_id))
    con.execute("COMMIT")
    return get_tree(con, tree_id)


if __name__ == "__main__":       # python -m backend.db  -> create + seed, print a summary
    c = connect()
    added = init_db(c)
    counts = c.execute("SELECT status, maturity, health, COUNT(*) FROM trees GROUP BY 1, 2, 3").fetchall()
    print(f"{config.DB_PATH}: {added} trees seeded" if added else f"{config.DB_PATH}: already seeded")
    for s, m, h, k in counts:
        print(f"  {s:10s} {m:11s} {h:13s} {k}")
