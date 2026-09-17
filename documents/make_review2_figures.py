#!/usr/bin/env python3
"""
Regenerate the three Experiments-and-Results figures at presentation
resolution (2000+ px wide, large fonts) into documents/review2_figures/.

    python make_review2_figures.py     # run in WSL venv (has matplotlib)
"""
import csv
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "review2_figures"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "flight_software"))
import upload_mission as gcs  # noqa: E402

plt.rcParams.update({
    "font.size": 15, "axes.titlesize": 17, "axes.labelsize": 15,
    "legend.fontsize": 13, "figure.dpi": 200, "savefig.dpi": 200,
    "axes.grid": True, "grid.alpha": 0.3, "lines.linewidth": 2.0,
})
BLUE, RED, GREEN, AMBER = "#1f6feb", "#cf222e", "#2da44e", "#d29922"


def _read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def fig1_sitl_mission():
    rows = _read_csv(ROOT / "flight_software/captures/telemetry.csv")
    lat0 = float(rows[0]["lat"]); lon0 = float(rows[0]["lon"])
    sx = 111_320.0 * math.cos(math.radians(lat0))
    fx = [(float(r["lon"]) - lon0) * sx for r in rows]
    fy = [(float(r["lat"]) - lat0) * 111_320.0 for r in rows]
    t = [float(r["t"]) for r in rows]
    alt = [float(r["alt"]) for r in rows]
    asp = [float(r["asp"]) if r["asp"] else float("nan") for r in rows]

    wps = gcs.make_grid_mission(lat0, lon0, survey_alt=35.0,
                                box_n=210.0, box_e=140.0, row_spacing=70.0)
    wx = [(w.lon - lon0) * sx for w in wps]
    wy = [(w.lat - lat0) * 111_320.0 for w in wps]

    fig, ax = plt.subplots(1, 2, figsize=(15, 6))
    ax[0].plot(wx, wy, "o--", ms=7, color=AMBER, label="planned survey grid")
    ax[0].plot(fx, fy, "-", color=BLUE, label="flown track")
    ax[0].set_aspect("equal"); ax[0].set_xlabel("East (m)")
    ax[0].set_ylabel("North (m)")
    ax[0].set_title("Autonomous survey grid — planned vs flown")
    ax[0].legend(loc="lower right")

    ax[1].plot(t, alt, color=GREEN, label="altitude (m)")
    ax[1].plot(t, asp, color=RED, label="airspeed (m/s)")
    ax[1].set_xlabel("mission time (s)")
    ax[1].set_title("VTOL takeoff → transition → cruise → VTOL land")
    ax[1].legend(loc="upper right")
    ax[1].annotate("VTOL\ntakeoff", (2, 20), color=GREEN, fontsize=12)
    ax[1].annotate("transition", (7.5, 3), color=RED, fontsize=12)
    ax[1].annotate("VTOL land", (48, 6), color=GREEN, fontsize=12)

    fig.suptitle("ArduPilot SITL — full mission, all flight-phase checks PASS",
                 fontsize=18, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "1_sitl_mission.png", bbox_inches="tight")
    print("wrote 1_sitl_mission.png")


def fig2_aero_coeffs():
    d = json.load(open(ROOT / "aero/coefficients.json"))
    L = d["longitudinal"]; g = d["geometry"]
    a = L["alpha_deg"]
    a_cruise = d["trim"]["alpha_trim_deg"]

    fig, ax = plt.subplots(1, 3, figsize=(16, 5))
    ax[0].plot(a, L["CL"], "o-", color=BLUE)
    ax[0].set_xlabel("angle of attack (deg)"); ax[0].set_title("$C_L$")
    ax[1].plot(L["CL"], L["CD"], "o-", color=RED)
    ax[1].set_xlabel("$C_L$"); ax[1].set_title("drag polar  $C_D$")
    ax[2].plot(a, L["Cm"], "o-", color=GREEN)
    ax[2].axhline(0, color="k", lw=0.8)
    ax[2].set_xlabel("angle of attack (deg)")
    ax[2].set_title("$C_m$  (slope $<0$ ⇒ stable)")
    for x in (ax[0], ax[2]):
        x.axvline(a_cruise, color=AMBER, ls="--", lw=1.5)
    ax[0].annotate(f"cruise\nα≈{a_cruise:.1f}°", (a_cruise + 0.5, 0.0),
                   color=AMBER, fontsize=12)

    fig.suptitle("Real 3-D aerodynamics — SD7037 wing / NACA 0009 tail "
                 f"(NeuralFoil + AeroSandbox, Re≈{g['Re_cruise']/1e3:.0f}k)",
                 fontsize=17, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "2_aero_coefficients.png", bbox_inches="tight")
    print("wrote 2_aero_coefficients.png")


def fig3_bridge_porpoising():
    rows = [r for r in _read_csv(
        ROOT / "flight_software/jsbsim/captures/bridge_mission_telemetry.csv")
        if r["alt"]]
    t = [float(r["t"]) for r in rows]

    def col(k):
        return [float(r[k]) if r[k] else float("nan") for r in rows]

    fig, ax = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    ax[0].plot(t, col("alt"), color=GREEN)
    ax[0].set_ylabel("altitude AGL (m)")
    ax[0].set_title("Full mission on the REAL aerodynamics (ArduPilot ↔ JSBSim bridge)")
    ax[1].plot(t, col("asp"), color=RED)
    ax[1].axhline(12, ls="--", color="grey", label="12 m/s target")
    ax[1].set_ylabel("airspeed (m/s)"); ax[1].legend(loc="upper right")
    ax[2].plot(t, col("roll"), color=BLUE, label="roll")
    ax[2].plot(t, col("pitch"), color=AMBER, label="pitch")
    ax[2].set_ylabel("attitude (deg)"); ax[2].set_xlabel("mission time (s)")
    ax[2].legend(loc="upper right")

    fig.suptitle("Survey-phase instability — diagnosed, fix in progress",
                 fontsize=18, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "3_bridge_survey_instability.png", bbox_inches="tight")
    print("wrote 3_bridge_survey_instability.png")


if __name__ == "__main__":
    fig1_sitl_mission()
    fig2_aero_coeffs()
    fig3_bridge_porpoising()
    print(f"\nfigures in {OUT}")
