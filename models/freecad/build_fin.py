"""
build_fin.py  —  parametric vertical fin for the CoconutQuadplane.

Headless build:
    "E:/proggramming/Freecad/bin/freecadcmd.exe" build_fin.py

Produces vertical_fin.FCStd (+ .step, .stl). Geometry is driven by a
Spreadsheet ("params") so it can be re-tuned in the FreeCAD GUI or via the
FreeCAD-MCP server later. Default dimensions come from the fin-sizing result
in aero/RESULTS.md (target V_V from the Cn_beta analysis).

Profile: the swept planform of the original KCL fin (root chord along X, a
swept leading edge, a short raked tip), scaled to hit a target area.
"""
import math
import FreeCAD as App
import Part

OUTDIR = r"E:\proggramming\semester proj\models\freecad"

# ---- design parameters (edit here or in the Spreadsheet) --------------------
P = dict(
    area_each_cm2=170.0,     # target area PER fin  (aero/RESULTS.md: 340 cm² total)
    aspect_ratio=2.6,        # height^2 / area  (keeps the tall-ish KCL look)
    taper=0.55,              # tip chord / root chord
    le_sweep_deg=22.0,       # leading-edge sweep
    thickness_mm=14.0,       # NACA 0009 max thickness at the target chord
    n_fins=2,                # twin
    fin_gauge_y_mm=230.0,    # half-spacing of the twin fins (from KCL main.kcl)
)


def fin_planform(area_m2, ar, taper, le_sweep_deg):
    """Return (root_chord, tip_chord, height) for a trapezoid of this area."""
    height = math.sqrt(area_m2 * ar)
    c_root = 2 * area_m2 / (height * (1 + taper))
    c_tip = c_root * taper
    return c_root, c_tip, height


def make_fin(doc):
    area = P["area_each_cm2"] * 1e-4
    c_root, c_tip, h = fin_planform(area, P["aspect_ratio"], P["taper"],
                                    P["le_sweep_deg"])
    dx_le = h * math.tan(math.radians(P["le_sweep_deg"]))   # LE offset at tip

    # profile in the X-Z plane (chord along +X, height along +Z), root at z=0
    pts = [
        App.Vector(0, 0, 0),                 # LE root
        App.Vector(c_root, 0, 0),            # TE root
        App.Vector(dx_le + c_tip, 0, h),    # TE tip
        App.Vector(dx_le, 0, h),            # LE tip
        App.Vector(0, 0, 0),
    ]
    wire = Part.makePolygon(pts)
    face = Part.Face(wire)
    solid = face.extrude(App.Vector(0, P["thickness_mm"] / 1000.0, 0))
    solid.translate(App.Vector(0, -P["thickness_mm"] / 2000.0, 0))  # centre on y

    made = []
    for i in range(P["n_fins"]):
        sign = -1 if i == 0 else 1
        s = solid.copy()
        s.translate(App.Vector(0, sign * P["fin_gauge_y_mm"] / 1000.0, 0))
        obj = doc.addObject("Part::Feature", f"VerticalFin{i+1}")
        obj.Shape = s
        made.append(obj)

    return dict(c_root=c_root, c_tip=c_tip, height=h, dx_le=dx_le,
               area_each=area, area_total=area * P["n_fins"], objs=made)


def add_spreadsheet(doc, geo):
    sh = doc.addObject("Spreadsheet::Sheet", "params")
    rows = [
        ("A1", "parameter", "B1", "value", "C1", "unit"),
        ("A2", "area_each", "B2", P["area_each_cm2"], "C2", "cm^2"),
        ("A3", "aspect_ratio", "B3", P["aspect_ratio"], "C3", "-"),
        ("A4", "taper", "B4", P["taper"], "C4", "-"),
        ("A5", "le_sweep", "B5", P["le_sweep_deg"], "C5", "deg"),
        ("A6", "thickness", "B6", P["thickness_mm"], "C6", "mm"),
        ("A7", "root_chord", "B7", round(geo["c_root"] * 1000, 1), "C7", "mm"),
        ("A8", "tip_chord", "B8", round(geo["c_tip"] * 1000, 1), "C8", "mm"),
        ("A9", "height", "B9", round(geo["height"] * 1000, 1), "C9", "mm"),
        ("A10", "area_total", "B10", round(geo["area_total"] * 1e4, 1), "C10", "cm^2"),
    ]
    for r in rows:
        for cell, val in zip(r[::2], r[1::2]):
            sh.set(cell, str(val))
    doc.recompute()


def main():
    doc = App.newDocument("vertical_fin")
    geo = make_fin(doc)
    add_spreadsheet(doc, geo)
    doc.recompute()

    base = OUTDIR + "\\vertical_fin"
    doc.saveAs(base + ".FCStd")
    shp = geo["objs"][0].Shape.fuse(geo["objs"][1].Shape) \
        if len(geo["objs"]) > 1 else geo["objs"][0].Shape
    try:
        Part.export(geo["objs"], base + ".step")
    except Exception as e:
        print("step export skipped:", e)
    try:
        import Mesh
        combined = Mesh.Mesh()
        for o in geo["objs"]:
            combined.addMesh(Mesh.Mesh(o.Shape.tessellate(0.1)))
        combined.write(base + ".stl")
    except Exception as e:
        print("stl export skipped:", e)

    print(f"root chord  : {geo['c_root']*1000:7.1f} mm")
    print(f"tip chord   : {geo['c_tip']*1000:7.1f} mm")
    print(f"height      : {geo['height']*1000:7.1f} mm")
    print(f"LE sweep off: {geo['dx_le']*1000:7.1f} mm")
    print(f"area each   : {geo['area_each']*1e4:7.1f} cm^2")
    print(f"area total  : {geo['area_total']*1e4:7.1f} cm^2  ({P['n_fins']} fins)")
    print(f"model volume: {shp.Volume*1e9:7.0f} mm^3 (solid, both fins)")
    print(f"saved       : {base}.FCStd / .step / .stl")


main()
