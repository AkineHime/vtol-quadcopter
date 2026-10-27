"""Decide when to photograph a palm: the drone is within the crown radius
(horizontally) of a palm in the current photo pattern that has no photo since
the pattern was set. The server then asks the dashboards for a frame; the
first dashboard with live video sends one back (see app.py)."""
from __future__ import annotations

import math
import time
import uuid

from . import db

RETRY_S = 5.0          # re-ask for the same tree at most this often while overhead
PENDING_S = 30.0       # a capture request expires after this


class Capture:
    def __init__(self, con, radius: float | None = None) -> None:
        self.con = con
        lay = db.layout(con)
        self.lat0, self.lon0 = lay["home"]["lat"], lay["home"]["lon"]
        self.grid = lay["grid"]
        self.radius = radius if radius is not None else lay.get("crown_radius_m", 4.0)
        self.trees: list[dict] = []
        self.pattern: dict = {}
        self.last_ask: dict[str, float] = {}
        self.pending: dict[str, tuple[str, float]] = {}      # capture id -> (tree id, time)
        self.refresh()

    def refresh(self) -> None:
        """Reload trees + pattern (call after anything that may change them)."""
        self.pattern = db.get_pattern(self.con)
        self.trees = db.list_trees(self.con)

    def todo(self, tree: dict) -> bool:
        if not db.in_pattern(tree, self.pattern["every"], self.grid):
            return False
        return not (tree["last_photo"] and tree["last_photo"] >= self.pattern["since"])

    def _to_ne(self, lat: float, lon: float) -> tuple[float, float]:
        return ((lat - self.lat0) * 111_320.0,
                (lon - self.lon0) * 111_320.0 * math.cos(math.radians(self.lat0)))

    def check(self, tel: dict) -> dict | None:
        """Given a telemetry message, return a capture request or None."""
        if not tel.get("connected") or tel.get("lat") is None:
            return None
        n, e = self._to_ne(tel["lat"], tel["lon"])
        best, best_d = None, self.radius
        for t in self.trees:
            d = math.hypot(t["n"] - n, t["e"] - e)
            if d <= best_d and self.todo(t):
                best, best_d = t, d
        if best is None:
            return None
        now = time.monotonic()
        if now - self.last_ask.get(best["id"], -1e9) < RETRY_S:
            return None
        self.last_ask[best["id"]] = now
        cid = uuid.uuid4().hex
        self.pending = {k: v for k, v in self.pending.items() if now - v[1] < PENDING_S}
        self.pending[cid] = (best["id"], now)
        return {"type": "capture", "tree_id": best["id"], "capture_id": cid}

    def claim(self, capture_id: str, tree_id: str) -> bool:
        """First dashboard to answer a capture request wins."""
        entry = self.pending.get(capture_id)
        if not entry or entry[0] != tree_id or time.monotonic() - entry[1] > PENDING_S:
            return False
        del self.pending[capture_id]
        return True
