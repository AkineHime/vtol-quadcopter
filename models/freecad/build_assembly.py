"""
build_assembly.py -- full CoconutQuadplane solid assembly, FreeCAD headless.

    "E:/proggramming/Freecad/bin/freecadcmd.exe" build_assembly.py

Read DESIGN_NOTES.md alongside this file before changing anything --
every number and decision below is explained and sourced there. This
pair of files is the whole spec: this script IS the model, the notes
file IS the reasoning. Nothing else in models/freecad/ should be needed.

Units: mm throughout (FreeCAD's default). Build convention, verified
against the real KCL source part by part (see DESIGN_NOTES.md "Sketch
plane per part" table): each lifting surface (wing/tail/fin) is built
as a flat 2D profile in a LOCAL sketch plane, extruded thin normal to
that plane, then rotated/mirrored/translated into place as a rigid
body -- exactly how the KCL itself is built. Getting each part's local
sketch plane right is the one thing that broke last time (the fin was
built like a wing and never rotated upright); every part below states
its local-axis convention in a comment so that mistake is checkable.
"""
import FreeCAD as App
import Part

OUTDIR = r"E:\proggramming\semester proj\models\freecad"
S = 1500.0 / 3040.0     # main.kcl's modelScale (real, from the KCL source)


def V(x, y, z):
    return App.Vector(x, y, z)


def flat_panel(points_2d, thickness, name, doc):
    """A closed polygon in the LOCAL XY plane, extruded symmetrically
    along LOCAL Z by `thickness`. This is only ever the shape-builder;
    which global axis local-X/Y/Z end up on is decided entirely by the
    rotation passed to place() -- see the per-part comments below."""
    pts = [V(x, y, 0) for x, y in points_2d] + [V(*points_2d[0], 0)]
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


def mirror_y(obj, name, doc):
    """An exact mirror across the XZ plane (Y -> -Y) -- used for every
    left/right part instead of a near-180-degree rotation trick, so the
    two sides are guaranteed identical instead of trusting an angle."""
    shp = obj.Shape.copy().mirror(V(0, 0, 0), V(0, 1, 0))
    new = doc.addObject("Part::Feature", name)
    new.Shape = shp
    return new


def loft_body(stations, name, doc, squash=1.0):
    """stations: [(x, radius), ...], lofted along GLOBAL X (fuselage.kcl /
    motorPod.kcl convention) -- each station is a Y-Z ellipse (radius in Y,
    radius*squash in Z), so this one is built directly in global space,
    no local-frame rotation needed."""
    wires = []
    for x, r in stations:
        if r < 1e-6:
            wires.append(Part.Vertex(V(x, 0, 0)))
            continue
        e = Part.Ellipse(App.Vector(0, 0, 0), r, r * squash)
        w = Part.Wire([e.toShape()]).copy()
        w.rotate(App.Vector(0, 0, 0), App.Vector(0, 1, 0), 90)  # normal -> +X
        w.translate(V(x, 0, 0))
        wires.append(w)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.makeLoft(wires, True)
    return obj


def cylinder_between(p1, p2, radius, name, doc):
    p1, p2 = V(*p1), V(*p2)
    vec = p2 - p1
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.makeCylinder(radius, vec.Length, p1, vec)
    return obj


def blade_pair(center, radius, axis, name, doc):
    """Two flat rectangular blades through `center`, normal to `axis` --
    a recognisable propeller silhouette, not an aerodynamic prop."""
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

    # ==== 1. FUSELAGE -- fuselage.kcl loft stations (global-X convention) ==
    fuse_stations = [(x * S, r * S) for x, r in
                     [(-1080, 12), (-900, 112), (-560, 188), (0, 198),
                      (500, 140), (820, 78), (1020, 42)]]
    loft_body(fuse_stations, "Fuselage", doc, squash=0.82)

    # ==== 2. NOSE PROBE -- sensorProbe.kcl (global-X convention) ===========
    loft_body([(-1150 * S, 1.5 * S), (70 * S, 5 * S), (120 * S, 8 * S)],
             "NoseProbe", doc)

    # ==== 3. WINGS -- wingHalf.kcl: sketch "on XY" => local(x,y) = ==========
    #    (chord, span). Extrude normal to sketch plane = local Z = thin. ====
    #    Right wing: rotate +2deg about X for dihedral, then translate.
    #    Left wing: built by mirroring the placed right wing (Y -> -Y),
    #    NOT a near-180deg rotation -- guarantees an exact mirror image.
    wing_profile = [(0, 0), (560 * S, 0), (610 * S, 1520 * S), (320 * S, 1520 * S)]
    wing_R = flat_panel(wing_profile, 15.0, "WingR", doc)
    place(wing_R, rot_axis=(1, 0, 0), rot_deg=2.0,
         translate=(-330 * S, 0, 155 * S))
    mirror_y(wing_R, "WingL", doc)

    # ==== 4. HORIZONTAL TAIL -- tailHalf.kcl: same XY-sketch convention ====
    #    as the wing (chord, span), no dihedral. Mirror for the left half.
    tail_profile = [(0, 0), (340 * S, 0), (340 * S, 500 * S), (120 * S, 500 * S)]
    tail_R = flat_panel(tail_profile, 10.0, "TailR", doc)
    place(tail_R, translate=(650 * S, 0, 180 * S))
    mirror_y(tail_R, "TailL", doc)

    # ==== 5. VERTICAL FINS -- verticalFin.kcl: sketch is "on XZ" => local ==
    #    (x,y) fed into flat_panel means (chord, HEIGHT), not (chord, span)
    #    like the wing/tail above. That's the bug from last time: this
    #    panel was placed with translate() only, so its "height" axis
    #    stayed as global Y (spanwise) instead of becoming global Z (up).
    #    Fix: rotate +90deg about X first. That maps local Y (height) onto
    #    global Z (up) and local Z (the thin extrusion) onto global Y
    #    (spanwise-thin) -- verify: Ry'=Y*cos90-Z*sin90=-Z (small, correct,
    #    spanwise-thin); Z'=Y*sin90+Z*cos90=Y (height -> up, correct).
    #    No fin-base landing skid in this version -- see DESIGN_NOTES.md,
    #    gear is 4 legs instead (section 6 below).
    #    CHANGED this pass: Y moved from 230*S (113.5mm, inboard -- read
    #    as "fins at the center") out to the tailplane's own half-span,
    #    500*S (246.7mm) -- so the keel sits at the tailplane's tip, not
    #    partway in. See DESIGN_NOTES.md sec 3 for the verification.
    FIN_Y = 500 * S   # 246.7mm -- the tailplane's real tip, not 230*S
    fin_profile = [(0, 0), (280 * S, 0), (265 * S, 160 * S), (70 * S, 245 * S)]
    fin_R = flat_panel(fin_profile, 9.0, "FinR", doc)
    place(fin_R, rot_axis=(1, 0, 0), rot_deg=90.0,
         translate=(690 * S, FIN_Y, 190 * S))
    mirror_y(fin_R, "FinL", doc)

    # ==== 6. ROTOR-MOUNT BOOMS x2 + boom-to-fin brace (global convention) ==
    #    CHANGED this pass: the boom's Y (spanwise position, 440*S) is
    #    unchanged from the real KCL, but the rotor mount points along
    #    it are pushed further fore/aft -- at the old +-217/212mm they
    #    overlapped the wing chord by 46-54mm (verified: at Y=217mm the
    #    wing spans LE=-117 to TE=121, but the old rotor discs, radius
    #    145.6mm, reached to -71 and +67 -- inside the wing). New
    #    positions clear the wing chord by a 40mm margin on each side
    #    (see LIFT dict below); the boom itself is lengthened to match.
    BOOM_Z = 38 * S
    BOOM_Y = 440 * S
    BOOM_TIP_X = 330.0
    for ysign in (1, -1):
        y = BOOM_Y * ysign
        cylinder_between((-BOOM_TIP_X, y, BOOM_Z), (BOOM_TIP_X, y, BOOM_Z),
                         11.0, f"Boom{'R' if ysign > 0 else 'L'}", doc)
        cylinder_between((BOOM_TIP_X, y, BOOM_Z),
                         (690 * S, FIN_Y * ysign, 190 * S), 6.0,
                         f"Brace{'R' if ysign > 0 else 'L'}", doc)

    # ==== 7. LANDING LEGS x4 -- CHANGED this pass: rear legs now mount ====
    #    on the main fuselage body (not the booms). Front legs are the
    #    real landingStrut.kcl/main.kcl position, unchanged. Rear legs
    #    are at fuselage station x=200mm (real local fuselage radius
    #    there, interpolated from the loft stations, is 74.5mm -- wider
    #    than the leg's 66.6mm spanwise offset, so it mounts flush on
    #    the fuselage belly, same spanwise spacing as the front legs,
    #    not out at the boom).
    GROUND_Z = -400 * S     # -197.4mm, from the front legs (unchanged)
    REAR_LEG_X = 200.0
    for ysign in (1, -1):
        cylinder_between((-170 * S, 135 * S * ysign, -130 * S),
                         (-170 * S, 135 * S * ysign, GROUND_Z), 4.0,
                         f"LegFront{'R' if ysign > 0 else 'L'}", doc)
        cylinder_between((REAR_LEG_X, 135 * S * ysign, -20.0),
                         (REAR_LEG_X, 135 * S * ysign, GROUND_Z), 4.0,
                         f"LegRear{'R' if ysign > 0 else 'L'}", doc)

    # ==== 8. LIFT ROTORS x4, staggered front-low/rear-high (global) =======
    #    CHANGED this pass: X positions moved out to -302.7 / +306.2mm
    #    (from -217.1 / +212.2mm) so the rotor discs (radius 145.6mm)
    #    clear the wing chord (LE=-117.1, TE=120.6mm at this boom Y)
    #    with a 40mm margin instead of overlapping it by 46-54mm.
    PROP_R = 295 * S
    lift_specs = {"FR": (-302.7, BOOM_Y, BOOM_Z - 70 * S),
                 "FL": (-302.7, -BOOM_Y, BOOM_Z - 70 * S),
                 "RR": (306.2, BOOM_Y, BOOM_Z + 70 * S),
                 "RL": (306.2, -BOOM_Y, BOOM_Z + 70 * S)}
    for k, (x, y, z) in lift_specs.items():
        cylinder_between((x, y, BOOM_Z), (x, y, z), 6.0, f"Pylon{k}", doc)
        pod = loft_body([(-90 * S, 0), (-60 * S, 26 * S), (0, 26 * S),
                        (60 * S, 26 * S), (90 * S, 0)], f"Pod{k}", doc)
        pod_shape = pod.Shape.copy()
        pod_shape.translate(V(x, y, z))
        pod.Shape = pod_shape
        blade_pair((x, y, z), PROP_R, "z", f"Rotor{k}", doc)

    # ==== 9. PUSHER -- same size as the lift rotors (uniform hardware) ====
    PUSH_X, PUSH_Z = 1030 * S, 45 * S
    cylinder_between((970 * S, 0, 190 * S), (PUSH_X, 0, PUSH_Z), 6.0,
                     "PusherMast", doc)
    blade_pair((PUSH_X, 0, PUSH_Z), PROP_R, "x", "Pusher", doc)

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

    def wing_chord_at_y(y):
        le_root, le_tip = -330 * S, -330 * S + 320 * S
        te_root, te_tip = -330 * S + 560 * S, -330 * S + 610 * S
        frac = y / (1520 * S)
        return (le_root + frac * (le_tip - le_root),
               te_root + frac * (te_tip - te_root))

    le, te = wing_chord_at_y(BOOM_Y)
    front_clear = (le) - (lift_specs["FR"][0] + PROP_R)
    rear_clear = (lift_specs["RR"][0] - PROP_R) - te
    print(f"Scale factor S     = {S:.6f}")
    print(f"Ground line Z      = {GROUND_Z:.1f} mm")
    print(f"Legs               = 4 (2 front on fuselage, 2 rear on fuselage)")
    print(f"Fin/keel Y         = {FIN_Y:.1f} mm (tailplane tip = {500*S:.1f} mm)")
    print(f"Wing chord at boom Y={BOOM_Y:.1f}: LE={le:.1f} TE={te:.1f}")
    print(f"Front rotor->wing clearance = {front_clear:.1f} mm (was -45.6, i.e. overlapping)")
    print(f"Rear rotor->wing clearance  = {rear_clear:.1f} mm (was -54.0, i.e. overlapping)")
    print(f"Objects            = {len(all_objs)}")
    print(f"Saved: {base}.FCStd / .step / .stl")


main()
