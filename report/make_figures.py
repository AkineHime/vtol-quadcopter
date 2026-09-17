#!/usr/bin/env python3
"""Generate the four report figures: Gantt, system architecture, data-flow
diagram, use-case diagram. Output to report/figs/ at 200 dpi."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from pathlib import Path

OUT = Path(__file__).resolve().parent / "figs"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})

INK = "#1f2328"
BLUE = "#1f6feb"
GREEN = "#2da44e"
AMBER = "#d29922"
GREY = "#6e7781"
LGREY = "#eef1f4"


# ---------------------------------------------------------------- 1. Gantt
def gantt():
    #  (label, start_week, duration_weeks, colour)   1 unit = 1 week
    tasks = [
        ("Literature review & scope refinement",            0.0, 2.0, GREY),
        ("Airframe / tail / airfoil decision",              1.0, 1.5, GREY),
        ("ArduPilot SITL setup & build (WSL2)",             2.0, 1.5, BLUE),
        ("QuadPlane parameter configuration",               3.0, 1.0, BLUE),
        ("pymavlink mission-upload & telemetry script",     3.5, 1.0, BLUE),
        ("SITL mission validation (built-in physics)",      4.0, 1.0, BLUE),
        ("2-D / 3-D aerodynamic analysis (NeuralFoil)",     3.5, 1.5, GREEN),
        ("JSBSim aircraft model + power-off verification",  4.5, 1.0, GREEN),
        ("Vertical-fin re-size, trim & control study",      4.5, 1.0, GREEN),
        ("ArduPilot ↔ JSBSim bridge integration",      5.0, 1.5, GREEN),
        ("Detection dataset assembly & pipeline skeleton",  5.0, 1.5, AMBER),
        ("Route planner + per-tree SQLite data store",      5.5, 1.5, AMBER),
        ("Report & Review-2 presentation",                  6.0, 1.5, INK),
        ("YOLO disease / pest detection model training",    7.5, 2.0, LGREY),
        ("Bridge control tuning (thrust table + AUTOTUNE)", 7.5, 2.0, LGREY),
        ("Dashboard (WebSocket + Leaflet)",                 8.0, 1.5, LGREY),
    ]
    fig, ax = plt.subplots(figsize=(11, 6.4))
    n = len(tasks)
    for i, (name, start, dur, col) in enumerate(tasks):
        y = n - i
        pending = col == LGREY
        ax.barh(y, dur, left=start, height=0.58, color=col,
                edgecolor=INK, linewidth=0.6,
                hatch="////" if pending else None,
                alpha=0.5 if pending else 0.92)
        ax.text(-0.2, y, name, ha="right", va="center", fontsize=9.5)
    ax.axvline(7.5, color="#cf222e", lw=1.7, ls="--")
    ax.text(7.5, n + 0.85, "  Review 2", color="#cf222e", fontsize=10,
            fontweight="bold", ha="left")
    ax.axvspan(7.5, 10.0, color="#cf222e", alpha=0.04)
    weeks = [f"Wk {w}" for w in range(1, 11)]
    ax.set_xticks(range(len(weeks)))
    ax.set_xticklabels(weeks, fontsize=9)
    ax.set_xlim(-7.3, 10.2)
    ax.set_ylim(0.2, n + 1.4)
    ax.set_yticks([])
    ax.set_xlabel("Project-I timeline (relative weeks)")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color="#d0d7de", lw=0.5)
    handles = [
        mpatches.Patch(color=GREY, label="Design / literature"),
        mpatches.Patch(color=BLUE, label="Flight software & SITL"),
        mpatches.Patch(color=GREEN, label="Aerodynamics & simulation"),
        mpatches.Patch(color=AMBER, label="Detection data & route logic"),
        mpatches.Patch(facecolor=LGREY, edgecolor=INK, hatch="////",
                       alpha=0.5, label="Planned (post Review 2)"),
    ]
    ax.legend(handles=handles, loc="upper center", fontsize=9,
              framealpha=0.96, ncol=5, bbox_to_anchor=(0.5, -0.13))
    fig.tight_layout()
    fig.savefig(OUT / "gantt.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("gantt.png")


def _box(ax, xy, w, h, text, fc, ec=INK, fs=10, tc=INK, bold=False):
    b = FancyBboxPatch((xy[0], xy[1]), w, h,
                       boxstyle="round,pad=0.02,rounding_size=0.06",
                       fc=fc, ec=ec, lw=1.1)
    ax.add_patch(b)
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, fontweight="bold" if bold else "normal",
            wrap=True)


def _arrow(ax, p1, p2, text="", color=INK, style="-|>", rad=0.0, fs=8.5,
           ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=14,
                                 color=color, lw=1.3, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}"))
    if text:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my + 0.12, text, ha="center", va="center", fontsize=fs,
                color=color, backgroundcolor="white")


# ------------------------------------------------- 2. system architecture
def architecture():
    fig, ax = plt.subplots(figsize=(11, 7.4))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # layer bands
    for y0, y1, c, lab in [(6.9, 9.7, "#eaf2ff", "AERIAL LAYER"),
                           (3.9, 6.7, "#eafaf0", "SENSING LAYER"),
                           (0.3, 3.7, "#fff6e6", "GROUND LAYER (laptop)")]:
        ax.add_patch(mpatches.Rectangle((0.2, y0), 11.6, y1 - y0, fc=c,
                     ec="none"))
        ax.text(0.45, y1 - 0.28, lab, fontsize=9.5, color=GREY,
                fontweight="bold")

    _box(ax, (1.0, 7.7), 4.6, 1.5,
         "Quadplane airframe\n1.3 m wing, 4 lift + 1 forward motor, 2 elevons",
         "#dbe9ff", bold=False)
    _box(ax, (6.4, 7.7), 4.6, 1.5,
         "ArduPilot QuadPlane FC\n(Brahma F4)  — executes MAVLink\nmissions autonomously",
         "#dbe9ff")

    _box(ax, (0.8, 4.4), 3.3, 1.6,
         "RGB camera\n(ESP32-CAM class)\nrecords onboard", "#d7f2e1")
    _box(ax, (4.5, 4.4), 3.0, 1.6,
         "VL53L1X\nTime-of-Flight\naltitude / ranging", "#d7f2e1")
    _box(ax, (8.0, 4.4), 3.2, 1.6,
         "Onboard storage\nflight imagery +\ntelemetry log", "#d7f2e1")

    _box(ax, (0.7, 2.0), 2.7, 1.4,
         "YOLO detection\n(ripeness +\nfrond health)", "#ffe9c2")
    _box(ax, (3.8, 2.0), 2.5, 1.4, "Per-tree data\nstore (SQLite)", "#ffe9c2")
    _box(ax, (6.7, 2.0), 2.4, 1.4,
         "Route planner\n(dynamic\npruning)", "#ffe9c2")
    _box(ax, (9.5, 2.0), 2.2, 1.4,
         "Ground-station\nlink\n(pymavlink)", "#ffe9c2")
    _box(ax, (3.5, 0.5), 4.8, 1.1,
         "Dashboard — Leaflet map, battery, mission time, detections",
         "#ffe9c2")

    _arrow(ax, (5.6, 8.45), (6.4, 8.45), "servo / PWM")
    _arrow(ax, (6.4, 8.0), (5.6, 8.0), "IMU / GPS state", rad=0.0)
    _arrow(ax, (3.3, 7.7), (2.6, 6.0), "capture cmd")
    _arrow(ax, (8.7, 7.7), (9.6, 6.0), "telemetry")
    _arrow(ax, (2.4, 4.4), (2.2, 3.4), "post-flight")
    _arrow(ax, (9.6, 4.4), (10.5, 3.4), "")
    _arrow(ax, (3.4, 2.7), (3.8, 2.7), "status")
    _arrow(ax, (6.3, 2.7), (6.7, 2.7), "active list")
    _arrow(ax, (9.1, 2.7), (9.5, 2.7), "mission")
    _arrow(ax, (10.6, 2.0), (10.6, 3.9), "upload next\nmission", color=BLUE,
           rad=-0.25)
    _arrow(ax, (5.9, 2.0), (5.9, 1.6), "")

    ax.set_title("Fig. 2.  Three-layer system architecture",
                 fontsize=12, fontweight="bold", loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "architecture.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("architecture.png")


# ------------------------------------------------------- 3. data-flow diagram
def dfd():
    fig, ax = plt.subplots(figsize=(11, 6.6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 8)
    ax.axis("off")

    def ext(xy, w, h, t):
        ax.add_patch(mpatches.Rectangle(xy, w, h, fc="#eef1f4", ec=INK,
                                        lw=1.1))
        ax.text(xy[0] + w / 2, xy[1] + h / 2, t, ha="center", va="center",
                fontsize=9.5)

    def proc(xy, r, t):
        ax.add_patch(mpatches.Circle(xy, r, fc="#dbe9ff", ec=INK, lw=1.1))
        ax.text(xy[0], xy[1], t, ha="center", va="center", fontsize=9)

    def store(xy, w, t):
        ax.add_patch(mpatches.Rectangle(xy, w, 0.7, fc="#ffe9c2", ec=INK,
                                        lw=1.1))
        ax.text(xy[0] + w / 2, xy[1] + 0.35, t, ha="center", va="center",
                fontsize=9)

    ext((0.3, 5.6), 2.2, 1.2, "Operator")
    ext((0.3, 1.0), 2.2, 1.2, "Coconut\nplantation\n(environment)")
    ext((10.5, 5.6), 2.2, 1.2, "ArduPilot\nflight\ncontroller")

    proc((4.2, 6.2), 0.95, "1.0\nPlan /\nprune route")
    proc((4.2, 3.6), 0.95, "2.0\nCapture\nimagery")
    proc((7.2, 3.6), 0.95, "3.0\nRipeness /\nfrond-health\ndetection")
    proc((7.2, 6.2), 0.95, "4.0\nUpdate tree\nstatus")
    proc((10.3, 3.0), 0.9, "5.0\nRender\ndashboard")

    store((3.2, 0.6), 2.2, "D1  Per-tree status (SQLite)")
    store((6.2, 0.6), 2.6, "D2  Flight imagery store")

    _arrow(ax, (2.5, 6.2), (3.25, 6.2), "survey area")
    _arrow(ax, (5.15, 6.2), (10.5, 6.2), "waypoint mission")
    _arrow(ax, (10.5, 6.0), (5.15, 3.9), "position / trigger", rad=0.15)
    _arrow(ax, (2.5, 1.5), (3.9, 2.75), "palm imagery")
    _arrow(ax, (5.15, 3.6), (6.25, 3.6), "images")
    _arrow(ax, (4.2, 2.65), (7.0, 1.3), "raw frames", rad=-0.1)
    _arrow(ax, (7.2, 2.65), (7.2, 1.3), "")
    _arrow(ax, (7.2, 4.55), (7.2, 5.25), "detections")
    _arrow(ax, (6.5, 0.95), (5.4, 0.95), "")
    _arrow(ax, (6.5, 6.2), (5.2, 1.0), "confidence,\ncleared flag", rad=0.2)
    _arrow(ax, (4.5, 0.95), (4.0, 5.4), "active waypoints", rad=-0.3,
           color=BLUE)
    _arrow(ax, (8.0, 0.95), (7.0, 3.0), "", rad=0.1)
    _arrow(ax, (8.1, 6.2), (9.6, 3.5), "status", rad=-0.1)
    _arrow(ax, (10.3, 3.9), (10.3, 5.6), "map / KPIs")

    ax.set_title("Fig. 3.  Level-1 Data Flow Diagram", fontsize=12,
                 fontweight="bold", loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "dfd.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("dfd.png")


# --------------------------------------------------------- 4. use-case diagram
def usecase():
    fig, ax = plt.subplots(figsize=(10.5, 7.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 11)
    ax.axis("off")

    # system boundary
    ax.add_patch(mpatches.FancyBboxPatch(
        (3.0, 0.6), 6.0, 9.8, boxstyle="round,pad=0.1,rounding_size=0.1",
        fc="#fbfcfd", ec=GREY, lw=1.2))
    ax.text(6.0, 10.0, "Coconut-surveillance quadplane system", ha="center",
            fontsize=10.5, color=GREY, fontweight="bold")

    def actor(x, y, label):
        ax.plot(x, y + 0.35, "o", ms=9, color=INK)
        ax.plot([x, x], [y + 0.28, y - 0.15], color=INK, lw=1.6)
        ax.plot([x - 0.28, x + 0.28], [y + 0.08, y + 0.08], color=INK, lw=1.6)
        ax.plot([x, x - 0.22], [y - 0.15, y - 0.5], color=INK, lw=1.6)
        ax.plot([x, x + 0.22], [y - 0.15, y - 0.5], color=INK, lw=1.6)
        ax.text(x, y - 0.9, label, ha="center", fontsize=10, fontweight="bold")

    def uc(x, y, t):
        ax.add_patch(mpatches.Ellipse((x, y), 3.5, 1.0, fc="#dbe9ff",
                                      ec=INK, lw=1.0))
        ax.text(x, y, t, ha="center", va="center", fontsize=9)
        return (x, y)

    actor(1.2, 6.0, "Operator")
    actor(10.8, 6.0, "ArduPilot\nflight controller")

    u1 = uc(6.0, 9.0, "Define survey area")
    u2 = uc(6.0, 7.7, "Generate / prune route")
    u3 = uc(6.0, 6.4, "Upload mission")
    u4 = uc(6.0, 5.1, "Execute autonomous flight")
    u5 = uc(6.0, 3.8, "Capture palm imagery")
    u6 = uc(6.0, 2.5, "Detect ripeness & frond health")
    u7 = uc(6.0, 1.3, "Review dashboard & tree status")

    for u in (u1, u2, u3, u7):
        ax.plot([1.7, u[0] - 1.75], [6.0, u[1]], color=INK, lw=1.0)
    for u in (u4, u5):
        ax.plot([10.3, u[0] + 1.75], [6.0, u[1]], color=INK, lw=1.0)

    # includes
    _arrow(ax, (6.0, 7.2), (6.0, 6.9), "", color=GREY, style="-|>")
    ax.text(7.9, 7.05, "«include»", fontsize=8, color=GREY)
    _arrow(ax, (6.0, 4.6), (6.0, 4.3), "", color=GREY)
    ax.text(7.9, 4.45, "«include»", fontsize=8, color=GREY)
    _arrow(ax, (6.0, 3.3), (6.0, 3.0), "", color=GREY)
    ax.text(7.9, 3.15, "«include»", fontsize=8, color=GREY)
    _arrow(ax, (5.0, 2.1), (5.0, 1.75), "", color=GREY)
    ax.text(3.4, 1.95, "«extend»", fontsize=8, color=GREY)

    ax.set_title("Fig. 4.  Use-case diagram", fontsize=12, fontweight="bold",
                 loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "usecase.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("usecase.png")


if __name__ == "__main__":
    gantt()
    architecture()
    dfd()
    usecase()
    print("done ->", OUT)
