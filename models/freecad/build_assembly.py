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
import math
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


def cone_between(p1, p2, r1, r2, name, doc):
    """Like cylinder_between but tapers from r1 (at p1) to r2 (at p2) --
    for a joint between two differently-sized members that should read
    as one continuous piece instead of an abrupt step."""
    p1, p2 = V(*p1), V(*p2)
    vec = p2 - p1
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.makeCone(r1, r2, vec.Length, p1, vec)
    return obj


def round_edges(obj, radius):
    """Best-effort fillet of every edge on a part -- softens the sharp
    mitred corners flat_panel/loft leave behind. Wrapped because OCC's
    fillet can refuse a radius that's too large for some short edge on
    a tapered tip; skipping there is fine (that part just stays sharp),
    it should never abort the whole build."""
    try:
        obj.Shape = obj.Shape.makeFillet(radius, obj.Shape.Edges)
    except Exception as e:
        print(f"  (fillet skipped on {obj.Name}: {e})")


def propeller(center, radius, axis, name, doc):
    """Two tapered blades (root wider than tip) plus a real hub mass --
    a recognisable 2-blade prop silhouette, replacing the bare
    rectangular cross this used to be. Still schematic: flat blades,
    no aerodynamic twist -- flagged in DESIGN_NOTES.md."""
    hub_r, hub_h = radius * 0.11, 10.0
    root_w, tip_w, thick = radius * 0.16, radius * 0.05, 2.5

    def blade(sign):
        pts = [V(sign * hub_r, -root_w / 2, 0), V(sign * radius, -tip_w / 2, 0),
               V(sign * radius, tip_w / 2, 0), V(sign * hub_r, root_w / 2, 0)]
        face = Part.Face(Part.makePolygon(pts + [pts[0]]))
        return face.extrude(V(0, 0, thick)).copy()

    both = blade(1).fuse(blade(-1))
    hub = Part.makeCylinder(hub_r, hub_h, V(0, 0, -hub_h / 2.0), V(0, 0, 1))
    both = both.fuse(hub).removeSplitter().copy()
    both.translate(V(0, 0, -thick / 2.0))
    if axis == "x":
        both.rotate(V(0, 0, 0), V(0, 1, 0), 90)
    both.translate(V(*center))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = both
    round_edges(obj, 1.5)
    return obj


def stud_ring(center, axis, ring_r, name, doc, n=6, stud_r=1.6, stud_h=3.0):
    """A ring of small cylindrical studs around a tube-to-tube joint --
    a visible fastener detail so two tubes read as bolted together
    instead of just touching. `axis` follows the same convention as
    motor_can/propeller: "x" rotates the ring (built flat in local XY)
    so it faces along global X; anything else leaves it facing Z."""
    studs = None
    for i in range(n):
        ang = math.radians(360.0 * i / n)
        px, py = ring_r * math.cos(ang), ring_r * math.sin(ang)
        c = Part.makeCylinder(stud_r, stud_h, V(px, py, -stud_h / 2.0), V(0, 0, 1))
        studs = c if studs is None else studs.fuse(c)
    shp = studs.copy()
    if axis == "x":
        shp.rotate(V(0, 0, 0), V(0, 1, 0), 90)
    shp.translate(V(*center))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shp
    return obj


def motor_can(center, axis, bell_r, bell_h, shaft_r, shaft_h, name, doc):
    """A stepped two-diameter cylinder (motor bell + shaft) standing in
    for a real motor -- schematic, but a visibly distinct mounted
    component instead of the bare round shape it replaces."""
    total = bell_h + shaft_h
    bell = Part.makeCylinder(bell_r, bell_h, V(0, 0, -total / 2.0), V(0, 0, 1))
    shaft = Part.makeCylinder(shaft_r, shaft_h, V(0, 0, -total / 2.0 + bell_h), V(0, 0, 1))
    both = bell.fuse(shaft).removeSplitter().copy()
    if axis == "x":
        both.rotate(V(0, 0, 0), V(0, 1, 0), 90)
    both.translate(V(*center))
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = both
    round_edges(obj, 1.0)
    return obj


def main():
    doc = App.newDocument("CoconutQuadplane")

    # ---- shared layout constants (computed once, used by several parts
    #      below -- see DESIGN_NOTES.md sec 8-10 for how each was chosen) --
    BOOM_Z = 38 * S            # 18.8mm -- boom height, unchanged from KCL
    BOOM_Y = 440 * S           # 217.1mm -- boom spanwise position, unchanged
    PROP_R = 295 * S           # 145.6mm -- uniform prop radius, all 5 rotors
    REAR_ROTOR_X = 306.2       # from the wing-clearance fix, previous pass
    # BOOM_AFT_X SHORTENED this pass: it used to reach 555mm specifically
    # to run straight into the tail (560mm) -- but the boom and the tail
    # never actually touched (only a 5mm gap, and the tail's mounting
    # geometry doesn't reach back to meet it), so it read as two bare
    # tube ends floating apart. Team's call: stop trying to make the
    # boom itself reach the tail -- shorten it back to just past its own
    # rotor mount (REAR_ROTOR_X=306.2, +24mm of overhang, matching the
    # boom's original real length before that extension).
    #
    # REVERSED this pass: a tapered strut connecting the boom to the tail
    # (sec. 12-13) was built, then explicitly rejected -- "do not connect
    # it to the back wings." The boom does not reach toward the tail at
    # all any more; see sec. 14 for what replaced it (a pillar up to the
    # MAIN wing instead).
    BOOM_AFT_X = 330.0
    TAIL_X = 560.0             # tail root LE mount, on the tailboom rod
    TAIL_ROOT_CHORD = 340 * S  # 167.8mm -- real tail root chord (KCL)
    WING_TE_X = TAIL_X + TAIL_ROOT_CHORD   # 727.8mm -- tail trailing edge;
    #    unswept (KCL's TE is a straight line across the whole span), so
    #    this one X value is the tail's aft-most point at every span station.
    FIN_Y = 500 * S            # 246.7mm -- tailplane's real tip (unchanged)
    FUSE_TIP_X = 1020 * S      # 503.4mm -- the REAL fuselage's own tail tip

    # Fin moved AFT along the tail's own chord this pass (was flush with
    # the tail's leading edge) -- see DESIGN_NOTES.md sec 10.1.
    FIN_CHORD = 138.2          # real KCL fin root chord, unchanged
    FIN_MARGIN = 10.0          # fin's aft edge stays this far short of the
    #    tail's own trailing edge -- "at the back, not completely at the end"
    FIN_X = TAIL_X + TAIL_ROOT_CHORD - FIN_CHORD - FIN_MARGIN   # 579.6mm

    # Pusher pulled way in this pass -- was 900mm (172mm clear of the tail),
    # now just past the tail's real trailing edge with a small motor+shaft
    # in between. See DESIGN_NOTES.md sec 10.2.
    #
    # ROD_R fixed this pass: the rod itself is 14mm, but the motor bell
    # that continues it was 13mm -- a millimeter NARROWER, so the rod
    # stepped IN right where the motor began instead of running straight
    # into it. That's what read as "not aligned" -- the centerline was
    # always correct (verified: rod/motor/prop share Y=0, Z=18.75mm
    # exactly), but the visible radius made the joint look like a kink.
    # Bell now matches the rod's own radius exactly (flush, no step);
    # only the shaft narrows down from there, as a real motor shaft would.
    ROD_R = 14.0
    PUSH_GAP = 2.0                              # rod-to-wing clearance
    PUSH_BELL_R, PUSH_BELL_H = ROD_R, 6.0
    PUSH_SHAFT_R, PUSH_SHAFT_H = 7.0, 4.0
    PUSH_MOTOR_LEN = PUSH_BELL_H + PUSH_SHAFT_H  # 10.0mm
    ROD_TIP_X = WING_TE_X + PUSH_GAP             # 729.8mm
    PUSH_MOTOR_X = ROD_TIP_X + PUSH_MOTOR_LEN / 2.0
    PUSH_X = ROD_TIP_X + PUSH_MOTOR_LEN          # 739.8mm -- propeller hub

    LIFT_BELL_R, LIFT_BELL_H = 18.0, 10.0
    LIFT_SHAFT_R, LIFT_SHAFT_H = 8.0, 8.0

    BOOM_R = 11.0

    # WING PILLARS -- one per boom at first, now TWO per boom (front +
    # back) for a proper two-point mount instead of a single pivot that
    # could still rock. The boom sits at a fixed BOOM_Z=18.8mm along its
    # whole length, but the MAIN wing (2-degree dihedral, root at
    # Z=155*S) is nowhere near that height -- at the boom's own spanwise
    # station (BOOM_Y) the wing's underside works out to ~76.6mm,
    # verified below by computing the exact same rotate-then-translate
    # transform place() applies to the wing. That ~58mm vertical gap is
    # why the boom originally read as "floating in midair".
    # PILLAR_X_FRONT/BACK sit inside the wing's chord at that station
    # (-117.2mm LE to +121.1mm TE), spaced well apart from each other
    # and from either edge, and both well within the boom's own span
    # (-340 to 330mm).
    def wing_underside_z(y):
        th = math.radians(2.0)               # wing's own dihedral angle
        cy = y / math.cos(th)                # inverse of place()'s rotation
        return cy * math.sin(th) - (15.0 / 2.0) * math.cos(th) + 155 * S

    PILLAR_R = 7.0
    PILLAR_X_FRONT = -70.0
    PILLAR_X_BACK = 70.0
    PILLAR_TOP_Z = wing_underside_z(BOOM_Y)

    # Landing legs SPLAYED this pass -- were plumb-vertical, which looks
    # (and structurally is) less stable than a splayed stance. Real
    # landing gear typically splays outward from the mount so the
    # ground-contact points sit wider than the airframe attachment,
    # spreading side-load better. LEG_SPLAY is the extra outward (Y) and
    # fore/aft (X) offset at the ground relative to the top mount --
    # front legs splay forward+outward, rear legs splay aft+outward, so
    # all four points push away from the CG in both directions (a true
    # four-point stable stance, not just parallel posts).
    LEG_SPLAY_Y = 35.0
    LEG_SPLAY_X = 25.0

    # ==== 1. FUSELAGE -- fuselage.kcl loft stations (global-X convention) ==
    #    Real KCL stations end-to-end, no stretch (kept from the previous
    #    pass -- the team confirmed this is right: the fuselage's own
    #    aerodynamic shape stays untouched, everything aft rides a separate
    #    rod). round_edges softens the loft's end-cap seams -- the "rounded"
    #    look this pass, see sec 10.4.
    fuse_stations = [(x * S, r * S) for x, r in
                     [(-1080, 12), (-900, 112), (-560, 188), (0, 198),
                      (500, 140), (820, 78), (1020, 42)]]     # all real, KCL
    fuselage = loft_body(fuse_stations, "Fuselage", doc, squash=0.82)
    round_edges(fuselage, 3.0)

    # ==== 1b. TAILBOOM ROD -- now ends at ROD_TIP_X, not a fixed +20mm past
    #    the old pusher mount. Shortened from 416.7mm to ~226mm this pass
    #    by bringing the pusher assembly up against the tail instead of
    #    leaving it 172mm clear -- see DESIGN_NOTES.md sec 10.2. Radius
    #    (14mm) unchanged -- still real relative to the lift-booms (11mm)
    #    and the fuselage tip it springs from (20.7mm).
    #
    #    FIXED this pass (real bug, not the earlier radius issue): the rod
    #    started at (FUSE_TIP_X, 0, BOOM_Z=18.8mm) -- but the fuselage's
    #    own centerline there is Z=0, and its cross-section at that X is
    #    only +-18.15mm (checked via Shape.slice), so the rod's top edge
    #    stuck out 14.6mm past the fuselage's own surface while its
    #    bottom half was buried inside -- a visibly lopsided joint (this
    #    is what the screenshots showed as "not aligned"). Fixed by
    #    starting the rod AT the fuselage's real axis (Z=0, concentric
    #    with its taper) and angling it gently up to the tail's mount
    #    height (BOOM_Z) at the far end -- a shallow ~4.8-degree rise
    #    over its ~227mm length, not a kink.
    cylinder_between((FUSE_TIP_X, 0, 0), (ROD_TIP_X, 0, BOOM_Z), ROD_R,
                     "TailBoomRod", doc)
    stud_ring((FUSE_TIP_X, 0, 0), "x", ROD_R, "StudFuseRod", doc)

    # ==== 2. NOSE PROBE -- sensorProbe.kcl (global-X convention) ===========
    #    No fillet here -- its own nose-tip radius (0.74mm) is smaller than
    #    any fillet worth applying.
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
    round_edges(wing_R, 2.0)
    mirror_y(wing_R, "WingL", doc)

    # ==== 4. HORIZONTAL TAIL -- tailHalf.kcl profile, same XY-sketch =======
    #    convention as the wing (chord, span). Mount point (TAIL_X, 0,
    #    BOOM_Z) unchanged this pass -- only the fin and pusher moved
    #    relative to it, not the tail itself.
    tail_profile = [(0, 0), (340 * S, 0), (340 * S, 500 * S), (120 * S, 500 * S)]
    tail_R = flat_panel(tail_profile, 10.0, "TailR", doc)
    place(tail_R, translate=(TAIL_X, 0, BOOM_Z))
    round_edges(tail_R, 2.0)
    mirror_y(tail_R, "TailL", doc)

    # ==== 5. VERTICAL FINS -- verticalFin.kcl: sketch is "on XZ" => local ==
    #    (x,y) fed into flat_panel means (chord, HEIGHT), not (chord, span)
    #    like the wing/tail above. Fix (from the earlier orientation bug):
    #    rotate +90deg about X first, mapping local Y (height) onto global
    #    Z (up) and local Z (the thin extrusion) onto global Y
    #    (spanwise-thin).
    #
    #    CHANGED this pass: mounted at FIN_X (579.6mm), not TAIL_X (560mm)
    #    -- moved aft along the tail's own chord so the fin sits toward the
    #    tail's trailing edge ("at the back of the wing... not completely
    #    at the end, like their planes") instead of flush with its leading
    #    edge. See DESIGN_NOTES.md sec 10.1. FIN_Y (tailplane's real tip)
    #    unchanged -- this is a chordwise move only.
    def fin_piece(height, name):
        frac = abs(height) / 90.0     # tip-chord taper scales with |height|,
        pts = [(0, 0), (138.2, 0), (100 * frac, height), (40 * frac, height)]
        panel = flat_panel(pts, 9.0, name, doc)
        place(panel, rot_axis=(1, 0, 0), rot_deg=90.0,
             translate=(FIN_X, FIN_Y, BOOM_Z))
        round_edges(panel, 1.5)
        return panel

    fin_up_R = fin_piece(90.0, "FinUpR")
    mirror_y(fin_up_R, "FinUpL", doc)
    fin_dn_R = fin_piece(-60.0, "FinDownR")
    mirror_y(fin_dn_R, "FinDownL", doc)

    # ==== 6. ROTOR-MOUNT BOOMS x2 (global convention) ======================
    #    SHORTENED this pass, back to just past the rear rotor's own mount
    #    (BOOM_AFT_X, see the constant's comment above) -- it no longer
    #    reaches anywhere near the tail on its own.
    for ysign in (1, -1):
        y = BOOM_Y * ysign
        cylinder_between((-340.0, y, BOOM_Z), (BOOM_AFT_X, y, BOOM_Z),
                         BOOM_R, f"Boom{'R' if ysign > 0 else 'L'}", doc)

    # ==== 6b. WING PILLARS x4 -- TWO per boom this pass ====================
    #    The team rejected the boom-to-tail strut outright ("do not
    #    connect it to the back wings") once they realized the boom was
    #    never attached to anything real in the first place -- it needs
    #    to pick up load from the MAIN wing, not reach aft to the tail.
    #    A single pillar (previous pass) was still just one pivot point --
    #    CHANGED this pass to two per boom, one at the wing's front
    #    (PILLAR_X_FRONT) and one at its back (PILLAR_X_BACK), for a real
    #    two-point mount that resists fore-aft rocking on its own instead
    #    of relying on the stud bracing at a single joint. Each embeds
    #    2mm into the wing's solid at the top (same fillet-inset lesson
    #    as sec. 13) and 2mm into the boom at the bottom, with a stud
    #    pair (front/back, sec. 15's fix) at each end.
    PILLAR_EMBED = 2.0
    for ysign in (1, -1):
        y = BOOM_Y * ysign
        side = "R" if ysign > 0 else "L"
        for px, tag in ((PILLAR_X_FRONT, "Front"), (PILLAR_X_BACK, "Back")):
            bot = (px, y, BOOM_Z - PILLAR_EMBED)
            top = (px, y, PILLAR_TOP_Z + PILLAR_EMBED)
            cylinder_between(bot, top, PILLAR_R, f"WingPillar{tag}{side}", doc)
            stud_ring((px, y, BOOM_Z), "z", PILLAR_R, f"StudPillar{tag}Boom{side}",
                     doc, n=2, stud_r=3.0, stud_h=5.0)
            stud_ring((px, y, PILLAR_TOP_Z), "z", PILLAR_R, f"StudPillar{tag}Wing{side}",
                     doc, n=2, stud_r=3.0, stud_h=5.0)

    # ==== 7. LANDING LEGS x4 -- SPLAYED this pass ==========================
    #    Ground-contact points moved outward (Y) and fore/aft (X) from
    #    their top mounts -- front legs splay forward+outward, rear legs
    #    splay aft+outward -- so the footprint is a stable four-point
    #    stance instead of four parallel vertical posts. Stud rings added
    #    at each top mount (fuselage joint).
    GROUND_Z = -400 * S     # -197.4mm, from the front legs (unchanged)
    REAR_LEG_X = 200.0
    for ysign in (1, -1):
        front_top = (-170 * S, 135 * S * ysign, -130 * S)
        front_gnd = (front_top[0] - LEG_SPLAY_X, front_top[1] + LEG_SPLAY_Y * ysign, GROUND_Z)
        cylinder_between(front_top, front_gnd, 4.0,
                         f"LegFront{'R' if ysign > 0 else 'L'}", doc)
        stud_ring(front_top, "z", 4.0, f"StudLegFront{'R' if ysign > 0 else 'L'}",
                 doc, n=4, stud_r=1.0, stud_h=1.8)

        rear_top = (REAR_LEG_X, 135 * S * ysign, -20.0)
        rear_gnd = (rear_top[0] + LEG_SPLAY_X, rear_top[1] + LEG_SPLAY_Y * ysign, GROUND_Z)
        cylinder_between(rear_top, rear_gnd, 4.0,
                         f"LegRear{'R' if ysign > 0 else 'L'}", doc)
        stud_ring(rear_top, "z", 4.0, f"StudLegRear{'R' if ysign > 0 else 'L'}",
                 doc, n=4, stud_r=1.0, stud_h=1.8)

    # ==== 8. LIFT ROTORS x4, staggered front-low/rear-high (global) =======
    #    X positions (wing-clearance fix) and Z stagger unchanged this
    #    pass. NEW: a motor_can at each mount point (was a bare pod +
    #    propeller meeting with nothing between them) and the propeller
    #    itself rebuilt with a real hub -- see DESIGN_NOTES.md sec 10.3.
    lift_specs = {"FR": (-302.7, BOOM_Y, BOOM_Z - 70 * S),
                 "FL": (-302.7, -BOOM_Y, BOOM_Z - 70 * S),
                 "RR": (REAR_ROTOR_X, BOOM_Y, BOOM_Z + 70 * S),
                 "RL": (REAR_ROTOR_X, -BOOM_Y, BOOM_Z + 70 * S)}
    #    Stud rings at BOTH of each pylon's joints this pass: where it
    #    meets its boom (was already added) and, NEW, where it meets its
    #    pod (previously the two tubes just crossed with nothing joining
    #    them -- flagged as skipped last pass for being too small a
    #    scale, added now on request with a smaller stud size to match).
    for k, (x, y, z) in lift_specs.items():
        cylinder_between((x, y, BOOM_Z), (x, y, z), 6.0, f"Pylon{k}", doc)
        stud_ring((x, y, BOOM_Z), "z", 6.0, f"StudBoomPylon{k}", doc,
                 n=4, stud_r=1.2, stud_h=2.0)
        stud_ring((x, y, z), "z", 6.0, f"StudPylonPod{k}", doc,
                 n=4, stud_r=1.0, stud_h=1.6)
        pod = loft_body([(-90 * S, 0), (-60 * S, 26 * S), (0, 26 * S),
                        (60 * S, 26 * S), (90 * S, 0)], f"Pod{k}", doc)
        pod_shape = pod.Shape.copy()
        pod_shape.translate(V(x, y, z))
        pod.Shape = pod_shape
        round_edges(pod, 2.5)
        motor_can((x, y, z), "z", LIFT_BELL_R, LIFT_BELL_H,
                 LIFT_SHAFT_R, LIFT_SHAFT_H, f"Motor{k}", doc)
        propeller((x, y, z), PROP_R, "z", f"Rotor{k}", doc)

    # ==== 9. PUSHER -- same prop size as the lift rotors (uniform hardware)
    #    CHANGED this pass: mounted right behind the tail's own trailing
    #    edge (PUSH_X, derived above) instead of 172mm clear of it, with a
    #    motor_can in between -- both built coaxial with the tailboom rod
    #    (same Y=0, Z=BOOM_Z line, same rotate-about-Y "x"-axis convention)
    #    so the rod, motor and prop hub sit on a single straight line, not
    #    offset from each other. See DESIGN_NOTES.md sec 10.2.
    #    Stud rings at both of the motor's own joints: rod-to-bell (flush,
    #    ROD_R) and shaft-to-hub (narrower, PUSH_SHAFT_R).
    stud_ring((ROD_TIP_X, 0, BOOM_Z), "x", ROD_R, "StudRodMotor", doc)
    motor_can((PUSH_MOTOR_X, 0, BOOM_Z), "x", PUSH_BELL_R, PUSH_BELL_H,
             PUSH_SHAFT_R, PUSH_SHAFT_H, "PusherMotor", doc)
    stud_ring((PUSH_X, 0, BOOM_Z), "x", PUSH_SHAFT_R, "StudMotorProp", doc,
             n=4, stud_r=1.0, stud_h=1.8)
    propeller((PUSH_X, 0, BOOM_Z), PROP_R, "x", "Pusher", doc)

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
    front_clear = le - (lift_specs["FR"][0] + PROP_R)
    rear_clear = (lift_specs["RR"][0] - PROP_R) - te
    # NOTE: this is boom-tip past its OWN rotor mount, not past the full
    # blade sweep -- the rotor's blade plane (BOOM_Z+-70*S) sits 34.8mm
    # clear of the boom's own surface in Z regardless of X, so a shorter
    # boom was never a blade-strike risk; this just checks the boom
    # still physically supports its pylon with some overhang.
    boom_overhang = BOOM_AFT_X - REAR_ROTOR_X
    pillar_len = (PILLAR_TOP_Z + PILLAR_EMBED) - (BOOM_Z - PILLAR_EMBED)
    fin_aft_edge = FIN_X + FIN_CHORD
    prop_wing_clear = PUSH_X - WING_TE_X
    pusher_fin_clear = ROD_TIP_X - fin_aft_edge
    front_stance_y = 135 * S + LEG_SPLAY_Y
    rear_stance_y = 135 * S + LEG_SPLAY_Y
    print(f"Scale factor S       = {S:.6f}")
    print(f"Ground line Z        = {GROUND_Z:.1f} mm")
    print(f"Legs                 = 4 (2 front + 2 rear, splayed outward "
         f"+-{LEG_SPLAY_Y:.0f}mm Y / {LEG_SPLAY_X:.0f}mm X at the ground)")
    print(f"Leg ground half-width = {front_stance_y:.1f} mm (was {135*S:.1f} mm plumb)")
    print(f"Boom overhang past its own rotor mount = {boom_overhang:.1f} mm")
    print(f"Boom is NOT connected toward the tail this pass (strut removed "
         f"on request) -- boom's aft tip ({BOOM_AFT_X:.1f}mm) is a free end")
    print(f"Wing pillars (x4)    = {pillar_len:.1f} mm each (boom Z={BOOM_Z:.1f} "
         f"to wing underside Z={PILLAR_TOP_Z:.1f}), at chord x="
         f"{PILLAR_X_FRONT:.1f}mm (front) / {PILLAR_X_BACK:.1f}mm (back), "
         f"y={BOOM_Y:.1f} -- wing chord there spans -117.2 to 121.1mm")
    print(f"Fin X (chordwise)    = {FIN_X:.1f} mm (tail LE={TAIL_X:.1f}, "
         f"TE={WING_TE_X:.1f}, fin TE={fin_aft_edge:.1f})")
    print(f"Fin/keel Y           = {FIN_Y:.1f} mm (tailplane tip = {500*S:.1f} mm)")
    print(f"Tail/boom mount Z    = {BOOM_Z:.1f} mm (same height -- no brace needed)")
    print(f"Front rotor->wing clearance = {front_clear:.1f} mm")
    print(f"Rear rotor->wing clearance  = {rear_clear:.1f} mm")
    print(f"Rod-tip/motor-start->fin-aft-edge clearance = {pusher_fin_clear:.1f} mm")
    print(f"Pusher prop -> tail wing TE clearance = {prop_wing_clear:.1f} mm "
         f"(target ~5mm; actual reflects a real motor+shaft length in between)")
    print(f"Fuselage length (real, unstretched) = {FUSE_TIP_X-(-1080*S):.1f} mm")
    rod_len_3d = math.hypot(ROD_TIP_X - FUSE_TIP_X, BOOM_Z - 0.0)
    rod_angle = math.degrees(math.atan2(BOOM_Z, ROD_TIP_X - FUSE_TIP_X))
    print(f"Tailboom rod length  = {rod_len_3d:.1f} mm, rise angle {rod_angle:.1f} deg "
         f"(fuselage axis (Z=0) at x={FUSE_TIP_X:.1f} to tail-height (Z={BOOM_Z:.1f}) "
         f"at x={ROD_TIP_X:.1f} -- angled so it leaves the fuselage concentric with "
         f"its own axis instead of stepping out sideways)")
    print(f"Objects              = {len(all_objs)}")
    print(f"Saved: {base}.FCStd / .step / .stl")


main()
