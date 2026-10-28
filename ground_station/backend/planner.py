"""Plan the next mission from the database (preview + QGroundControl export).

Picks the palms to confirm:
  1. every palm with status 'target' (flagged by the scout sweep or an operator);
  2. then 'unscouted' palms predicted ripe (ripeness.score >= PREDICT_MIN),
     best score first;
adding hover stops while the mission stays within the battery rule
(USABLE x BATT_WH). Confirmed palms go to the harvest crew and harvested ones were
just harvested, so neither is revisited. The route itself comes from
flight_software/route_planner.py (racetrack sweep from the dock, U-turn into
the stops, stops flowing back to the dock), the same planner the simulator flies.

Energy model, from the JSBSim runs (js_demo_v4: sweep + 4 stops = 13.1 Wh;
js_hover_ripe: ~1.2 Wh per hover stop):
  E = E_SWEEP + E_FIXED + E_STOP x stops
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone

from . import config, db, ripeness

sys.path.insert(0, str(config.REPO / "flight_software"))
import route_planner as rp  # noqa: E402  (pymavlink + stdlib only)

BATT_WH = 44.4
USABLE = 0.80               # land with >= 20% left
E_SWEEP = 7.3               # Wh, fixed-wing scout sweep of the 1 ha field
E_FIXED = 0.9               # Wh, back-transition, return and VTOL landing
E_STOP = 1.2                # Wh per confirm stop (hover + hop)


def max_stops() -> int:
    return max(0, math.floor((USABLE * BATT_WH - E_SWEEP - E_FIXED) / E_STOP))


def energy(stops: int) -> float:
    return E_SWEEP + (E_FIXED + E_STOP * stops if stops else 0.0)


def plan(con) -> dict:
    lay = db.layout(con)
    trees = db.list_trees(con)
    scores = ripeness.score_all(con)
    targets = sorted((t for t in trees if t["status"] == "target"),
                     key=lambda t: -(t["confidence"] or scores[t["id"]][0]))
    predicted = sorted((t for t in trees if t["status"] == "unscouted"
                        and scores[t["id"]][0] >= ripeness.PREDICT_MIN), key=lambda t: -scores[t["id"]][0])
    cap = max_stops()
    picks = (targets + predicted)[:cap]
    dropped = [t["id"] for t in (targets + predicted)[cap:]]
    pick_ids = {t["id"] for t in picks}
    rp_trees = [rp.Tree(t["id"], t["n"], t["e"], t["height"], t["condition"],
                        "target" if t["id"] in pick_ids else "unscouted") for t in trees]
    home = (lay["home"]["lat"], lay["home"]["lon"])
    items = rp.build_mission("hybrid", home, dict(lay, dock=dict(lay["dock"])), rp_trees)
    route, order, dist, prev = [], {}, 0.0, None
    for i, it in enumerate(items, start=1):
        if it.n is None:
            continue
        lat, lon = db.meters_to_latlon(it.n, it.e, *home)
        if prev:
            dist += math.hypot(it.n - prev[0], it.e - prev[1])
        prev = (it.n, it.e)
        route.append({"seq": i, "label": it.label, "cmd": it.wp.command, "lat": lat, "lon": lon,
                      "alt": it.wp.alt, "tree": it.tree})
        if it.tree:
            order[it.tree] = len(order) + 1
    stops = [{"tree": t["id"], "order": order.get(t["id"]), "kind": "target" if t["status"] == "target" else "predicted",
              "score": scores[t["id"]][0], "reason": scores[t["id"]][1], "lat": t["lat"], "lon": t["lon"]}
             for t in picks]
    stops.sort(key=lambda s: s["order"] or 999)
    e = energy(len(picks))
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stops": stops, "route": route, "dropped": dropped,
            "n_targets": sum(s["kind"] == "target" for s in stops), "n_predicted": sum(s["kind"] == "predicted" for s in stops),
            "distance_m": round(dist), "energy_wh": round(e, 1), "battery_pct": round(100 * e / BATT_WH),
            "budget_pct": round(100 * USABLE), "max_stops": cap, "_items": items, "_home": home}


def waypoints(p: dict) -> str:
    """QGroundControl WPL 110 text, same format as route_planner.write_plan."""
    home = p["_home"]
    lines = ["QGC WPL 110", f"0\t1\t0\t16\t0\t0\t0\t0\t{home[0]:.7f}\t{home[1]:.7f}\t0\t1"]
    for i, it in enumerate(p["_items"], start=1):
        w = it.wp
        frame = 2 if w.command == rp.MAV.MAV_CMD_DO_VTOL_TRANSITION else 3
        lines.append(f"{i}\t0\t{frame}\t{w.command}\t{w.param1:g}\t0\t0\t0\t{w.lat:.7f}\t{w.lon:.7f}\t{w.alt:g}\t1")
    return "\n".join(lines) + "\n"


def public(p: dict) -> dict:
    return {k: v for k, v in p.items() if not k.startswith("_")}
