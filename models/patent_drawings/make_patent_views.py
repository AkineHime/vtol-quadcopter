#!/usr/bin/env python3
"""
Patent-drawing generator for the coconut-surveillance quadplane -- v3.

Built directly from the real KCL CAD source (3d model files/*.zip,
demo-project/*.kcl), which the team confirmed IS the intended design
(reverse-engineered from the actual Raefly VT240 Pro reference photo).
Every dimension below is either:
  (a) taken straight from the KCL part files, converted through the same
      modelScale = 1500/3040 = 0.493421 factor main.kcl applies, or
  (b) a NEW addition the team confirmed in this session, clearly marked,
      with the reasoning that drove its size.

NEW vs. the original KCL (confirmed this session, not yet in the CAD):
  - Front lift rotors on each boom mounted BELOW the boom, rear lift
    rotors mounted ABOVE the boom (was: both at the same height) --
    keeps each boom's rear rotor out of its front rotor's downwash.
  - Vertical fins extended down to the same ground line as the front
    landing legs, to serve as the rear gear -- with only 2 front legs,
    the tail would otherwise sag onto the pusher prop. The extension
    length (~291mm) is computed from the real leg and fin geometry
    below, not assumed.
  - A short brace from each boom's aft tip into the fin root, so the
    booms structurally support the tail instead of ending near it
    unattached -- stiffer for the same material (ties two long
    cantilevers together instead of leaving them independent).
  - All five propellers the SAME size (the KCL scales the pusher to
    72% of the lift-rotor size, photo-inferred; the real hardware BOM
    specs one prop, 1045/254mm, for all five positions).

Occlusion is approximate: each part's silhouette is its convex hull in
the current view, filled opaque white, drawn back-to-front.

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

S = 1500.0 / 3040.0          # main.kcl's modelScale
AIRLEN = 1190.0              # nose tip to pusher-disc aft edge, post-scale

# ===========================================================================
# 1. GEOMETRY (mm, post-scale). X = aft from nose, Y = right span, Z = up.
# ===========================================================================

def ring(x, r, n=8, squash=1.0):
    return [(x, r * np.cos(a), squash * r * np.sin(a))
            for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]


def disc(center, radius, axis, n=16):
    cx, cy, cz = center
    pts = []
    for a in np.linspace(0, 2 * np.pi, n, endpoint=False):
        if axis == "x":
            pts.append((cx, cy + radius * np.cos(a), cz + radius * np.sin(a)))
        else:
            pts.append((cx + radius * np.cos(a), cy + radius * np.sin(a), cz))
    return pts


PARTS = {}

# ---- 100 fuselage: real loft stations from fuselage.kcl (x, radius), -----
#      z-flattened to 0.82 (matches the KCL's local z-scale) ---------------
FUSE_STATIONS = [(-1080, 12), (-900, 112), (-560, 188), (0, 198),
                 (500, 140), (820, 78), (1020, 42)]
body_pts = []
for x_pre, r_pre in FUSE_STATIONS:
    body_pts += ring(x_pre * S, r_pre * S, n=10, squash=0.82)
PARTS["body"] = {"kind": "hull", "pts": body_pts, "num": 100}

# ---- 102 nose sensor probe: sensorProbe.kcl, x=-1150 to -910 pre-scale --
PARTS["probe"] = {"kind": "line",
                  "pts": [(-1150 * S, 0, 0), (-910 * S, 0, 0)], "num": 102}

# ---- 104 landing legs x2 ONLY: landingStrut.kcl, main.kcl placement -----
#      ground line established here: bottom = (-265-135)*S = -197.4mm -----
for k, ysign in (("R", 1), ("L", -1)):
    top = (-170 * S, 135 * S * ysign, -130 * S)
    bot = (-170 * S, 135 * S * ysign, -400 * S)
    PARTS[f"leg_{k}"] = {"kind": "line", "pts": [top, bot], "num": 104}
GROUND_Z = -400 * S   # -197.4mm

# ---- 110 wing: wingHalf.kcl profile, +2deg dihedral, main.kcl placement --
def wing_half(sign):
    root_le = (-330 * S, 0, 155 * S)
    root_te = (230 * S, 0, 155 * S)
    tip_dz = 1520 * np.sin(np.radians(2))          # dihedral rise at tip
    tip_le = (-10 * S, 1520 * S * sign, (155 + tip_dz) * S)
    tip_te = (280 * S, 1520 * S * sign, (155 + tip_dz) * S)
    return [root_le, root_te, tip_le, tip_te]


PARTS["wing_R"] = {"kind": "hull", "pts": wing_half(1), "num": 110}
PARTS["wing_L"] = {"kind": "hull", "pts": wing_half(-1), "num": 110}

# ---- 120 horizontal tail: tailHalf.kcl, main.kcl placement [650,0,180] --
def tail_half(sign):
    root_le = (650 * S, 0, 180 * S)
    root_te = (990 * S, 0, 180 * S)
    tip_le = (770 * S, 500 * S * sign, 180 * S)
    tip_te = (990 * S, 500 * S * sign, 180 * S)
    return [root_le, root_te, tip_le, tip_te]


PARTS["tail"] = {"kind": "hull", "pts": tail_half(1) + tail_half(-1),
                 "num": 120}

# ---- 130 vertical fin (twin): verticalFin.kcl (curved crown top), -------
#      main.kcl placement [690,+-230,190] ----------------------------------
def fin_pts(sign):
    y = 230 * S * sign
    root_front = (690 * S, y, 190 * S)
    root_back = (970 * S, y, 190 * S)
    mid_back = (955 * S, y, 350 * S)
    crown = (760 * S, y, 435 * S)          # curved-crown apex
    return [root_front, root_back, mid_back, crown]


PARTS["fin_R"] = {"kind": "hull", "pts": fin_pts(1), "num": 130}
PARTS["fin_L"] = {"kind": "hull", "pts": fin_pts(-1), "num": 130}

# ---- 132 NEW fin-base landing skid: extend each fin down to GROUND_Z ----
#      extension length = fin root z (93.8mm) - GROUND_Z = ~291mm ---------
for k, sign in (("R", 1), ("L", -1)):
    y = 230 * S * sign
    top1, top2 = (690 * S, y, 190 * S), (740 * S, y, 190 * S)
    bot1, bot2 = (700 * S, y, GROUND_Z), (760 * S, y, GROUND_Z)
    PARTS[f"finskid_{k}"] = {"kind": "hull", "pts": [top1, top2, bot1, bot2],
                             "num": 132}

# ---- 140 rotor-mount booms (twin): liftBoom.kcl, main.kcl [0,+-440,38] --
BOOM_Z = 38 * S
for k, sign in (("R", 1), ("L", -1)):
    y = 440 * S * sign
    PARTS[f"boom_{k}"] = {"kind": "line",
                          "pts": [(-660 * S, y, BOOM_Z), (660 * S, y, BOOM_Z)],
                          "num": 140}
    # ---- 142 NEW: brace tying the boom's aft tip into the fin root -----
    PARTS[f"brace_{k}"] = {"kind": "line",
                           "pts": [(660 * S, y, BOOM_Z),
                                  (690 * S, 230 * S * sign, 190 * S)],
                           "num": 142}

# ---- 150/152 lift rotors x4: motorPod + propeller, main.kcl positions, --
#      STAGGERED per this session's confirmed change: front pods/rotors --
#      mounted below the boom, rear pods/rotors mounted above it --------
PROP_R = 295 * S   # uniform prop radius, ~146mm (all 5 rotors this size)
LIFT = {
    "FR": (-440 * S, 440 * S, BOOM_Z - 70 * S, 150),
    "FL": (-440 * S, -440 * S, BOOM_Z - 70 * S, 150),
    "RR": (430 * S, 440 * S, BOOM_Z + 70 * S, 152),
    "RL": (430 * S, -440 * S, BOOM_Z + 70 * S, 152),
}
for k, (x, y, z, num) in LIFT.items():
    PARTS[f"rotor_{k}"] = {"kind": "hull", "pts": disc((x, y, z), PROP_R, "z"),
                           "num": num}
    PARTS[f"pylon_{k}"] = {"kind": "line", "pts": [(x, y, BOOM_Z), (x, y, z)],
                           "num": None}

# ---- 160 pusher propeller: main.kcl [1030,0,45], NOW same size as lift --
PUSH_X, PUSH_Z = 1030 * S, 45 * S
PARTS["pusher"] = {"kind": "hull", "pts": disc((PUSH_X, 0, PUSH_Z), PROP_R, "x"),
                   "num": 160}
PARTS["pusher_mast"] = {"kind": "line",
                        "pts": [(970 * S, 0, 190 * S), (PUSH_X, 0, PUSH_Z)],
                        "num": None}

LABEL_TEXT = {
    100: "100  fuselage", 102: "102  nose sensor probe",
    104: "104  landing leg (x2, front only)", 110: "110  main wing",
    120: "120  horizontal tail", 130: "130  vertical fin (twin)",
    132: "132  fin-base landing skid (NEW, ~291mm extension)",
    140: "140  rotor-mount boom (twin)",
    142: "142  boom-to-tail brace (NEW)",
    150: "150  front lift rotor (mounted below boom, NEW stagger)",
    152: "152  rear lift rotor (mounted above boom, NEW stagger)",
    160: "160  pusher propeller (aft of tail, same size as lift rotors)",
}

ANCHOR = {
    100: (0, 95, 20), 102: (-1000 * S, 0, 0), 104: (-84, 66, -130),
    110: (-50, 700, 90), 120: (480, 150, 89), 130: (470, 113, 150),
    132: (350, 113, -60), 140: (150, 217, 19), 142: (330, 217, 60),
    150: (-217, 217, -55), 152: (212, 217, 102), 160: (PUSH_X, 0, PUSH_Z),
}

# ===========================================================================
# 2. VIEWS (unchanged engine from the earlier passes)
# ===========================================================================

def rot(pts, deg_z, deg_x):
    a, b = np.radians(deg_z), np.radians(deg_x)
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0],
                   [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)],
                   [0, np.sin(b), np.cos(b)]])
    return (np.array(pts) @ Rz.T) @ Rx.T


VIEWS = {
    "FIG1_isometric": dict(
        proj=lambda p: (rot(p, 12, 58)[:, 0], rot(p, 12, 58)[:, 1]),
        close=lambda p: rot(p, 12, 58)[:, 2].mean()),
    "FIG2_top": dict(
        proj=lambda p: (np.array(p)[:, 1], AIRLEN / 2 - np.array(p)[:, 0]),
        close=lambda p: np.array(p)[:, 2].mean()),
    "FIG3_bottom": dict(
        proj=lambda p: (-np.array(p)[:, 1], AIRLEN / 2 - np.array(p)[:, 0]),
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
        proj=lambda p: (AIRLEN / 2 - (np.array(p)[:, 0] - AIRLEN / 2),
                        np.array(p)[:, 2]),
        close=lambda p: np.array(p)[:, 1].mean()),
}

FIG_TITLE = {
    "FIG1_isometric": "FIG. 1 — Perspective view",
    "FIG2_top": "FIG. 2 — Top view", "FIG3_bottom": "FIG. 3 — Bottom view",
    "FIG4_front": "FIG. 4 — Front view", "FIG5_rear": "FIG. 5 — Rear view",
    "FIG6_left": "FIG. 6 — Left side view (ground line shown)",
    "FIG7_right": "FIG. 7 — Right side view",
}

CALLOUTS = {
    "FIG1_isometric": [100, 110, 120, 130, 132, 140, 142, 150, 152, 160],
    "FIG2_top": [100, 110, 120, 130, 140, 150, 152, 160],
    "FIG3_bottom": [100, 104, 132, 150, 152, 160],
    "FIG4_front": [100, 130, 132, 150, 152, 160],
    "FIG5_rear": [100, 120, 130, 132, 140, 150, 152],
    "FIG6_left": [100, 102, 104, 110, 120, 130, 132, 140, 142, 150, 152, 160],
    "FIG7_right": [100, 104, 110, 120, 130, 140, 150, 152, 160],
}

DIR_OVERRIDE = {}   # filled in per-view below if collisions show up


def draw_view(view_name, save_path, ground=False):
    v = VIEWS[view_name]
    entries, all_uv = [], []
    for name, part in PARTS.items():
        pts = np.array(part["pts"], dtype=float)
        u, vv = v["proj"](pts)
        entries.append((v["close"](pts), name, part, np.column_stack([u, vv])))
        all_uv.append(np.column_stack([u, vv]))
    entries.sort(key=lambda e: e[0])

    all_uv = np.vstack(all_uv)
    umin, vmin = all_uv.min(axis=0)
    umax, vmax = all_uv.max(axis=0)
    diag = float(np.hypot(umax - umin, vmax - vmin))

    fig, ax = plt.subplots(figsize=(8, 6.8))
    for _, name, part, uv in entries:
        if part["kind"] == "line":
            ax.plot(uv[:, 0], uv[:, 1], color="black", linewidth=1.1,
                    solid_capstyle="round")
            continue
        try:
            hull = ConvexHull(uv)
            poly = uv[hull.vertices]
        except Exception:
            poly = uv
        ax.add_patch(MplPolygon(poly, closed=True, facecolor="white",
                                edgecolor="black", linewidth=1.1, zorder=1))

    if ground and view_name == "FIG6_left":
        gz = VIEWS[view_name]["proj"](np.array([[0, 0, GROUND_Z]]))[1][0]
        ax.axhline(gz, color="black", lw=0.8, ls="--")
        ax.text(umax, gz - 0.04 * diag, "ground line", fontsize=8,
                ha="right", style="italic")

    for num in CALLOUTS[view_name]:
        pt3 = np.array([ANCHOR[num]])
        u, vv = v["proj"](pt3)
        dx, dy = DIR_OVERRIDE.get((view_name, num), (1.0, 1.0))
        norm = np.hypot(dx, dy) or 1.0
        tx = u[0] + (dx / norm) * 0.11 * diag
        ty = vv[0] + (dy / norm) * 0.11 * diag
        ax.plot(u, vv, marker="o", ms=2.2, color="black")
        ha = "right" if dx < -0.3 else "left"
        ax.annotate(str(num), xy=(u[0], vv[0]), xytext=(tx, ty), fontsize=9,
                    ha=ha, va="center",
                    arrowprops=dict(arrowstyle="-", lw=0.6, color="black"))

    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(umin - 0.12 * diag, umax + 0.12 * diag)
    ax.set_ylim(vmin - 0.10 * diag, vmax + 0.30 * diag)
    ax.set_title(FIG_TITLE[view_name], fontsize=12, family="serif", pad=16)
    fig.patch.set_facecolor("white")
    fig.tight_layout()
    fig.savefig(save_path, dpi=220, facecolor="white")
    plt.close(fig)
    print("wrote", save_path.name)


if __name__ == "__main__":
    for vname in VIEWS:
        draw_view(vname, OUT / f"{vname}.png", ground=True)

    print(f"\nScale factor from KCL: S = {S:.6f} (1500mm target span / "
          f"3040mm CAD span)")
    print(f"Ground line (from front legs): z = {GROUND_Z:.1f} mm")
    print(f"Fin-skid extension required: "
          f"{190*S - GROUND_Z:.1f} mm below the original fin root")
