#!/usr/bin/env python3
"""
schedule_sim.py -- a week of plantation operations, Monte-Carlo, for choosing
the operating policy (how often to scout, whether to stop at trees).

    python schedule_sim.py [--weeks 300] [--seed 1]

Flight costs come from the Gazebo/SITL runs in demo/runs/ (sim_runner.py):
  scout   fw_sweep run   -> time, energy, frames per palm (imaging coverage)
  confirm hover run      -> time and energy per inspected palm
  hover_all             -> the hover run's per-palm cost x 169 (stop at every tree)
so the schedule numbers trace back to flown simulations, not guesses.

World model (all assumptions at the top):
  * each healthy palm starts a ripe bunch with probability 1/RIPEN_DAYS per day
    (one bunch per ~month); a ripe palm stays ripe until harvested
  * ML detection on the scout frames: recall depends on frames of that palm
    (0 frames: not seen), plus a false-positive rate on non-ripe palms
  * a VTOL confirm stop (close, slow, several frames) is ~certain
  * harvest crew acts the day after a palm is reported (confirmed, or
    straight from the scout for the scout-only policy); a wrong report
    is a wasted climb
  * weather: some days are no-fly (wind over limit or rain)
Policies:
  hover_all        VTOL hop and hover over every palm daily (needs several sorties)
  scout_confirm    fixed-wing scout every morning + VTOL confirm of detections
  scout2_confirm   scout every second day + confirm
  scout_vote       daily scout; report palms with >= 2 agreeing frames
                   directly, VTOL-confirm only the 1-vote palms
  scout_v2_confirm daily scout; VTOL-confirm palms with >= 2 agreeing frames,
                   ignore 1-frame hits (tomorrow's scout looks again)
  scout_only       daily scout, report any detection without confirming
Also prints how detection quality depends on frames per palm (k), i.e. how
many images per tree are worth taking.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE / "demo"
RUNS = DEMO / "runs"

DAYS = 7
N_PALMS = 169
RIPEN_DAYS = 30            # one new bunch per palm per ~month
# ML on the scout frames, per frame (oblique 4-15 m, ~2 cm/px): a ripe bunch
# is visible in a frame with P_FRAME_TP; a non-ripe crown is flagged with
# P_FRAME_FP. A palm gets k frames (from the flown sweep's analysis.json).
P_FRAME_TP = 0.70
P_FRAME_FP = 0.04
CONFIRM_RECALL = 0.98
P_NOFLY = 0.12             # wind > 10 m/s or rain (monsoon-season average)
BATT_WH, USABLE = 44.4, 0.80
CHARGE_W = 40.0            # ~1C charge of the 3S 4000 pack
TURNAROUND_MIN = 5.0       # battery swap / checks between sorties


def load_costs(scout_run="fw_calm", hover_run="hover_ripe"):
    def summ(name):
        p = RUNS / name / "summary.json"
        return json.loads(p.read_text()) if p.exists() else None

    fw = summ(scout_run)
    hv = summ(hover_run)
    an = json.loads((RUNS / scout_run / "analysis.json").read_text()) if fw else None
    c = {
        "scout_s": fw["flight_s"] if fw else 245.0,
        "scout_wh": fw["energy_wh"] if fw else 6.5,
        "frames": an["per_tree_frames"] if an else None,
        "src_scout": f"demo/runs/{scout_run}" if fw else "default",
    }
    if hv and hv.get("flight_s"):
        n = hv.get("n_targets") or 29
        c.update(per_palm_s=hv["flight_s"] / n, per_palm_wh=hv["energy_wh"] / n, src_hover=f"demo/runs/{hover_run}")
    else:
        c.update(per_palm_s=11.0, per_palm_wh=0.55, src_hover="default (hover run missing)")
    return c


def sorties(wh):
    return max(1, math.ceil(wh / (BATT_WH * USABLE)))


def simulate(policy, costs, rng):
    frames = costs["frames"]
    ids = sorted(frames) if frames else [f"P{i:04d}" for i in range(N_PALMS)]
    nfr = {i: (frames or {}).get(i, 4) for i in ids}
    ripe_since = {i: (0 if rng.random() < 29 / 169 else None) for i in ids}  # ~start-of-week state
    reported = {}
    log = dict(flight_s=0.0, energy_wh=0.0, sorties=0, wasted_climbs=0, harvested=0, latency=[], nofly=0,
               days=[])
    pending_harvest = []
    for day in range(DAYS):
        # crew harvests yesterday's reports
        for i in pending_harvest:
            reported.pop(i, None)          # palm can be reported again when it re-ripens
            if ripe_since[i] is not None:
                log["harvested"] += 1
                log["latency"].append(day - ripe_since[i])
                ripe_since[i] = None
            else:
                log["wasted_climbs"] += 1
        pending_harvest = []
        for i in ids:      # new ripening
            if ripe_since[i] is None and rng.random() < 1 / RIPEN_DAYS:
                ripe_since[i] = day
        fly = rng.random() >= P_NOFLY
        dl = {"day": day + 1, "fly": fly, "flights": []}
        if not fly:
            log["nofly"] += 1
            log["days"].append(dl)
            continue
        found = []
        if policy == "hover_all":
            s, wh = costs["per_palm_s"] * len(ids), costs["per_palm_wh"] * len(ids)
            dl["flights"].append(("hover all", s, wh))
            found = [i for i in ids if ripe_since[i] is not None and rng.random() < CONFIRM_RECALL]
        else:
            scout_today = policy != "scout2_confirm" or day % 2 == 0
            if scout_today:
                dl["flights"].append(("scout", costs["scout_s"], costs["scout_wh"]))
                votes = {i: sum(rng.random() < (P_FRAME_TP if ripe_since[i] is not None else P_FRAME_FP)
                                for _ in range(nfr[i])) for i in ids if i not in reported}
                if policy == "scout_vote":          # >= 2 agreeing frames: report; 1: confirm
                    sure = [i for i, v in votes.items() if v >= 2]
                    det = [i for i, v in votes.items() if v == 1]
                elif policy == "scout_v2_confirm":  # >= 2 frames: confirm; 1: wait for tomorrow's scout
                    sure, det = [], [i for i, v in votes.items() if v >= 2]
                else:                               # any positive frame
                    sure, det = [], [i for i, v in votes.items() if v >= 1]
                if policy == "scout_only":
                    sure, det = det, []
                found = list(sure)
                if det:
                    s, wh = costs["per_palm_s"] * len(det), costs["per_palm_wh"] * len(det)
                    dl["flights"].append((f"confirm {len(det)}", s, wh))
                    found += [i for i in det if ripe_since[i] is not None and rng.random() < CONFIRM_RECALL]
        for name, s, wh in dl["flights"]:
            log["flight_s"] += s
            log["energy_wh"] += wh
            log["sorties"] += sorties(wh)
        for i in found:
            reported[i] = day
            pending_harvest.append(i)
        log["days"].append(dl)
    log["missed_ripe_end"] = sum(1 for i in ids if ripe_since[i] is not None)
    return log


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--scout-run", default="fw_calm")
    ap.add_argument("--hover-run", default="hover_ripe")
    a = ap.parse_args()
    costs = load_costs(a.scout_run, a.hover_run)
    rng = random.Random(a.seed)
    policies = ["hover_all", "scout_confirm", "scout2_confirm", "scout_vote", "scout_v2_confirm", "scout_only"]
    rows, sample = [], {}
    for pol in policies:
        runs = [simulate(pol, costs, rng) for _ in range(a.weeks)]
        lat = [x for r in runs for x in r["latency"]]
        busy_min = st.mean(r["flight_s"] / 60 + r["sorties"] * TURNAROUND_MIN
                           + r["energy_wh"] / CHARGE_W * 60 for r in runs)
        rows.append({
            "policy": pol,
            "flight_min_week": round(st.mean(r["flight_s"] for r in runs) / 60, 1),
            "energy_wh_week": round(st.mean(r["energy_wh"] for r in runs), 1),
            "sorties_week": round(st.mean(r["sorties"] for r in runs), 1),
            "max_sorties_day": max(sorties(f[2]) for r in runs for d in r["days"] for f in d["flights"]) if any(
                d["flights"] for r in runs for d in r["days"]) else 0,
            "busy_min_week_incl_charge": round(busy_min, 1),
            "harvested_week": round(st.mean(r["harvested"] for r in runs), 1),
            "latency_days_mean": round(st.mean(lat), 2) if lat else None,
            "wasted_climbs_week": round(st.mean(r["wasted_climbs"] for r in runs), 2),
            "ripe_unreported_end": round(st.mean(r["missed_ripe_end"] for r in runs), 1),
        })
        sample[pol] = runs[0]["days"]
    from math import comb
    sens = []
    for k in range(1, 11):
        rec = sum(comb(k, j) * P_FRAME_TP ** j * (1 - P_FRAME_TP) ** (k - j) for j in range(2, k + 1))
        fp = sum(comb(k, j) * P_FRAME_FP ** j * (1 - P_FRAME_FP) ** (k - j) for j in range(2, k + 1))
        sens.append({"frames": k, "recall_vote2": round(rec, 3), "false_pos_vote2": round(fp, 4),
                     "false_reports_per_169_palms": round(fp * 140, 2)})
    out = {"frames_sensitivity": sens, "costs": {k: v for k, v in costs.items() if k != "frames"}, "assumptions": {
        "ripen_days": RIPEN_DAYS, "p_frame_tp": P_FRAME_TP, "p_frame_fp": P_FRAME_FP, "p_nofly": P_NOFLY,
        "weeks": a.weeks}, "policies": rows, "sample_week": sample}
    (DEMO / "schedule_result.json").write_text(json.dumps(out, indent=1))
    hdr = list(rows[0])
    md = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    md += ["| " + " | ".join(str(r[h]) for h in hdr) + " |" for r in rows]
    print(json.dumps(out["costs"]))
    print("\n".join(md))
    print("\nframes per palm k -> 'vote >= 2' recall / false reports per scout (140 non-ripe palms)")
    for r in sens:
        print(f"  k={r['frames']:2d}  recall {r['recall_vote2']:.3f}  false reports {r['false_reports_per_169_palms']:.2f}")


if __name__ == "__main__":
    main()
