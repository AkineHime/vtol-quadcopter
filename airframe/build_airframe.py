#!/usr/bin/env python3
"""
build_airframe.py -- print-ready CoconutQuadplane airframe (CadQuery).

    python build_airframe.py            # WSL venv: ~/venv-ardupilot (pip install cadquery)

Writes
  print/<part>.stl                  every printable part, one file each (mm)
  out/coconut_quadplane_build.step  full assembly incl. carbon tubes
  out/mass_properties.json          per-part mass, CG, inertia (two material configs)
  out/preview_*.png                 quick-look renders (iso / side / top)

Construction (see BUILD_NOTES.md):
  * wing: two detachable halves on one 12 mm carbon spar + 4 mm anti-rotation
    rod, printed in 4 segments per side + a PETG boom node at Y=+-300 that
    carries each VTOL boom straight into the spar
  * pod: 3 printed sections with sleeve joints + M3 screws, magnetic top hatch
    with a front tongue, contoured wing saddle with 2 M4 nylon wing bolts per
    side, battery tray (battery slides to set the CG)
  * tail: printed H-stab (centre keel over a 10 mm carbon tail boom + 2 tips
    on a 4 mm rod) and twin fins; pusher mount on the boom end
  * 4 motor pods (5 deg tangential yaw tilt) + 6 mm carbon landing legs
All dimensions come from params.py.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cadquery as cq

import params as P

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT_PRINT = HERE / "print"
OUT = HERE / "out"
V = cq.Vector


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def load_airfoil(name: str, step: int = 1) -> list[tuple[float, float]]:
    pts = []
    for line in (REPO / "aero" / "airfoils" / f"{name}.dat").read_text().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            pts.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    out: list[tuple[float, float]] = []
    for p in pts[::step] + ([pts[-1]] if step > 1 else []):
        if not out or abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if abs(out[0][0] - out[-1][0]) < 1e-6 and abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


AF_WING = load_airfoil(P.AIRFOIL_WING)
AF_TAIL = load_airfoil(P.AIRFOIL_TAIL, step=3)


def section_pts(af, chord, x_le, y, z_ref, inc_deg, plane="XZ", pivot=0.25):
    """Airfoil points in 3D. plane XZ: horizontal surface at span station y.
    plane XY: vertical surface (fin) at height z = y-arg, thickness along Y
    around z_ref (used as the fin's Y position). Nose-up incidence."""
    c, s = math.cos(math.radians(inc_deg)), math.sin(math.radians(inc_deg))
    px = x_le + pivot * chord
    out = []
    for u, w in af:
        dx, dz = (x_le + u * chord) - px, w * chord
        xr, zr = px + dx * c + dz * s, dz * c - dx * s
        if plane == "XZ":
            out.append(V(xr, y, z_ref + zr))
        else:
            out.append(V(xr, z_ref + zr, y))
    return out


def poly_wire(pts):
    return cq.Wire.makePolygon(pts, close=True)


def loft(wires, ruled=True):
    return cq.Solid.makeLoft(wires, ruled)


def box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p0, direction, length):
    return cq.Solid.makeCylinder(r, length, V(*p0), V(*direction))


def bounds_at(pts3d, x, axis_z=2):
    """Lower/upper Z of a closed section polygon at a given X (ray cast)."""
    zs = []
    n = len(pts3d)
    for i in range(n):
        a, b = pts3d[i], pts3d[(i + 1) % n]
        if (a.x - x) * (b.x - x) <= 0 and a.x != b.x:
            t = (x - a.x) / (b.x - a.x)
            zs.append([a.x, a.y, a.z][axis_z] + t * ([b.x, b.y, b.z][axis_z] - [a.x, a.y, a.z][axis_z]))
    return (min(zs), max(zs)) if len(zs) >= 2 else (None, None)


# --------------------------------------------------------------------------
# wing
# --------------------------------------------------------------------------
def w_chord(y):
    return P.C_ROOT + (P.C_TIP - P.C_ROOT) * abs(y) / (P.SPAN / 2)


def w_xle(y):
    return abs(y) * math.tan(math.radians(P.SWEEP_LE_DEG))


def w_pts(y):
    return section_pts(AF_WING, w_chord(y), w_xle(y), y, P.Z_WING, P.I_WING_DEG)


def w_wire(y):
    return poly_wire(w_pts(y))


def w_hinge_x(y):
    return w_xle(y) + (1 - P.ELEVON_CHORD_FRAC) * w_chord(y)


X_SPAR = P.X_LE_MAC + P.SPAR_X_FRAC * P.MAC
X_PIN = P.PIN_X_ROOT_FRAC * P.C_ROOT


def fit_rod_z(x, r, y_max):
    """Highest-clearance straight-rod Z at chordwise X over 0..y_max."""
    lo, hi = -1e9, 1e9
    for k in range(0, 11):
        y = y_max * k / 10
        zl, zu = bounds_at(w_pts(y), x)
        lo, hi = max(lo, zl + r), min(hi, zu - r)
    return (lo + hi) / 2, (hi - lo) / 2   # z, remaining margin (mm)


Z_SPAR, SPAR_MARGIN = fit_rod_z(X_SPAR, P.SPAR_OD / 2 + 0.8, P.SPAN / 2 - 5)
Z_PIN, PIN_MARGIN = fit_rod_z(X_PIN, P.PIN_OD / 2 + 0.8, P.PIN_HALF)


def y_cyl(r, x, z, y0, y1):
    return cyl(r, (x, min(y0, y1), z), (0, 1, 0), abs(y1 - y0))


def elevon_prism(y0, y1, offset):
    """Everything aft of (hinge + offset) between stations y0..y1."""
    def rect(y):
        h = w_hinge_x(y) + offset
        return poly_wire([V(h, y, -50), V(h + 400, y, -50), V(h + 400, y, 200), V(h, y, 200)])
    return loft([rect(y0), rect(y1)])


def wing_segment(y0, y1, side):
    ya, yb = side * y0, side * y1
    seg = loft([w_wire(ya), w_wire(yb)])
    seg = seg.cut(y_cyl(P.SPAR_OD / 2 + P.CLEAR, X_SPAR, Z_SPAR, ya - side, yb + side))
    if y0 < P.PIN_HALF:
        seg = seg.cut(y_cyl(P.PIN_OD / 2 + P.CLEAR, X_PIN, Z_PIN, ya - side, side * min(y1 + 1, P.PIN_HALF)))
    e0, e1 = max(y0, P.ELEVON_Y[0]), min(y1, P.ELEVON_Y[1])
    if e0 < e1:
        seg = seg.cut(elevon_prism(side * (e0 - 0.5), side * (e1 + 0.5), -0.5))
    if y0 == 0.0:      # wing bolts through the root segment
        for bx, by in P.WING_BOLTS:
            seg = seg.cut(cyl(2.15, (bx, side * by, -100), (0, 0, 1), 300))
    if y0 <= 330 < y1:  # elevon servo (MG90S) pocket, open at the bottom
        yc = side * 342
        x40 = w_xle(yc) + 0.40 * w_chord(yc)
        zl, zu = bounds_at(w_pts(yc), x40)
        seg = seg.cut(box(x40 - 6.5, x40 + 6.5, min(yc - side * 12, yc + side * 12),
                          max(yc - side * 12, yc + side * 12), zl - 5, zu - 1.2))
    return seg


def elevon_piece(y0, y1, side):
    ya, yb = side * (y0 + 0.5), side * (y1 - 0.5)
    piece = loft([w_wire(ya), w_wire(yb)]).intersect(elevon_prism(ya, yb, 0.5))
    ym = (ya + yb) / 2
    xr = w_hinge_x(ym) + 6
    zl, zu = bounds_at(w_pts(ym), xr)
    return piece.cut(y_cyl(1.1, xr, (zl + zu) / 2, ya - side, yb + side))   # 2 mm joiner rod


def boom_node(side):
    y0, y1 = side * P.NODE_Y[0], side * P.NODE_Y[1]
    rib = loft([w_wire(y0), w_wire(y1)])
    yb = side * P.BOOM_Y
    ring = cyl(P.BOOM_OD / 2 + 3.0, (X_SPAR - 30, yb, P.Z_BOOM), (1, 0, 0), 60)
    zl, _ = bounds_at(w_pts(yb), X_SPAR)
    web = box(X_SPAR - 25, X_SPAR + 25, min(y0, y1), max(y0, y1), P.Z_BOOM, zl + 4)
    node = rib.fuse(ring).fuse(web)
    node = node.cut(y_cyl(P.SPAR_OD / 2 + P.CLEAR, X_SPAR, Z_SPAR, y0 - side, y1 + side))
    node = node.cut(y_cyl(P.PIN_OD / 2 + P.CLEAR, X_PIN, Z_PIN, y0 - side, y1 + side))
    node = node.cut(cyl(P.BOOM_OD / 2 + P.CLEAR, (X_SPAR - 40, yb, P.Z_BOOM), (1, 0, 0), 80))
    return node


def boom_pylon(side):
    """Rear brace between the boom and the wing underside (glued)."""
    yb, xp = side * P.BOOM_Y, 200.0
    zl, _ = bounds_at(w_pts(yb), xp)
    pylon = box(xp - 10, xp + 10, yb - 8, yb + 8, P.Z_BOOM, zl + 0.5)
    pylon = pylon.fuse(cyl(P.BOOM_OD / 2 + 2.5, (xp - 12, yb, P.Z_BOOM), (1, 0, 0), 24))
    pylon = pylon.cut(loft([w_wire(yb - 20), w_wire(yb + 20)]))   # contour to the skin
    return pylon.cut(cyl(P.BOOM_OD / 2 + P.CLEAR, (xp - 20, yb, P.Z_BOOM), (1, 0, 0), 40))


# --------------------------------------------------------------------------
# fuselage pod
# --------------------------------------------------------------------------
POD_STATIONS = P.POD_STATIONS


def pod(off, x0=None, x1=None):
    """Pod loft offset inward by `off`, optionally clipped to x0..x1 by
    interpolating end stations (so each print section is its own clean loft)."""
    # Dense ruled loft through a smooth, overshoot-free outline: a spline loft
    # through a few clipped stations bulged differently inside and out and
    # turned the 0.8 mm wall into centimetres in places.
    a = POD_STATIONS[0][0] if x0 is None else max(x0, POD_STATIONS[0][0])
    b = POD_STATIONS[-1][0] if x1 is None else min(x1, POD_STATIONS[-1][0])
    n = max(2, int(math.ceil((b - a) / 8.0)) + 1)
    xs = [a + (b - a) * i / (n - 1) for i in range(n)]
    wires = []
    for x in xs:
        w, h = pod_wh(x)
        wires.append(cq.Wire.makeEllipse(w / 2 - off, h / 2 - off, V(x, 0, P.POD_ZC), V(1, 0, 0), V(0, 1, 0)))
    return cq.Solid.makeLoft(wires, True)


def pod_wh(x):
    """Pod width/height at X: smoothstep between stations (C1, no overshoot)."""
    st = POD_STATIONS
    if x <= st[0][0]:
        return st[0][1:]
    for (x0, w0, h0), (x1, w1, h1) in zip(st, st[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            t = t * t * (3 - 2 * t)
            return w0 + t * (w1 - w0), h0 + t * (h1 - h0)
    return st[-1][1:]


def _prism_y(pts_xz, y0, y1):
    """Extrude a closed XZ polygon from y0 to y1 (planar faces: robust booleans)."""
    wire = cq.Wire.makePolygon([V(x, y0, z) for x, z in pts_xz], close=True)
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(wire), V(0, y1 - y0, 0))


def wing_root_solid():
    """The wing root over the pod as a prism of the root section (the real
    loft changes < 3 mm over these 164 mm; the prism is the larger of the two,
    so the saddle opening is conservative)."""
    return _prism_y([(p.x, p.z) for p in w_pts(0)], -82, 82)


def saddle_layer(t=2.5, half=60.0):
    """t-mm layer that follows the wing root's lower surface."""
    pts = [(p.x, p.z) for p in w_pts(0)]
    i_le = min(range(len(pts)), key=lambda i: pts[i][0])
    lower = pts[i_le:] + [pts[0]]                 # LE -> TE along the lower surface
    poly = lower + [(x, z - t) for x, z in reversed(lower)]
    return _prism_y(poly, -half, half)


def build_pod():
    """Each print section is lofted on its own and only then given its
    features: cutting one big fused pod into sections failed silently in
    OpenCASCADE (empty or untouched results)."""
    outer = pod(0)
    wroot = wing_root_solid()
    hx0, hx1 = P.HATCH_X
    nsec = len(P.POD_SECTIONS)

    add, cut = [], []
    # contoured saddle: a 2.5 mm layer under the wing root, inside the pod
    add.append(saddle_layer().intersect(outer))
    # wing-bolt bosses from the pod floor up to the wing (M4 heat-set insert, 5.6 mm)
    for bx, by in P.WING_BOLTS:
        _, h = pod_wh(bx)
        z0 = P.POD_ZC - h / 2 + P.WALL
        for s in (1, -1):
            # stops inside the wing, so after the saddle cut it ends exactly on the skin
            boss = cyl(5.5, (bx, s * by, z0), (0, 0, 1), P.Z_WING - z0).cut(wroot)
            add.append(boss)
            cut.append(cyl(2.8, (bx, s * by, z0 + 4), (0, 0, 1), 200))
    cut.append(wroot)                                   # open the saddle; the wing closes it
    # tail-boom socket
    add.append(cyl(P.TAILBOOM_OD / 2 + 3, (P.TAILBOOM_X[0], 0, P.Z_TAIL), (1, 0, 0),
                   P.POD_X[1] - P.TAILBOOM_X[0]).intersect(outer))
    cut.append(cyl(P.TAILBOOM_OD / 2 + P.CLEAR, (P.TAILBOOM_X[0] - 1, 0, P.Z_TAIL), (1, 0, 0), 80))
    # battery tray on 6 posts, strap slots
    tray = box(-160, 80, -28, 28, -47.2, -46)
    for px in (-150.0, -60.0, 30.0):
        for py in (-22.0, 22.0):
            tray = tray.fuse(cyl(2.0, (px, py, -80), (0, 0, 1), 34))
    tray = tray.intersect(pod(P.WALL * 0.5))
    for sx in (-120.0, 40.0):
        tray = tray.cut(box(sx - 2, sx + 2, -12, 12, -60, -40))
    add.append(tray)
    # nose sensors: ESP32-CAM window (60 deg below the horizon, forward: sees the
    # crown top AND the bunches under the fronds on a pass) and ToF port
    cut.append(cyl(4.5, (-185, 0, -12), (-math.cos(math.radians(60)), 0, -math.sin(math.radians(60))), 40))
    cut.append(cyl(3.5, (-150, 0, -40), (0, 0, -1), 40))
    # hatch ledges + magnet blocks + tongue seat
    add.append(pod(P.WALL * 0.5).cut(pod(P.WALL + 2.5)).intersect(box(hx0 + 2, hx1 - 2, -100, 100, 18, 22)))
    mags = []
    for s in (1, -1):
        w, h = pod_wh(hx1 - 15)
        yi = (w / 2 - P.WALL) * math.sqrt(max(0.0, 1 - (22 / (h / 2 - P.WALL)) ** 2))
        blk = box(hx1 - 20, hx1 - 10, min(s * (yi - 9), s * (yi + 1)), max(s * (yi - 9), s * (yi + 1)), 18, 22)
        add.append(blk.intersect(pod(P.WALL * 0.5)))
        cut.append(cyl(2.6, (hx1 - 15, s * (yi - 4.5), 19.8), (0, 0, 1), 2.4))
        mags.append((hx1 - 15, s * (yi - 4.5)))
    w, h = pod_wh(hx0 - 4)
    top_in = h / 2 - P.WALL
    add.append(box(hx0 - 9.5, hx0 + 4.5, -15, 15, top_in - 3.6, top_in - 2.6).intersect(pod(P.WALL * 0.5)))
    cut.append(box(hx0 - 0.3, hx1 + 0.3, -100, 100, 22, 100))          # hatch opening
    for _, j in P.POD_SECTIONS[:-1]:
        cut.append(cyl(1.6, (j + 5, -100, 0), (0, 1, 0), 200))         # radial M3 joint screws

    sections = {}
    for k, (a, b) in enumerate(P.POD_SECTIONS):
        i0 = a + P.WALL if k == 0 else a - 1
        i1 = b - P.WALL if k == nsec - 1 else b + 1
        sec = pod(0, a, b).cut(pod(P.WALL, i0, i1))
        clip = box(a, b, -100, 100, -200, 200)
        for i, f in enumerate(add):
            try:
                fc = f.intersect(clip)
                if fc.Solids() and fc.Volume() > 1.0:
                    sec = sec.fuse(fc)
            except ValueError:       # empty boolean result
                continue
        if k < nsec - 1:   # sleeve lip into the next section
            lip = pod(P.WALL + P.CLEAR, b - 1, b + P.JOINT_LIP).cut(
                pod(P.WALL + P.CLEAR + 1.6, b - 2, b + P.JOINT_LIP + 1))
            sec = sec.fuse(lip)
        for f in cut:
            sec = sec.cut(f)
        sections[f"pod_{['nose', 'mid', 'tail'][k]}"] = sec.clean()

    hatch = outer.cut(pod(P.WALL)).intersect(box(hx0, hx1, -100, 100, 22, 100))
    hatch = hatch.fuse(box(hx0 - 9, hx0 + 4, -14, 14, top_in - 2.6, top_in - 1.0))     # front tongue
    for mx, my in mags:
        hb = box(mx - 5, mx + 5, my - 4.5, my + 4.5, 22.2, 26).intersect(pod(P.WALL * 0.5))
        hatch = hatch.fuse(hb).cut(cyl(2.6, (mx, my, 22.0), (0, 0, 1), 2.4))
    return sections, hatch.clean()


# --------------------------------------------------------------------------
# tail
# --------------------------------------------------------------------------
def h_chord(y):
    return P.C_ROOT_H + (P.C_TIP_H - P.C_ROOT_H) * abs(y) / (P.B_H / 2)


def h_wire(y):
    return poly_wire(section_pts(AF_TAIL, h_chord(y), P.X_LE_H, y, P.Z_STAB, P.I_TAIL_DEG))


X_STAB_SPAR = P.X_LE_H + 0.3 * P.C_ROOT_H


def stab_parts():
    centre = loft([h_wire(-100), h_wire(0), h_wire(100)])
    keel = cyl(P.TAILBOOM_OD / 2 + 3, (P.X_LE_H + 4, 0, P.Z_TAIL), (1, 0, 0), P.C_ROOT_H - 8)
    keel = keel.fuse(box(P.X_LE_H + 4, P.X_LE_H + P.C_ROOT_H - 8, -4, 4, P.Z_TAIL, P.Z_STAB))
    centre = centre.fuse(keel)
    centre = centre.cut(cyl(P.TAILBOOM_OD / 2 + P.CLEAR, (P.X_LE_H - 10, 0, P.Z_TAIL), (1, 0, 0), P.C_ROOT_H + 20))
    centre = centre.cut(y_cyl(P.STAB_SPAR_OD / 2 + P.CLEAR, X_STAB_SPAR, P.Z_STAB, -101, 101))
    tips = {}
    for s, nm in ((1, "R"), (-1, "L")):
        tip = loft([h_wire(s * 100), h_wire(s * 250)])
        tip = tip.cut(y_cyl(P.STAB_SPAR_OD / 2 + P.CLEAR, X_STAB_SPAR, P.Z_STAB, s * 99, s * 240))
        tips[f"stab_tip_{nm}"] = tip
    return centre, tips


def fin(side):
    x_le_root = P.X_LE_H + P.C_TIP_H - P.C_ROOT_V + 10
    y = side * (P.B_H / 2)

    def fw(z, chord, x_le):
        return poly_wire(section_pts(AF_TAIL, chord, x_le, z, y, 0.0, plane="XY"))
    return loft([fw(P.Z_STAB - 2, P.C_ROOT_V, x_le_root),
                 fw(P.Z_STAB + P.B_V, P.C_TIP_V, x_le_root + 30)])


# --------------------------------------------------------------------------
# motor pods, pusher mount, feet
# --------------------------------------------------------------------------
def tilt_normal(xm, ym, spin):
    """5 deg tangential tilt (FLU logic of gen_sdf.yaw_tilt_rpy) in the build frame."""
    x, y = P.X_CG_TARGET - xm, -ym               # FLU
    r = math.hypot(x, y)
    ux, uy = (y / r, -x / r) if spin > 0 else (-y / r, x / r)
    th = math.radians(P.MOTOR_YAW_TILT_DEG)
    return V(-ux * math.sin(th), -uy * math.sin(th), math.cos(th))


def motor_plate(center, normal, r=17.0, t=4.0, aft_facing=False):
    plate = cyl(r, (0, 0, 0), (0, 0, 1), t)
    plate = plate.cut(cyl(4.6, (0, 0, -1), (0, 0, 1), t + 2))
    for hx, hy in ((8, 0), (-8, 0), (0, 9.5), (0, -9.5)):
        plate = plate.cut(cyl(1.6, (hx, hy, -1), (0, 0, 1), t + 2))
    z = V(0, 0, 1)
    ax = z.cross(normal)
    ang = math.degrees(math.acos(max(-1, min(1, z.dot(normal)))))
    if ax.Length > 1e-9:
        plate = plate.rotate(V(0, 0, 0), ax, ang)
    return plate.translate(center)


def motor_pod(xm, side, spin):
    yb = side * P.BOOM_Y
    r_s = P.BOOM_OD / 2 + 2.5
    sleeve = cyl(r_s, (xm - 25, yb, P.Z_BOOM), (1, 0, 0), 50)
    n = tilt_normal(xm, yb, spin)
    top = P.Z_BOOM + r_s + 6
    ped = box(xm - 12, xm + 12, yb - 12, yb + 12, P.Z_BOOM, top)
    plate = motor_plate(V(xm, yb, top - 1), n)
    leg = cyl(P.LEG_OD / 2 + 2.5, (xm, yb, P.Z_BOOM - r_s - 22), (0, 0, 1), 22 + r_s)
    part = sleeve.fuse(ped).fuse(plate).fuse(leg)
    part = part.cut(cyl(P.BOOM_OD / 2 + P.CLEAR, (xm - 30, yb, P.Z_BOOM), (1, 0, 0), 60))
    part = part.cut(cyl(P.LEG_OD / 2 + P.CLEAR, (xm, yb, P.Z_BOOM - r_s - 23), (0, 0, 1), 21))
    part = part.cut(box(xm - 8, xm + 8, yb - 13, yb + 13, P.Z_BOOM + r_s + 1, P.Z_BOOM + r_s + 3.5))  # ESC tie slot
    return part


def pusher_mount():
    x_end = P.TAILBOOM_X[1]
    sleeve = cyl(P.TAILBOOM_OD / 2 + 2.5, (x_end - 30, 0, P.Z_TAIL), (1, 0, 0), 30)
    plate = motor_plate(V(x_end, 0, P.Z_TAIL), V(1, 0, 0))
    part = sleeve.fuse(plate)
    return part.cut(cyl(P.TAILBOOM_OD / 2 + P.CLEAR, (x_end - 31, 0, P.Z_TAIL), (1, 0, 0), 30))


def foot(xm, yb):
    f = cyl(7.0, (xm, yb, P.GROUND_Z), (0, 0, 1), 4).fuse(cyl(P.LEG_OD / 2 + 2, (xm, yb, P.GROUND_Z), (0, 0, 1), 18))
    return f.cut(cyl(P.LEG_OD / 2 + P.CLEAR, (xm, yb, P.GROUND_Z + 3), (0, 0, 1), 20))


# --------------------------------------------------------------------------
# assembly, checks, mass/CG
# --------------------------------------------------------------------------
# kind: "skin" (single-wall shell, print 1 perimeter / 0 top-bottom / 4% gyroid),
#       "shell" (already-thin solid, print as-is), "solid" (PETG, 3 walls 25%)
MATERIAL = {"skin": ("LW-PLA", "PLA"), "shell": ("PLA", "PLA"), "solid": ("PETG", "PETG")}


def build_parts():
    parts = {}

    def add(name, shape, kind, count=1):
        parts[name] = {"shape": shape, "kind": kind, "count": count}

    for s, nm in ((1, "R"), (-1, "L")):
        for k, (y0, y1) in enumerate(P.WING_SEGMENTS, start=1):
            seg = wing_segment(y0, y1, s)
            if w_chord(y0) > P.CHORD_SPLIT_ABOVE:
                front = box(-100, P.CHORD_SPLIT_X, -700, 700, -100, 200)
                add(f"wing_{nm}{k}a", seg.intersect(front), "skin")
                add(f"wing_{nm}{k}b", seg.cut(front), "skin")
            else:
                add(f"wing_{nm}{k}", seg, "skin")
        add(f"boom_node_{nm}", boom_node(s), "solid")
        add(f"boom_pylon_{nm}", boom_pylon(s), "solid")
        add(f"elevon_{nm}1", elevon_piece(P.ELEVON_Y[0], P.ELEVON_SPLIT, s), "skin")
        add(f"elevon_{nm}2", elevon_piece(P.ELEVON_SPLIT, P.ELEVON_Y[1], s), "skin")
        add(f"fin_{nm}", fin(s), "skin")
    sections, hatch = build_pod()
    for nm, sh in sections.items():
        add(nm, sh, "shell")
    add("hatch", hatch, "shell")
    centre, tips = stab_parts()
    add("stab_centre", centre, "skin")
    for nm, sh in tips.items():
        add(nm, sh, "skin")
    corners = [("FR", P.X_ROTOR_FRONT, 1, +1), ("RL", P.X_ROTOR_REAR, -1, +1),
               ("FL", P.X_ROTOR_FRONT, -1, -1), ("RR", P.X_ROTOR_REAR, 1, -1)]
    for nm, xm, s, spin in corners:
        add(f"motor_pod_{nm}", motor_pod(xm, s, spin), "solid")
        add(f"foot_{nm}", foot(xm, s * P.BOOM_Y), "solid")
    add("pusher_mount", pusher_mount(), "solid")
    return parts


def part_mass(info, cfg, name=""):
    sh, kind = info["shape"], info["kind"]
    mat = MATERIAL[kind][cfg]
    if cfg == 0 and name in P.POD_MATERIAL_LIGHT:
        mat = P.POD_MATERIAL_LIGHT[name]
    rho = P.RHO[mat] / 1000.0                       # g/mm^3
    vol, area = sh.Volume(), sh.Area()
    if kind == "skin":
        m = area * P.SKIN * rho + 0.04 * vol * rho
    elif kind == "shell":
        m = vol * rho
    else:
        m = vol * rho * 0.45
    return m, mat


def bed_fit(sh):
    bb = sh.BoundingBox()
    dims = sorted([bb.xlen, bb.ylen, bb.zlen])
    bed = sorted(P.BED)
    return all(d <= b for d, b in zip(dims, bed)), (round(bb.xlen), round(bb.ylen), round(bb.zlen))


def carbon_shapes():
    out = {}
    out["main_spar"] = y_cyl(P.SPAR_OD / 2, X_SPAR, Z_SPAR, -P.SPAR_LEN / 2, P.SPAR_LEN / 2)
    out["wing_pins"] = y_cyl(P.PIN_OD / 2, X_PIN, Z_PIN, -P.PIN_HALF, P.PIN_HALF)
    for s in (1, -1):
        out[f"boom_{'R' if s > 0 else 'L'}"] = cyl(P.BOOM_OD / 2, (P.BOOM_X[0], s * P.BOOM_Y, P.Z_BOOM), (1, 0, 0), P.BOOM_X[1] - P.BOOM_X[0])
        for xm in (P.X_ROTOR_FRONT, P.X_ROTOR_REAR):
            out[f"leg_{s}_{int(xm)}"] = cyl(P.LEG_OD / 2, (xm, s * P.BOOM_Y, P.GROUND_Z + 3), (0, 0, 1), P.LEG_LEN)
    out["tailboom"] = cyl(P.TAILBOOM_OD / 2, (P.TAILBOOM_X[0], 0, P.Z_TAIL), (1, 0, 0), P.TAILBOOM_X[1] - P.TAILBOOM_X[0])
    out["stab_spar"] = y_cyl(P.STAB_SPAR_OD / 2, X_STAB_SPAR, P.Z_STAB, -P.B_H / 2 + 10, P.B_H / 2 - 10)
    return out


def mass_properties(parts, cfg):
    rows, pts = [], []
    for name, info in parts.items():
        m, mat = part_mass(info, cfg, name)
        c = info["shape"].Center()
        rows.append({"part": name, "kind": info["kind"], "material": mat, "mass_g": round(m, 1),
                     "x": round(c.x, 1), "y": round(c.y, 1), "z": round(c.z, 1)})
        pts.append((m, c.x, c.y, c.z))
    for name, (od, idd, length, x, y, z, count) in P.CARBON.items():
        m = P.carbon_mass_g(od, idd, length, count)
        rows.append({"part": name, "kind": "carbon", "material": "CF", "mass_g": round(m, 1), "x": x, "y": y, "z": z})
        pts.append((m, x, y, z))
    bat_m = P.COTS["battery_3s_4000"][0]
    for name, (m, x, y, z) in P.COTS.items():
        if x is None:
            continue
        rows.append({"part": name, "kind": "cots", "material": "-", "mass_g": m, "x": x, "y": y, "z": z})
        pts.append((m, x, y, z))
    m0 = sum(p[0] for p in pts)
    mx0 = sum(p[0] * p[1] for p in pts)
    total = m0 + bat_m
    bat_x = (P.X_CG_TARGET * total - mx0) / bat_m
    bat_x_used = min(max(bat_x, P.BATTERY_X_RANGE[0]), P.BATTERY_X_RANGE[1])
    bz = P.COTS["battery_3s_4000"][3]
    pts.append((bat_m, bat_x_used, 0.0, bz))
    rows.append({"part": "battery_3s_4000", "kind": "cots", "material": "-", "mass_g": bat_m,
                 "x": round(bat_x_used, 1), "y": 0, "z": bz})
    cg = [sum(p[0] * p[i] for p in pts) / total for i in (1, 2, 3)]
    ixx = sum(p[0] * ((p[2] - cg[1]) ** 2 + (p[3] - cg[2]) ** 2) for p in pts) * 1e-9   # kg m^2
    iyy = sum(p[0] * ((p[1] - cg[0]) ** 2 + (p[3] - cg[2]) ** 2) for p in pts) * 1e-9
    izz = sum(p[0] * ((p[1] - cg[0]) ** 2 + (p[2] - cg[1]) ** 2) for p in pts) * 1e-9
    printed = sum(r["mass_g"] for r in rows if r["kind"] in ("skin", "shell", "solid"))
    return {
        "config": ["LW-PLA skins + PLA pod + PETG nodes", "all PLA (+PETG nodes)"][cfg],
        "total_g": round(total, 1), "printed_g": round(printed, 1),
        "carbon_g": round(sum(r["mass_g"] for r in rows if r["kind"] == "carbon"), 1),
        "cots_g": round(sum(r["mass_g"] for r in rows if r["kind"] == "cots"), 1),
        "battery_x_needed": round(bat_x, 1), "battery_x_used": round(bat_x_used, 1),
        "battery_in_range": P.BATTERY_X_RANGE[0] <= bat_x <= P.BATTERY_X_RANGE[1],
        "cg_build_mm": [round(v, 1) for v in cg],
        "cg_pct_mac": round(100 * (cg[0] - P.X_LE_MAC) / P.MAC, 1),
        "inertia_kgm2_flu": {"ixx": round(ixx, 4), "iyy": round(iyy, 4), "izz": round(izz, 4)},
        "parts": rows,
    }


def render(parts, carbon, path_prefix):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except Exception as e:  # noqa: BLE001
        print(f"[render] skipped ({e})")
        return
    colours = {"skin": "#d9dde3", "shell": "#8fb3d9", "solid": "#e0a040", "carbon": "#333333"}
    tris_by = {k: [] for k in colours}
    for info in parts.values():
        v, t = info["shape"].tessellate(1.5, 0.5)
        tris_by[info["kind"]] += [[(v[a].x, v[a].y, v[a].z) for a in tri] for tri in t]
    for sh in carbon.values():
        v, t = sh.tessellate(1.5, 0.5)
        tris_by["carbon"] += [[(v[a].x, v[a].y, v[a].z) for a in tri] for tri in t]
    for view, (elev, azim) in {"iso": (22, -125), "side": (0, -90), "top": (90, -90), "front": (0, 180)}.items():
        fig = plt.figure(figsize=(11, 8))
        ax = fig.add_subplot(111, projection="3d")
        for k, tris in tris_by.items():
            if tris:
                ax.add_collection3d(Poly3DCollection(tris, facecolor=colours[k], edgecolor="none",
                                                     alpha=1.0 if k != "skin" else 0.85))
        ax.set_xlim(-250, 760); ax.set_ylim(-505, 505); ax.set_zlim(-505, 505)
        ax.set_box_aspect((1010, 1010, 1010))
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        ax.set_title(f"CoconutQuadplane build model -- {view}")
        fig.savefig(f"{path_prefix}_{view}.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
    print(f"[render] {path_prefix}_*.png")


def main() -> None:
    OUT_PRINT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT_PRINT.glob("*.stl"):          # parts may have been renamed/split
        old.unlink()
    print(f"[geom] spar  X={X_SPAR:.1f} Z={Z_SPAR:.1f}  min skin clearance {SPAR_MARGIN:.1f} mm")
    print(f"[geom] pin   X={X_PIN:.1f} Z={Z_PIN:.1f}  min skin clearance {PIN_MARGIN:.1f} mm")
    if SPAR_MARGIN < 0 or PIN_MARGIN < 0:
        print("[geom] ERROR: a straight rod leaves the wing skin")
        sys.exit(1)
    parts = build_parts()
    problems = []
    for name, info in parts.items():
        sh = info["shape"]
        if not sh.isValid():
            problems.append(f"{name}: invalid solid")
        ok, dims = bed_fit(sh)
        info["dims"] = dims
        if not ok:
            problems.append(f"{name}: {dims} mm does not fit the {P.BED} bed")
        cq.exporters.export(cq.Workplane().add(sh), str(OUT_PRINT / f"{name}.stl"),
                            tolerance=0.1, angularTolerance=0.2)
    carbon = carbon_shapes()
    comp = cq.Compound.makeCompound([i["shape"] for i in parts.values()] + list(carbon.values()))
    comp.exportStep(str(OUT / "coconut_quadplane_build.step"))
    report = {"bed_mm": P.BED, "problems": problems,
              "geometry": {"x_spar": round(X_SPAR, 1), "z_spar": round(Z_SPAR, 1),
                           "spar_margin_mm": round(SPAR_MARGIN, 1),
                           "x_pin": round(X_PIN, 1), "z_pin": round(Z_PIN, 1),
                           "pin_margin_mm": round(PIN_MARGIN, 1),
                           "x_cg_target": round(P.X_CG_TARGET, 1),
                           "x_cg_limits": [round(v, 1) for v in P.X_CG_LIMITS]},
              "part_dims_mm": {n: i["dims"] for n, i in parts.items()},
              "configs": [mass_properties(parts, 0), mass_properties(parts, 1)]}
    (OUT / "mass_properties.json").write_text(json.dumps(report, indent=1))
    for c in report["configs"]:
        print(f"[mass] {c['config']}: total {c['total_g']:.0f} g (printed {c['printed_g']:.0f}, "
              f"carbon {c['carbon_g']:.0f}, COTS {c['cots_g']:.0f}); battery X {c['battery_x_needed']:.0f} mm "
              f"({'ok' if c['battery_in_range'] else 'OUT OF TRAY RANGE'}); CG {c['cg_pct_mac']}% MAC")
    print(f"[parts] {len(parts)} printable parts -> {OUT_PRINT}")
    for p in problems:
        print(f"[CHECK] {p}")
    render(parts, carbon, str(OUT / "preview"))
    print("[done]" if not problems else f"[done with {len(problems)} problems]")


if __name__ == "__main__":
    main()
