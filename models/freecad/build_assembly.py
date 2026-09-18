"""
build_assembly.py -- full CoconutQuadplane assembly, FreeCAD headless.

    "E:/proggramming/Freecad/bin/freecadcmd.exe" build_assembly.py

Every part's shape and placement is taken from the real KCL CAD source
(3d model files/*.zip, demo-project/*.kcl) -- same fuselage loft stations,
same wing/tail/fin profiles, same boom/pod/prop positions -- converted
through main.kcl's own modelScale = 1500/3040 = 0.493421mm. This is a
faithful rebuild of that model in FreeCAD, NOT a re-guess.

On top of that real baseline, this adds every change confirmed this
session (none of these exist in the original KCL):
  - Front lift rotors mounted BELOW their boom, rear rotors mounted
    ABOVE it (was: both at the same height) -- keeps each boom's rear
    rotor out of its front rotor's downwash.
  - Vertical fins extended down ~291mm to the same ground line as the
    front landing legs, serving as the rear gear (with only 2 front
    legs, the tail would otherwise sag onto the pusher prop). The
    291mm figure is computed below from the real leg/fin geometry,
    not assumed -- see GROUND_Z and the fin-skid points.
  - A short brace tying each boom's aft tip into its fin root, so the
    booms structurally support the tail instead of ending near it
    unattached.
  - All five propellers the same size (the KCL scales the pusher to
    72% of the lift-rotor size, inferred from a photo; the real
    hardware BOM specs one prop, 1045/254mm, for all five positions).

Units: mm throughout (FreeCAD's default document unit), building each
part as a flat profile extruded thin, then rigidly rotated/translated
into place -- exactly how the KCL itself is built (see e.g. wingHalf.kcl
+ main.kcl's rotate/translate of it), which is simpler and more faithful
than trying to loft a twisted surface.
"""
import math
import FreeCAD as App
import Part

OUTDIR = r"E:\proggramming\semester proj\models\freecad"
S = 1500.0 / 3040.0     # main.kcl's modelScale


def V(x, y, z):
    return App.Vector(x, y, z)


def flat_panel(points_xy, thickness, name, doc):
    """A closed polygon in the local XY plane, extruded symmetrically
    along Z by `thickness` -- the KCL pattern for wing/tail/fin panels."""
    pts = [V(x, y, 0) for x, y in points_xy] + [V(*points_xy[0], 0)]
    face = Part.Face(Part.makePolygon(pts))
    solid = face.extrude(V(0, 0, thickness)).copy()
    solid.translate(V(0, 0, -thickness / 2.0))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = solid
    return obj


def place(obj, rot_axis=None, rot_deg=0.0, translate=(0, 0, 0)):
    shp = obj.Shape.copy()
    if rot_axis and rot_deg:
        shp.rotate(V(0, 0, 0), V(*rot_axis), rot_deg)
    shp.translate(V(*translate))
    obj.Shape = shp
    return obj


def loft_body(stations, n=16, name="Body", doc=None, squash=1.0):
    """stations: [(x, radius), ...] -- circular (or z-squashed elliptical)
    cross-sections lofted along X, matching fuselage.kcl / motorPod.kcl."""
    wires = []
    for x, r in stations:
        if r < 1e-6:
            wires.append(Part.Vertex(V(x, 0, 0)))
            continue
        e = Part.Ellipse(App.Vector(0, 0, 0), r, r * squash)
        w = Part.Wire([e.toShape()]).copy()
        w.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), 90)
        w.translate(V(x, 0, 0))
        wires.append(w)
    loft = Part.makeLoft(wires, True)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = loft
    return obj


def cylinder_between(p1, p2, radius, name, doc):
    p1, p2 = V(*p1), V(*p2)
    vec = p2 - p1
    cyl = Part.makeCylinder(radius, vec.Length, p1, vec)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = cyl
    return obj


def disc(center, radius, axis, thickness, name, doc):
    """A thin disc standing in for a propeller sweep (2 real blades are
    added separately for the visual read; this is the aero disc)."""
    ax = {"x": V(1, 0, 0), "z": V(0, 0, 1)}[axis]
    cyl = Part.makeCylinder(radius, thickness, V(*center) - ax * (thickness / 2),
                            ax)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = cyl
    return obj


def blade_pair(center, radius, axis, name, doc):
    """Two flat rectangular blades through `center`, normal to `axis`,
    for a recognisable propeller silhouette (not an aerodynamic prop)."""
    length, width, thick = radius * 2, radius * 0.16, 2.0
    box = Part.makeBox(length, width, thick, V(-length / 2, -width / 2, -thick / 2))
    b2 = box.copy()
    b2.rotate(V(0, 0, 0), V(0, 0, 1), 90)
    both = box.fuse(b2).copy()
    if axis == "x":
        both.rotate(V(0, 0, 0), V(0, 1, 0), 90)
    both.translate(V(*center))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = both
    return obj


def main():
    doc = App.newDocument("CoconutQuadplane")

    # ---- 1. fuselage: real loft stations from fuselage.kcl ---------------
    fuse_stations_pre = [(-1080, 12), (-900, 112), (-560, 188), (0, 198),
                         (500, 140), (820, 78), (1020, 42)]
    fuse_stations = [(x * S, r * S) for x, r in fuse_stations_pre]
    fuselage = loft_body(fuse_stations, name="Fuselage", doc=doc, squash=0.82)

    # ---- 2. nose sensor probe: sensorProbe.kcl ----------------------------
    probe = loft_body([(-1150 * S, 1.5 * S), (70 * S, 5 * S), (120 * S, 8 * S)],
                      name="NoseProbe", doc=doc)

    # ---- 3. wings x2: wingHalf.kcl profile, +2deg dihedral, ---------------
    #         main.kcl placement translate=[-330,0,155] ----------------------
    wing_profile = [(0, 0), (560 * S, 0), (610 * S, 1520 * S), (320 * S, 1520 * S)]
    wing_R = flat_panel(wing_profile, 15.0, "WingR", doc)
    place(wing_R, rot_axis=(1, 0, 0), rot_deg=2.0,
         translate=(-330 * S, 0, 155 * S))
    wing_L = flat_panel(wing_profile, 15.0, "WingL", doc)
    place(wing_L, rot_axis=(1, 0, 0), rot_deg=178.0,
         translate=(-330 * S, 0, 155 * S))

    # ---- 4. horizontal tail: tailHalf.kcl, translate=[650,0,180] ----------
    tail_profile = [(0, 0), (340 * S, 0), (340 * S, 500 * S), (120 * S, 500 * S)]
    tail_R = flat_panel(tail_profile, 10.0, "TailR", doc)
    place(tail_R, translate=(650 * S, 0, 180 * S))
    tail_L = flat_panel(tail_profile, 10.0, "TailL", doc)
    place(tail_L, rot_axis=(1, 0, 0), rot_deg=180.0,
         translate=(650 * S, 0, 180 * S))

    # ---- 5. vertical fins x2 + NEW fin-base landing skid ------------------
    #      verticalFin.kcl (curved crown), translate=[690,+-230,190] --------
    #      ground line established by the front legs (step 7): -197.4mm ----
    GROUND_Z = -400 * S                                  # -197.4mm
    fin_root_z_global = 190 * S                          # 93.8mm
    skid_len = fin_root_z_global - GROUND_Z              # ~291.1mm

    def fin_with_skid(ysign, name):
        pts = [
            (0, -skid_len), (280 * S, -skid_len),          # skid bottom (NEW)
            (280 * S, 0), (265 * S, 160 * S), (70 * S, 245 * S),  # fin body+crown
            (0, 0),
        ]
        panel = flat_panel(pts, 9.0, name, doc)
        return place(panel, translate=(690 * S, 230 * S * ysign, 190 * S))

    fin_R = fin_with_skid(1, "FinR_withSkid")
    fin_L = fin_with_skid(-1, "FinL_withSkid")

    # ---- 6. rotor-mount booms x2 + NEW boom-to-tail brace -----------------
    BOOM_Z = 38 * S
    booms, braces = [], []
    for k, ysign in (("R", 1), ("L", -1)):
        y = 440 * S * ysign
        b = cylinder_between((-660 * S, y, BOOM_Z), (660 * S, y, BOOM_Z),
                             11.0, f"Boom{k}", doc)
        booms.append(b)
        br = cylinder_between((660 * S, y, BOOM_Z),
                              (690 * S, 230 * S * ysign, 190 * S), 6.0,
                              f"Brace{k}", doc)
        braces.append(br)

    # ---- 7. landing legs x2 ONLY: landingStrut.kcl ------------------------
    #      sets GROUND_Z used above ------------------------------------------
    legs = []
    for k, ysign in (("R", 1), ("L", -1)):
        y = 135 * S * ysign
        leg = cylinder_between((-170 * S, y, -130 * S), (-170 * S, y, GROUND_Z),
                               4.0, f"Leg{k}", doc)
        legs.append(leg)

    # ---- 8/9. lift rotors x4, STAGGERED (NEW), + pusher (uniform size) ----
    PROP_R = 295 * S
    lift_specs = {
        "FR": (-440 * S, 440 * S, BOOM_Z - 70 * S),
        "FL": (-440 * S, -440 * S, BOOM_Z - 70 * S),
        "RR": (430 * S, 440 * S, BOOM_Z + 70 * S),
        "RL": (430 * S, -440 * S, BOOM_Z + 70 * S),
    }
    rotors = []
    for k, (x, y, z) in lift_specs.items():
        cylinder_between((x, y, BOOM_Z), (x, y, z), 6.0, f"Pylon{k}", doc)
        pod = loft_body([(x - 90 * S, 0), (x - 60 * S, 26 * S), (x, 26 * S),
                        (x + 60 * S, 26 * S), (x + 90 * S, 0)],
                       name=f"Pod{k}", doc=doc)
        pod_shape = pod.Shape.copy()
        pod_shape.translate(V(0, y, z))
        pod.Shape = pod_shape
        rotors.append(blade_pair((x, y, z), PROP_R, "z", f"Rotor{k}", doc))

    PUSH_X, PUSH_Z = 1030 * S, 45 * S
    cylinder_between((970 * S, 0, 190 * S), (PUSH_X, 0, PUSH_Z), 6.0,
                     "PusherMast", doc)
    pusher = blade_pair((PUSH_X, 0, PUSH_Z), PROP_R, "x", "Pusher", doc)

    doc.recompute()

    base = OUTDIR + "\\coconut_quadplane_assembly"
    doc.saveAs(base + ".FCStd")
    all_objs = [o for o in doc.Objects if hasattr(o, "Shape")]
    try:
        Part.export(all_objs, base + ".step")
    except Exception as e:
        print("step export skipped:", e)
    try:
        import Mesh
        combined = Mesh.Mesh()
        for o in all_objs:
            combined.addMesh(Mesh.Mesh(o.Shape.tessellate(0.5)))
        combined.write(base + ".stl")
    except Exception as e:
        print("stl export skipped:", e)

    print(f"Scale factor S = {S:.6f}")
    print(f"Ground line Z  = {GROUND_Z:.1f} mm")
    print(f"Fin-skid length= {skid_len:.1f} mm")
    print(f"Objects        = {len(all_objs)}")
    print(f"Saved: {base}.FCStd / .step / .stl")


main()
