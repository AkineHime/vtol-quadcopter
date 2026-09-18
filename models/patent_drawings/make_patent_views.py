#!/usr/bin/env python3
"""
Schematic patent-drawing generator for the coconut-surveillance quadplane.

v2 -- rebuilt to match the team's hand-sketched blended-wing-body layout
(fuselage blends continuously into the wing, no separate pod; twin swept
fins + a small fixed horizontal tail mounted close to the body, not on
long booms; ailerons outboard, a fixed elevator inboard; two rotor-mount
beams each carrying two lift rotors; separate nose-mounted cruise motor).
Confirmed against the team 2024-09: 4 fixed lift rotors + 1 separate
cruise motor (same QuadPlane concept as before); tail stays fixed/passive,
ailerons + elevator do pitch/roll on the wing/body -- so the CONTROL
PHILOSOPHY carries over from the earlier elevon study, only the outer
shape is new.

NOT a manufacturing CAD model. This is a proportionally-representative
wireframe (mm) built from the real, fixed component dimensions (prop
diameter) plus the team's sketch proportions. The body/wing blend,
tail size, beam placement and overall length are all still SCHEMATIC --
nothing about this shape has been aero-analysed yet. That is the next
step once this shape itself is confirmed.

Every part is stored as a 3D point cloud. Each of the 7 standard patent
views (isometric + top + bottom + front + rear + left + right) is produced
by the SAME projector, so all views are guaranteed consistent with one
underlying model.

Occlusion is approximate: each part's silhouette is its convex hull in the
current view, filled opaque white, drawn back-to-front by a per-view
"closeness to viewer" key.

    uv run --with matplotlib --with numpy --with scipy python make_patent_views.py
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

AIRLEN = 640.0   # overall nose-to-fin-tip length used to lay out top/side views

# ===========================================================================
# 1. GEOMETRY  (all dimensions in mm; X = aft from nose, Y = right span,
#    Z = up). Prop diameter is the one REAL, fixed number here (254 mm,
#    10x4.5in, from vtol_project_summary.md); everything else is a
#    schematic reading of the hand sketch, pending its own analysis.
# ===========================================================================

def disc(center, radius, axis, n=16):
    """Circle of n points, normal to `axis` ('x' or 'z'), centred at 3D
    `center`. Projects as a true circle face-on and collapses to a line
    edge-on, automatically, via the hull projector."""
    cx, cy, cz = center
    pts = []
    for a in np.linspace(0, 2 * np.pi, n, endpoint=False):
        if axis == "x":
            pts.append((cx, cy + radius * np.cos(a), cz + radius * np.sin(a)))
        else:  # 'z'
            pts.append((cx + radius * np.cos(a), cy + radius * np.sin(a), cz))
    return pts


PARTS = {}   # name -> {"kind": "hull"/"line", "pts": [...], "num": int/None}

# ---- 100  blended fuselage/wing body (SCHEMATIC -- reading of the sketch;
#           no separate pod: the body thins continuously into the wingtip)
#      stations: (y, leading_edge_x, chord, half_thickness)
BODY_STATIONS = [
    (0,   90, 430, 55),
    (150, 110, 390, 45),
    (350, 170, 300, 26),
    (500, 230, 220, 15),
    (650, 300, 120,  7),
]


def _body_side_pts(sign):
    pts = []
    for y, le, chord, h in BODY_STATIONS:
        yy = y * sign
        te = le + chord
        thick_x = le + 0.30 * chord
        pts += [(le, yy, 0), (thick_x, yy, h), (thick_x, yy, -h), (te, yy, 0)]
    return pts


body_pts = _body_side_pts(1) + _body_side_pts(-1) + [(10, 0, 8)]  # + nose tip
PARTS["body"] = {"kind": "hull", "pts": body_pts, "num": 100}

# ---- 112  ailerons (SCHEMATIC: outer wing, hinged ~72% local chord) ------
def _station_at(y):
    ys = [s[0] for s in BODY_STATIONS]
    i = np.searchsorted(ys, y)
    i = min(max(i, 1), len(BODY_STATIONS) - 1)
    (y0, le0, c0, _), (y1, le1, c1, _) = BODY_STATIONS[i - 1], BODY_STATIONS[i]
    t = (y - y0) / (y1 - y0)
    le = le0 + t * (le1 - le0)
    chord = c0 + t * (c1 - c0)
    return le, chord


def _control_pts(y0, y1, frac0, frac1, sign):
    le0, c0 = _station_at(y0)
    le1, c1 = _station_at(y1)
    h0, te0 = le0 + frac0 * c0, le0 + c0
    h1, te1 = le1 + frac1 * c1, le1 + c1
    return [(h0, y0 * sign, 0), (te0, y0 * sign, 0),
            (h1, y1 * sign, 0), (te1, y1 * sign, 0)]


PARTS["aileron_R"] = {"kind": "hull",
                      "pts": _control_pts(500, 650, 0.72, 0.72, 1), "num": 112}
PARTS["aileron_L"] = {"kind": "hull",
                      "pts": _control_pts(500, 650, 0.72, 0.72, -1), "num": 112}

# ---- 114  elevator (SCHEMATIC: fixed centre-body trailing edge) ---------
PARTS["elevator"] = {"kind": "hull",
                     "pts": _control_pts(150, 150, 0.75, 0.75, 1)
                     + _control_pts(150, 150, 0.75, 0.75, -1), "num": 114}

# ---- 120  fixed horizontal tail (SCHEMATIC, small, blended near the -----
#           fin roots -- passive, per the confirmed fixed-tail decision) --
tail_top = [(480, 0, 20), (560, 0, 20),
            (480, 300, 20), (555, 300, 20),
            (480, -300, 20), (555, -300, 20)]
PARTS["tail"] = {"kind": "hull", "pts": tail_top, "num": 120}

# ---- 130  twin swept vertical fins (SCHEMATIC -- matches the swept, ------
#           pointed "Tail" shape in the sketch) --------------------------
def _fin_pts(y):
    return [(480, y, -20), (520, y, -20), (560, y, 140), (600, y, 140),
            (480, y + (4 if y > 0 else -4), -20),
            (600, y + (4 if y > 0 else -4), 140)]


PARTS["fin_R"] = {"kind": "hull", "pts": _fin_pts(380), "num": 130}
PARTS["fin_L"] = {"kind": "hull", "pts": _fin_pts(-380), "num": 130}

# ---- 140  rotor-mount beams x2 (SCHEMATIC -- each carries 2 lift rotors,
#           matching the sketch's "beam" callout) -------------------------
PARTS["beam_R"] = {"kind": "line",
                   "pts": [(260, 240, 15), (330, 580, 15)], "num": 140}
PARTS["beam_L"] = {"kind": "line",
                   "pts": [(260, -240, 15), (330, -580, 15)], "num": 140}

# ---- 150  lift rotors x4 (SCHEMATIC mount points on the beams; REAL -----
#           prop diameter 254mm / 10x4.5in, vtol_project_summary.md) ------
LIFT = {"FL": (280, 300, 85), "RL": (315, 540, 85),
        "FR": (280, -300, 85), "RR": (315, -540, 85)}
for k, c in LIFT.items():
    PARTS[f"motor_{k}"] = {"kind": "hull", "pts": disc(c, 127, "z"), "num": 150}
    beam_pt = (c[0], c[1], 15)
    PARTS[f"pylon_{k}"] = {"kind": "line", "pts": [beam_pt, c], "num": None}

# ---- 160  forward / cruise propulsion unit (REAL prop diameter 254mm; --
#           nose-mounted tractor, separate from the 4 lift rotors) -------
PARTS["fwd_motor"] = {"kind": "hull", "pts": disc((0, 0, 8), 127, "x"),
                      "num": 160}

# ---- 170 / 180  RGB camera + ToF ranging sensor (REAL parts, SCHEMATIC -
#           underside placement) ------------------------------------------
PARTS["camera"] = {"kind": "hull", "pts": disc((150, 0, -50), 15, "x"),
                   "num": 170}
PARTS["tof"] = {"kind": "hull", "pts": disc((260, 0, -48), 10, "x"),
                "num": 180}

LABEL_TEXT = {
    100: "100  blended fuselage/wing body",
    112: "112  aileron (roll control surface)",
    114: "114  elevator (pitch control surface, fixed body)",
    120: "120  horizontal tail (fixed)",
    130: "130  vertical fin, twin (fixed)",
    140: "140  rotor-mount beam (twin)",
    150: "150  lift rotor (x4, on beams)",
    160: "160  forward / cruise propulsion unit",
    170: "170  RGB camera",
    180: "180  time-of-flight ranging sensor",
}

ANCHOR = {  # representative 3D point used for each numeral's leader line
    100: (150, 500, 15), 112: (410, 580, 0), 114: (450, 0, 0),
    120: (520, 150, 20), 130: (560, 380, 60), 140: (300, 400, 15),
    150: (280, 300, 85), 160: (0, 0, 30), 170: (150, 0, -50),
    180: (260, 0, -48),
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
    "FIG1_isometric": dict(
        proj=lambda p: (rot(p, 10, 55)[:, 0], rot(p, 10, 55)[:, 1]),
        close=lambda p: rot(p, 10, 55)[:, 2].mean()),
    "FIG2_top": dict(
        proj=lambda p: (np.array(p)[:, 1], AIRLEN - np.array(p)[:, 0]),
        close=lambda p: np.array(p)[:, 2].mean()),
    "FIG3_bottom": dict(
        proj=lambda p: (-np.array(p)[:, 1], AIRLEN - np.array(p)[:, 0]),
        close=lambda p: -np.array(p)[:, 2].mean()),
    "FIG4_front": dict(
        proj=lambda p: (-np.array(p)[:, 1], np.array(p)[:, 2]),
        close=lambda p: -np.array(p)[:, 0].mean()),
    "FIG5_rear": dict(
        proj=lambda p: (np.array(p)[:, 1], np.array(p)[:, 2]),
        close=lambda p: np.array(p)[:, 0].mean()),
    "FIG6_left": dict(
        proj=lambda p: (np.array(p)[:, 0], np.array(p)[:, 2]),
        close=lambda p: -np.array(p)[:, 1].mean()),
    "FIG7_right": dict(
        proj=lambda p: (AIRLEN - np.array(p)[:, 0], np.array(p)[:, 2]),
        close=lambda p: np.array(p)[:, 1].mean()),
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

CALLOUTS = {
    "FIG1_isometric": [100, 112, 114, 120, 130, 140, 150, 160],
    "FIG2_top": [100, 112, 114, 120, 130, 140, 150, 160],
    "FIG3_bottom": [100, 140, 150, 160, 170, 180],
    "FIG4_front": [100, 130, 150, 160],
    "FIG5_rear": [100, 120, 130, 140, 150],
    "FIG6_left": [100, 120, 130, 140, 150, 160],
    "FIG7_right": [100, 120, 130, 140, 150, 160],
}

DIR_OVERRIDE = {
    ("FIG1_isometric", 150): (0.2, 1.7), ("FIG1_isometric", 140): (-1.4, 1.0),
    ("FIG2_top", 150): (1.6, 0.4), ("FIG2_top", 140): (1.7, -0.3),
    ("FIG4_front", 150): (1.6, 0.6), ("FIG4_front", 160): (0.2, 1.7),
    ("FIG4_front", 130): (-1.4, 1.1),
    ("FIG5_rear", 150): (1.6, 0.6), ("FIG5_rear", 130): (-1.4, 1.1),
    ("FIG5_rear", 140): (1.6, -0.7),
    ("FIG6_left", 150): (0.2, 1.8), ("FIG6_left", 140): (-0.3, -1.7),
    ("FIG6_left", 120): (1.2, -1.2),
    ("FIG7_right", 150): (0.2, 1.8), ("FIG7_right", 140): (0.3, -1.7),
    ("FIG7_right", 120): (-1.2, -1.2),
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

    print("\nREAL (fixed) dimension used: lift + cruise propeller diameter "
          "254mm / 10x4.5in (vtol_project_summary.md). Everything else in "
          "this shape -- the body/wing blend, tail size and placement, "
          "beam layout, overall length -- is a SCHEMATIC reading of the "
          "team's hand sketch and has not been aero-analysed yet. That is "
          "the next step once this shape is confirmed correct.")
