#!/usr/bin/env python3
"""
Schematic patent-drawing generator for the coconut-surveillance quadplane.

NOT a manufacturing CAD model. This is a proportionally-representative
wireframe (mm) built from the real, fixed dimensions where they exist
(wing span/chord/taper, twin-fin area) and reasonable schematic placement
for parts that have never been engineered in detail yet (pod, booms, motor
mounts, tail size/arm). Those are flagged in OUTPUT and must be confirmed /
refined before a final filing.

Every part is stored as a 3D point cloud. Each of the 7 standard patent
views (isometric + top + bottom + front + rear + left + right) is produced
by the SAME projector, so all views are guaranteed consistent with one
underlying model -- which is what a patent examiner expects across figures.

Occlusion is approximate: each part's silhouette is its convex hull in the
current view, filled opaque white, drawn back-to-front by a per-view
"closeness to viewer" key. Good enough for a schematic/preview set; a true
CAD-derived hidden-line render would refine this for final filing.

    uv run --with matplotlib --with numpy python make_patent_views.py
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from scipy.spatial import ConvexHull
from pathlib import Path

OUT = Path(__file__).resolve().parent
OUT.mkdir(exist_ok=True)

# ===========================================================================
# 1. GEOMETRY  (all dimensions in mm; X = aft from nose, Y = right span,
#    Z = up).  REAL where noted; SCHEMATIC (placeholder, not yet engineered)
#    otherwise -- see REAL_DIMS / SCHEMATIC_DIMS printed at the bottom.
# ===========================================================================

def ring(cx, r, x, n=8, squash=1.0):
    """n points around a circle of radius r in the Y-Z plane at station x."""
    return [(x, r * np.cos(a), squash * r * np.sin(a))
            for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]


def disc(center, radius, axis, n=16):
    """Circle of n points, normal to `axis` ('x' or 'z'), centred at 3D
    `center`. Used for propellers -- projects as a true circle face-on and
    collapses to a line edge-on, automatically, via the hull projector."""
    cx, cy, cz = center
    pts = []
    for a in np.linspace(0, 2 * np.pi, n, endpoint=False):
        if axis == "x":
            pts.append((cx, cy + radius * np.cos(a), cz + radius * np.sin(a)))
        else:  # 'z'
            pts.append((cx + radius * np.cos(a), cy + radius * np.sin(a), cz))
    return pts


PARTS = {}   # name -> {"kind": "hull"/"line", "pts": [...], "num": int/None}

# ---- 100  fuselage pod (SCHEMATIC: ~46 cm pod, per the spec's 40-50 cm) --
pod_pts = [(20, 0, 0)]                          # nose tip
pod_pts += ring(90, 40, 60)
pod_pts += ring(90, 45, 220)
pod_pts += ring(90, 42, 400)
pod_pts += [(460, 0, 0)]                        # tail tip
PARTS["pod"] = {"kind": "hull", "pts": pod_pts, "num": 100}

# ---- 110  main wing (REAL: 1.3 m span, 288/173 mm root/tip chord, ------
#           0.30 m^2 area, unswept LE -- from aero/RESULTS.md) -----------
wing_top = [(250, 0, 55), (538, 0, 55),
            (250, 650, 55), (423, 650, 55),
            (250, -650, 55), (423, -650, 55)]
wing_bot = [(x, y, z - 15) for (x, y, z) in wing_top]
PARTS["wing"] = {"kind": "hull", "pts": wing_top + wing_bot, "num": 110}

# ---- 112  elevons (REAL: outer ~40% span, full-span-elevon aircraft; ---
#           hinge at 28% local chord -- from aero/control_authority.py) -
def _chord(y):
    return 288 - (288 - 173) * (abs(y) / 650)


def _elevon_pts(sign):
    y0, y1 = 250 * sign, 650 * sign
    h0 = 250 + _chord(y0) - 0.28 * _chord(y0)
    h1 = 250 + _chord(y1) - 0.28 * _chord(y1)
    te0 = 250 + _chord(y0)
    te1 = 250 + _chord(y1)
    return [(h0, y0, 55), (te0, y0, 55), (h1, y1, 55), (te1, y1, 55)]


PARTS["elevon_R"] = {"kind": "hull", "pts": _elevon_pts(1), "num": 112}
PARTS["elevon_L"] = {"kind": "hull", "pts": _elevon_pts(-1), "num": 112}

# ---- 120  horizontal tail (SCHEMATIC size -- real target is V_H~0.45; --
#           exact span/chord not yet finalised, shown representatively) -
tail_top = [(1080, 0, 40), (1210, 0, 40),
            (1080, 300, 40), (1170, 300, 40),
            (1080, -300, 40), (1170, -300, 40)]
tail_bot = [(x, y, z - 10) for (x, y, z) in tail_top]
PARTS["tail"] = {"kind": "hull", "pts": tail_top + tail_bot, "num": 120}

# ---- 130  twin vertical fins (REAL: 170 cm^2 each, from RESULTS.md ------
#           fin-sizing table -- root/tip chord chosen to match that area) -
def _fin_pts(y):
    base = [(1080, y, -40), (1220, y, -40),
            (1120, y, 110), (1200, y, 110)]
    return [(x, y + (5 if y > 0 else -5), z) for (x, _, z) in base] + \
           [(x, y - (5 if y > 0 else -5), z) for (x, _, z) in base]


PARTS["fin_R"] = {"kind": "hull", "pts": _fin_pts(300), "num": 130}
PARTS["fin_L"] = {"kind": "hull", "pts": _fin_pts(-300), "num": 130}

# ---- 140  twin tail booms (SCHEMATIC placement, connecting wing to tail)
PARTS["boom_R"] = {"kind": "line",
                    "pts": [(450, 300, 30), (1080, 300, 0)], "num": 140}
PARTS["boom_L"] = {"kind": "line",
                    "pts": [(450, -300, 30), (1080, -300, 0)], "num": 140}

# ---- 150  lift rotors x4, quad-X (SCHEMATIC mount points; REAL prop -----
#           diameter 10x4.5in = 254mm, from vtol_project_summary.md) ------
LIFT = {"FL": (300, -300, 140), "FR": (300, 300, 140),
        "RL": (1000, -300, 90), "RR": (1000, 300, 90)}
for k, c in LIFT.items():
    PARTS[f"motor_{k}"] = {"kind": "hull", "pts": disc(c, 127, "z"), "num": 150}
    base_z = 55 if k[0] == "F" else 0
    PARTS[f"pylon_{k}"] = {"kind": "line",
                           "pts": [(c[0], c[1], base_z), c], "num": None}

# ---- 160  forward propulsion unit (REAL prop diameter 254mm; nose- -----
#           mounted tractor layout per vtol_project_summary.md) ----------
PARTS["fwd_motor"] = {"kind": "hull", "pts": disc((0, 0, 0), 127, "x"),
                      "num": 160}

# ---- 170 / 180  RGB camera + ToF ranging sensor (REAL parts, SCHEMATIC -
#           underside placement -- VL53L1X + ESP32-CAM class, per specs) -
PARTS["camera"] = {"kind": "hull", "pts": disc((200, 0, -45), 15, "x"),
                   "num": 170}
PARTS["tof"] = {"kind": "hull", "pts": disc((320, 0, -45), 10, "x"),
                "num": 180}

LABEL_TEXT = {
    100: "100  fuselage pod",
    110: "110  main wing",
    112: "112  elevon (pitch+roll control surface)",
    120: "120  horizontal tail",
    130: "130  vertical fin (twin)",
    140: "140  tail boom (twin)",
    150: "150  lift rotor (quad-X, x4)",
    160: "160  forward propulsion unit",
    170: "170  RGB camera",
    180: "180  time-of-flight ranging sensor",
}

ANCHOR = {  # representative 3D point used for each numeral's leader line
    100: (100, 0, 40), 110: (300, 480, 55), 112: (420, 560, 55),
    120: (1140, 150, 40), 130: (1150, 300, 30), 140: (700, 300, 15),
    150: (300, 300, 140), 160: (0, 0, 60), 170: (200, 0, -45),
    180: (320, 0, -45),
}

# ===========================================================================
# 2. VIEWS
# ===========================================================================

def rot(pts, deg_z, deg_x):
    a, b = np.radians(deg_z), np.radians(deg_x)
    Rz = np.array([[np.cos(a), -np.sin(a), 0],
                   [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)],
                   [0, np.sin(b), np.cos(b)]])
    return (np.array(pts) @ Rz.T) @ Rx.T


VIEWS = {
    # name: (project(pts)->(u,v) , closeness(pts)-> scalar, label_offset)
    "FIG1_isometric": dict(
        proj=lambda p: (rot(p, 20, 60)[:, 0], rot(p, 20, 60)[:, 1]),
        close=lambda p: rot(p, 20, 60)[:, 2].mean(),
        flip_v=False),
    "FIG2_top": dict(
        proj=lambda p: (np.array(p)[:, 1], 1250 - np.array(p)[:, 0]),
        close=lambda p: np.array(p)[:, 2].mean(), flip_v=False),
    "FIG3_bottom": dict(
        proj=lambda p: (-np.array(p)[:, 1], 1250 - np.array(p)[:, 0]),
        close=lambda p: -np.array(p)[:, 2].mean(), flip_v=False),
    "FIG4_front": dict(
        proj=lambda p: (-np.array(p)[:, 1], np.array(p)[:, 2]),
        close=lambda p: -np.array(p)[:, 0].mean(), flip_v=False),
    "FIG5_rear": dict(
        proj=lambda p: (np.array(p)[:, 1], np.array(p)[:, 2]),
        close=lambda p: np.array(p)[:, 0].mean(), flip_v=False),
    "FIG6_left": dict(
        proj=lambda p: (np.array(p)[:, 0], np.array(p)[:, 2]),
        close=lambda p: -np.array(p)[:, 1].mean(), flip_v=False),
    "FIG7_right": dict(
        proj=lambda p: (1250 - np.array(p)[:, 0], np.array(p)[:, 2]),
        close=lambda p: np.array(p)[:, 1].mean(), flip_v=False),
}

FIG_TITLE = {
    "FIG1_isometric": "FIG. 1 — Perspective view",
    "FIG2_top": "FIG. 2 — Top view",
    "FIG3_bottom": "FIG. 3 — Bottom view",
    "FIG4_front": "FIG. 4 — Front view",
    "FIG5_rear": "FIG. 5 — Rear view",
    "FIG6_left": "FIG. 6 — Left side view",
    "FIG7_right": "FIG. 7 — Right side view",
}

# which reference numerals to call out on each view (kept sparse -> legible)
CALLOUTS = {
    "FIG1_isometric": [100, 110, 112, 120, 130, 140, 150, 160],
    "FIG2_top": [100, 110, 112, 120, 130, 140, 150, 160],
    "FIG3_bottom": [100, 110, 150, 160, 170, 180],
    "FIG4_front": [100, 110, 130, 150, 160],
    "FIG5_rear": [100, 120, 130, 140, 150],
    "FIG6_left": [100, 110, 120, 130, 140, 150, 160],
    "FIG7_right": [100, 110, 120, 130, 140, 150, 160],
}


# Per-(view, numeral) label direction override, as a unit-ish (dx, dy) --
# only needed where the default up-right placement collides with another
# label or with the title. Values are directions, scaled by the view's
# own bounding-box diagonal so they work at any zoom level.
DIR_OVERRIDE = {
    ("FIG4_front", 150): (0.3, 1.6), ("FIG4_front", 100): (1.3, 0.2),
    ("FIG4_front", 160): (1.9, 0.9),
    ("FIG5_rear", 150): (0.6, 1.6), ("FIG5_rear", 130): (1.6, -0.3),
    ("FIG5_rear", 140): (1.6, -1.4), ("FIG5_rear", 120): (-1.6, 0.6),
    ("FIG6_left", 150): (0.2, 1.9), ("FIG6_left", 120): (-1.2, 1.3),
    ("FIG6_left", 130): (1.4, -0.9),
    ("FIG7_right", 150): (0.2, 1.9), ("FIG7_right", 120): (-1.4, -0.9),
    ("FIG7_right", 130): (1.2, 1.3),
}


def draw_view(view_name, save_path):
    v = VIEWS[view_name]
    entries = []
    all_uv = []
    for name, part in PARTS.items():
        pts = np.array(part["pts"], dtype=float)
        u, vv = v["proj"](pts)
        entries.append((v["close"](pts), name, part, np.column_stack([u, vv])))
        all_uv.append(np.column_stack([u, vv]))
    entries.sort(key=lambda e: e[0])   # farthest first, nearest last

    all_uv = np.vstack(all_uv)
    umin, vmin = all_uv.min(axis=0)
    umax, vmax = all_uv.max(axis=0)
    diag = float(np.hypot(umax - umin, vmax - vmin))

    fig, ax = plt.subplots(figsize=(7.5, 6.4))
    for _, name, part, uv in entries:
        if part["kind"] == "line":
            ax.plot(uv[:, 0], uv[:, 1], color="black", linewidth=1.1,
                    solid_capstyle="round")
            continue
        if len(uv) >= 3:
            try:
                hull = ConvexHull(uv)
                poly = uv[hull.vertices]
            except Exception:
                poly = uv
        else:
            poly = uv
        ax.add_patch(MplPolygon(poly, closed=True, facecolor="white",
                                edgecolor="black", linewidth=1.1, zorder=1))

    for num in CALLOUTS[view_name]:
        pt3 = np.array([ANCHOR[num]])
        u, vv = v["proj"](pt3)
        dx, dy = DIR_OVERRIDE.get((view_name, num), (1.0, 1.0))
        norm = np.hypot(dx, dy) or 1.0
        tx = u[0] + (dx / norm) * 0.11 * diag
        ty = vv[0] + (dy / norm) * 0.11 * diag
        ax.plot(u, vv, marker="o", ms=2.2, color="black")
        ha = "right" if dx < -0.3 else "left"
        ax.annotate(str(num), xy=(u[0], vv[0]), xytext=(tx, ty),
                    fontsize=9, ha=ha, va="center",
                    arrowprops=dict(arrowstyle="-", lw=0.6, color="black"))

    ax.set_aspect("equal")
    ax.axis("off")
    # extra headroom above the geometry so labels/title never collide
    ax.set_xlim(umin - 0.12 * diag, umax + 0.12 * diag)
    ax.set_ylim(vmin - 0.08 * diag, vmax + 0.30 * diag)
    ax.set_title(FIG_TITLE[view_name], fontsize=12, family="serif", pad=16,
                y=1.0)
    fig.patch.set_facecolor("white")
    fig.tight_layout()
    fig.savefig(save_path, dpi=220, facecolor="white")
    plt.close(fig)
    print("wrote", save_path.name)


if __name__ == "__main__":
    for vname in VIEWS:
        draw_view(vname, OUT / f"{vname}.png")

    print("\nREAL (fixed) dimensions used: wing span 1300mm, root/tip chord "
          "288/173mm, wing area 0.30 m^2, unswept LE, wing incidence 1 deg "
          "(aero/RESULTS.md); elevon hinge at 28% local chord "
          "(control_authority.py); twin vertical fin area 170 cm^2 each "
          "(RESULTS.md fin-sizing table); forward + lift propeller diameter "
          "254mm / 10x4.5in (vtol_project_summary.md).")
    print("\nSCHEMATIC (placeholder, not yet engineered) dimensions used: "
          "fuselage pod length/cross-section, tail boom length/placement, "
          "horizontal-tail span/chord, lift-motor mount positions, camera/"
          "ToF underside placement. Proportioned to be plausible, not "
          "measured -- refine before a final filing.")
