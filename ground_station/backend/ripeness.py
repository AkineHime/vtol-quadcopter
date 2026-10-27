"""Which palms probably carry tender nuts right now -- bunch-cycle rules.

A coconut palm opens a new bunch about every month, and a bunch is tender (the
harvest target, 7-8 months after opening) for about a month, so a productive
palm has a tender bunch roughly every BUNCH_INTERVAL_D days. The score combines
the latest evidence for each palm, newest first:

  status confirmed                -> 1.0  (a confirm stop already saw tender nuts)
  maturity sighting after the     -> tender: its confidence, fading after the
  last harvest (ML label, colour     tender window back to the cycle; mature or
  card, a logged visit, or the       over-mature: a bunch was missed and a
  survey's 'ripe')                   younger one is likely tender now; young:
                                     tender in a few months, not now
  harvest (status harvested)      -> due again one bunch interval later (logistic)
  nothing                         -> UNKNOWN_P
then x HEALTH_FACTOR for palms with frond damage or pests (stressed palms bear less).

These are rules, not a fitted model: there is no per-palm history yet. Every
constant is named here so it can be fitted later from the tree_events table
(e.g. BUNCH_INTERVAL_D and the decay from the harvest dates).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .db import LABEL_MATURITY

BUNCH_INTERVAL_D = 30.0     # a new bunch opens about monthly
TENDER_WINDOW_D = 30.0      # a bunch stays tender (7-8 months) about a month
DUE_SPREAD_D = 5.0          # how sharply a harvested palm becomes "due" again
UNKNOWN_P = 0.35            # never observed
STAGE_P = {"mature": 0.55, "over-mature": 0.45, "young": 0.2}   # tender: the sighting's confidence
SEED_TENDER_CONF = 0.7      # the farm survey's "ripe" counts as a tender sighting
VISIT_CONF = 0.9            # a person logging "tender" on a visit
HEALTH_FACTOR = 0.7
PREDICT_MIN = 0.5           # score at or above which a palm is "predicted ripe"


def _days(a: str, b: datetime) -> float:
    t = datetime.fromisoformat(a)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return max(0.0, (b - t).total_seconds() / 86400.0)


def _due(days_since_harvest: float) -> float:
    return 1.0 / (1.0 + math.exp(-(days_since_harvest - BUNCH_INTERVAL_D) / DUE_SPREAD_D))


def _sighting(e: dict) -> tuple[str, float, str] | None:
    """(stage, confidence, source) if the event says what maturity the palm is at."""
    stage = LABEL_MATURITY.get(e.get("label") or "") or e.get("maturity")
    if not stage and e["kind"] == "seed" and e.get("condition") in ("ripe", "ripe+frond"):
        stage = "tender"                                     # survey 'ripe' = the harvest target
    if not stage or stage == "unknown":
        return None
    if e["kind"] == "seed":
        return stage, SEED_TENDER_CONF, "survey"
    if e["kind"] == "detection":
        return stage, e.get("confidence") or SEED_TENDER_CONF, (e.get("model") or "detection")
    return stage, e.get("confidence") or VISIT_CONF, "visit"


def score(tree: dict, events: list[dict], now: datetime | None = None) -> tuple[float, str]:
    """(probability 0..1 that the palm has tender nuts now, short reason). `events`
    newest first, as db.history returns them."""
    now = now or datetime.now(timezone.utc)
    if tree["status"] == "confirmed":
        return 1.0, "confirmed at a stop"
    harvest = next((e for e in events if e["kind"] == "status" and e["status"] in ("harvested", "cleared")), None)
    seen = next(((e, s) for e in events if (not harvest or e["ts"] > harvest["ts"])
                 for s in [_sighting(e)] if s), None)
    if seen:
        e, (stage, conf, src) = seen
        age = _days(e["ts"], now)
        when = "survey" if src == "survey" else f"{src}, {age:.0f} d ago"
        if stage == "tender":
            p = conf if age <= TENDER_WINDOW_D else max(UNKNOWN_P, conf * math.exp(-(age - TENDER_WINDOW_D) / TENDER_WINDOW_D))
            why = f"tender ({when}, {conf:.0%})"
        elif stage == "young":
            p, why = STAGE_P["young"], f"young bunch ({when}): tender later"
        else:
            p, why = STAGE_P[stage], f"{stage} ({when}): a younger bunch is likely tender"
    elif harvest:
        d = _days(harvest["ts"], now)
        p, why = 0.85 * _due(d), f"harvested {d:.0f} d ago" + (": next bunch due" if d >= BUNCH_INTERVAL_D else "")
    else:
        p, why = UNKNOWN_P, "no observations yet"
    if tree.get("health", "healthy") != "healthy":
        p, why = p * HEALTH_FACTOR, why + f"; {tree['health'].replace('-', ' ')}"
    return round(min(1.0, p), 3), why


def score_all(con, now: datetime | None = None) -> dict[str, tuple[float, str]]:
    """Scores for every palm, from one pass over the trees and their events."""
    trees = {r["id"]: dict(r) for r in con.execute("SELECT * FROM trees")}
    evs: dict[str, list[dict]] = {k: [] for k in trees}
    for r in con.execute("SELECT * FROM tree_events ORDER BY ts DESC, id DESC"):
        evs[r["tree_id"]].append(dict(r))
    return {k: score(t, evs[k], now) for k, t in trees.items()}
