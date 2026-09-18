# CoconutQuadplane CAD assembly — design notes

This folder holds exactly two files that matter: **`build_assembly.py`**
(the model — run it to regenerate `.FCStd`/`.step`/`.stl`) and **this
file** (the reasoning — every number and decision the script uses, so
neither has to be re-derived or re-argued from scratch). Nothing else
belongs here; regenerable outputs and one-off checks live elsewhere
(see "Housekeeping" at the bottom).

## 1. Where the geometry comes from

Every dimension in `build_assembly.py` traces to the real KCL CAD source
in `3d model files/*.zip` (`demo-project/*.kcl`), which the team
confirmed **is** the intended design — reverse-engineered from an actual
Raefly VT240 Pro reference photo (see `demo-project/NOTES.md`: *"scale is
proportionally inferred... uniformly scaled by 1500/3040"*).

**Scale factor**: `S = 1500/3040 = 0.493421`. The KCL part files (wing,
tail, fin, etc.) are written in the *original* ~3040mm-span coordinate
system; `main.kcl` applies `S` when it assembles them. `build_assembly.py`
applies the same `S` to the same source numbers — nothing here is a
fresh guess.

## 2. Sketch plane per part (the thing that broke once already)

Each lifting surface is built as a **flat 2D profile, extruded thin,
then rigidly rotated + translated into place** — this is exactly how the
KCL itself is built (see `wingHalf.kcl` + `main.kcl`'s `rotate`/
`translate` of it), and it's simpler than lofting a twisted surface.
The one thing that must be tracked correctly per part is **which local
axis becomes "up" after placement** — this is what broke on the first
build (the fin was sketched like a wing and never rotated upright, so it
rendered as a flat slab). Check any future edit against this table:

| Part | KCL sketch plane | Local (x, y) means | Rotation needed |
|---|---|---|---|
| Wing | `on = XY` | (chord, span) | +2° about X (dihedral), mirror for left |
| Tail | `on = XY` | (chord, span) | none, mirror for left |
| Fin  | `on = XZ` | (chord, **height**) | **+90° about X** (else height stays on global Y — the bug) |

Left-side parts are built by **mirroring the placed right-side part**
(`Y -> -Y`) rather than the KCL's own "rotate by 178°" trick. Both are
mathematically equivalent (178° = 180° − 2°, chosen in the KCL to flip Y
while preserving the dihedral's upward sense), but an explicit mirror is
easier to verify by inspection and can't be thrown off by an arithmetic
slip in the angle.

## 3. What's real (from the KCL) vs. new this session

**Unchanged from the KCL** (just re-expressed in FreeCAD, same numbers):
fuselage loft stations, wing/tail/fin profiles and positions, boom
length/position, motor pod shape, propeller diameter *(scale)*, front
landing-leg position.

**Confirmed changed this session** (none of these exist in the original
KCL — each has a reason, not just a preference):

1. **Front lift rotors mounted BELOW their boom, rear rotors mounted
   ABOVE it** (`BOOM_Z ∓ 70*S`). The original KCL has both pods/rotors at
   the same height. Reason: front and rear rotors share one boom and sit
   close together longitudinally; staggering their height keeps the rear
   rotor's disc out of the front rotor's downwash — cleaner, more
   predictable thrust, easier to stabilize.
2. **Four landing legs (2 front + 2 rear), not two.** The original KCL
   has 2 legs, both at one forward station — fine with a nose-heavy
   trike stance, but this airframe's pusher and tail mass sit aft, so
   2 legs alone let the tail sag onto the pusher prop. **First fix
   tried and then reverted**: extending the vertical fins down to the
   ground as skids (computed at 291.1mm extension) — geometrically
   correct but the team decided a large keel extension wasn't worth it.
   **Current fix**: 2 new rear legs, mounted from each boom's aft tip
   (`BOOM_TIP_X`, y=±217mm) straight down to the same ground line as the
   front legs. Checked clear of the pusher (on the centerline, y=0 vs.
   legs at y=±217) and clear of the rear rotors (rotors sit above the
   boom in Z; legs only run below it — no overlap).
3. **A short brace from each boom's aft tip into its fin root.** The
   original KCL has the booms (y=±217mm) and fins (y=±230mm) as
   independent parts that don't touch. Reason: two long unbraced
   cantilevered booms are exactly the structure prone to rotor-induced
   vibration; tying their tips into the tail turns two independent
   cantilevers into one braced structure, for the same material.
4. **All five propellers the same size.** The KCL scales the pusher to
   72% of the lift-rotor diameter — but that ratio came from the
   *reference photo*, not a real spec. The actual hardware BOM
   (`documents/vtol_project_summary.md`) specs one part, a 1045
   (10×4.5in, ≈254mm), for all five positions. Corrected here.

5. **Rotor mount points moved along the boom, away from the wing.** At
   the boom's Y (217.1mm), the wing chord runs LE=−117.1mm to TE=120.6mm.
   The original front/rear rotor X positions (−217.1 / +212.2mm, straight
   from the KCL) put the rotor discs (145.6mm radius) 45.6mm and 54.0mm
   *inside* that chord band — the props swept directly under the wing.
   Moved to −302.7 / +306.2mm, which clears the chord by 40mm on each
   side (verified by the script's own printed output every run — check
   "Front/Rear rotor->wing clearance" is positive, not just present).
   Boom length increased to match (now ±330mm, was ±660mm pre-scale
   ≈±325.7mm — barely changed, since the fix is about *where* the rotor
   sits on the boom, not a much longer boom).
6. **Fin/keel moved to the tailplane's actual tip.** The original KCL
   places the fin at Y=230mm pre-scale (113.5mm post-scale) while the
   tailplane's own half-span is 500mm pre-scale (246.7mm post-scale) —
   the fin sits at only 46% of the way out, reading as "at the center"
   rather than at the tail's edge. Moved to Y=246.7mm exactly (the
   tailplane's real tip), which also shortens the boom-to-fin brace
   from item 3 since the boom and fin are now much closer in Y.
7. **Rear legs moved from the booms to the main fuselage.** Item 2's
   rear legs were originally mounted from each boom's aft tip (y=±217mm,
   wide stance). Moved to the fuselage body itself, at x=200mm (real
   fuselage radius there, interpolated from the loft stations, is
   74.5mm — wider than the leg's 66.6mm spanwise offset, so it mounts
   flush on the fuselage belly), same spanwise spacing as the front
   legs — a narrow, centered stance on the body, not a wide one on the
   booms.

8. **Tail moved down to boom height; brace and pusher mast eliminated.**
   The tail was at Z=88.8mm while the boom sits at Z=18.8mm — that 70mm
   gap is exactly why a diagonal brace was needed to connect them (item
   3). Team's call: instead of bridging the gap, remove it — move the
   tail down to the boom's own height so the boom runs straight into
   the tail's root, no brace required. Ripple effects, each checked:
   - **Fin is now two pieces per side**, not one: a dorsal piece
     reaching 90mm up and a ventral piece reaching 60mm down from the
     shared boom/tail waterline ("a vertical stabilizer on both ends,
     one facing up, one facing down"). Combined span (150mm) exceeds
     the old single fin's height (120.8mm), so yaw authority isn't
     reduced. The crown-arc taper from the KCL fin is simplified to a
     straight taper here — a modeling simplification, not a dimension
     change (real root chord, 138.2mm, kept).
   - **Boom extended aft** from 330mm to 555mm to reach the relocated
     tail (560mm) directly. Checked clear of the rear rotor disc
     (aft edge 451.8mm) by 103mm.
   - **Pusher mast removed.** The pusher previously needed a mast
     because it was offset from the tail's mount point. With the tail
     now at boom height and the pusher mounted flush at the end of the
     tailboom rod (item 9 below), at the rod's own height, no offset
     exists to bridge. Checked clear of the fin (aft edge 698.2mm) by
     56mm.
   - Re-verified the wing/rotor clearance fix from item 5 still holds
     (40mm each side, unaffected by any of this — the wing and front
     boom half didn't move).

9. **Tailboom rod, replacing a stretched fuselage.** The first attempt
   at fitting the relocated tail/pusher lengthened the fuselage itself
   (1081mm to 1445mm, stretching its last two loft stations). The team
   correctly called this out as distorting the fuselage's real
   aerodynamic proportions for no good reason — a stretched *lofted body*
   was the wrong tool. Reverted the fuselage to its exact original real
   KCL stations (all 7, no stretch), and instead added a simple
   constant-radius rod (14mm — between the lift-booms' 11mm and the
   fuselage tip's own 20.7mm, since it carries the tail surfaces' loads
   too) running from the real fuselage's own tail tip (503.4mm) out to
   the pusher mount (920mm, a 416.7mm rod) — exactly how real pusher
   aircraft carry a tail assembly aft of a compact fuselage. The tail
   and fin (item 8) mount partway along this rod at TAIL_X; the pusher
   mounts at its tip. All the clearance numbers from item 8 are
   unaffected, since none of TAIL_X, FIN_Y, or PUSH_X moved — only what
   physically carries them out there changed.

10. **Fin moved aft, pusher pulled in against the tail, real
    propeller + motor detail, rounded edges.** Four related fixes from
    direct FreeCAD-GUI review, all touching the same rear section:

    - **Fin moved from `TAIL_X` (flush with the tail's leading edge) to
      a new `FIN_X` (579.6mm), aft along the tail's own chord.** The
      fin's aft edge now sits 10mm short of the tail's real trailing
      edge (`FIN_MARGIN`) — "at the back of the wing... not completely
      at the end, like their planes" — instead of occupying mostly the
      front of the chord as before. `FIN_Y` (tailplane's real tip,
      246.7mm) is unchanged; this was a chordwise move only.
    - **Pusher pulled in from 900mm to 738.8mm.** The tailboom rod used
      to run 172mm past the tail before reaching the pusher (rod length
      416.7mm) — visibly too long. The tail's real trailing edge is a
      fixed `WING_TE_X = TAIL_X + 340*S = 727.8mm` (unswept — the KCL's
      tail TE is a straight line across the whole span, so this one X
      value holds at every span station). The rod now ends 2mm past
      that (`ROD_TIP_X`), followed by a motor+shaft (9mm) to the
      propeller hub — so the prop sits **11mm** behind the wing, not
      the requested "roughly half a centimeter" exactly, because a
      real two-diameter motor+shaft needs some physical length; 11mm
      was the closest fit without asking the motor to overlap the
      tail's own structure. Rod length dropped from 416.7mm to 226.5mm.
    - **Real propeller (`propeller()`) replacing the bare rectangular
      cross (`blade_pair`).** Each blade now tapers root-to-tip (root
      width 16% of radius, tip 5%) and there's an actual hub cylinder
      at the center, instead of two flat rectangles crossing at a
      point. Applied to all 5 rotor positions (4 lift + pusher). Still
      schematic — flat blades, no aerodynamic twist.
    - **Motor housings (`motor_can()`) added at all 5 rotor
      positions** — a stepped two-diameter cylinder (bell + shaft)
      standing in for a real motor, replacing "just a round shape"
      where the pod/rod met the propeller directly. The pusher's motor
      is built coaxial with the tailboom rod itself (same Y=0, Z=BOOM_Z
      line, same axis convention) so the rod, motor and prop hub read
      as one straight line rather than offset pieces — this is also
      the fix for "the hole [motor/prop] should be concentric with the
      tail boom's center... in one single line."
      **Follow-up (still reported "not aligned" after the above):**
      checked the actual coordinates (`Shape.BoundBox` on the saved
      `.FCStd`) and confirmed the rod/motor/prop centerline really was
      exact (Y=0.000, Z=18.750mm, all the way from `BoomR`/`BoomL`
      through `TailR` to `Pusher`) — the axis was never the problem.
      The real issue: the motor bell was **13mm**, a millimeter
      *narrower* than the **14mm** rod (`ROD_R`), so the rod visibly
      stepped inward right where the motor began instead of running
      straight into it — that's what read as "not aligned" in the GUI.
      Fixed by setting `PUSH_BELL_R = ROD_R` exactly, so the rod flows
      flush into the bell with no radius jump; only the shaft narrows
      from there, as a real motor shaft would. Axial numbers barely
      moved (motor now 10mm long instead of 9mm; prop 12mm behind the
      wing instead of 11mm) — this was a radius fix, not a position
      fix.
    - **`round_edges()` fillets applied** to the wings, tail, both fin
      pieces (2mm radius), the lift-rotor pods and fuselage (2.5-3mm),
      and the propellers/motors (1-1.5mm) — softens the sharp mitred
      corners flat_panel/loft leave behind ("everything has sharp
      lines now"). Wrapped in try/except per part since OCC's fillet
      can refuse a radius that doesn't fit some short edge; on this
      build it succeeded on every panel, the fuselage, and every motor,
      but failed on the 4 lift-rotor pods and all 5 propeller/motor
      fused shapes (`ChFi3d_Builder: only 2 faces` / `no suitable
      edges`) — those stay sharp-edged. Not worth chasing further for
      a schematic-level model; flagged here rather than silently
      dropped.

11. **Real fuselage/rod misalignment fixed, stud rings added at every
    major tube joint.** Direct screenshots from the FreeCAD GUI showed
    the rod visibly off-center where it left the fuselage -- checked
    with `Shape.slice()` and confirmed: the fuselage's own centerline
    at that station is Z=0 with a +-18.15mm cross-section, but the rod
    started at Z=BOOM_Z (18.8mm), so 14.6mm of the rod stuck out past
    the fuselage's surface on top while the rest sat buried inside --
    a real bug, not the radius-step issue fixed in item 10. Fixed by
    starting the rod at (FUSE_TIP_X, 0, **0**) -- concentric with the
    fuselage's own axis -- and angling it up to the tail's mount height
    (BOOM_Z) at its far end: a shallow ~4.7-degree rise over ~227mm,
    not a visible kink. Also added `stud_ring()` -- a small ring of
    bolt-like cylinders -- at every major tube-to-tube joint that was
    previously just two bare surfaces touching: fuselage-to-rod,
    rod-to-motor-bell, motor-shaft-to-prop-hub, both boom-to-tail
    junctions, and all four boom-to-pylon junctions. Schematic (studs
    aren't sized to a real bolt spec), but reads as an actual joined
    assembly instead of intersecting tubes. Not added at the
    pylon-to-pod or leg-to-fuselage joints (too small a scale for six
    tiny cylinders to look like anything but noise) -- flag this if you
    want those covered too.

12. **Boom shortened, tail strut added, legs splayed, remaining stud
    rings added, fillets fixed on the propellers/motors.** From direct
    screenshots again:

    - **Boom and tail were never actually touching** (only the 5mm gap
      from item 8, with a stud ring added in item 11 that couldn't
      fix a real physical gap, only decorate a joint). Team's call:
      stop trying to make the main boom itself reach the tail --
      `BOOM_AFT_X` shortened from 555mm back to **330mm** (just 24mm
      past its own rotor mount at 306.2mm, matching the boom's
      original real length before it was ever stretched to 555mm).
    - **New `Strut{R,L}`** bridges the resulting gap: a thinner, visibly
      secondary member (`STRUT_R=6mm` vs the boom's 11mm) running
      straight from the boom's new tip to the tail root -- both already
      share `BOOM_Z`, so this is a straight connector, not a
      height-bridging brace like the one removed in item 8. Stud rings
      at both of its own joints (boom-to-strut, strut-to-tail).
    - **Landing legs splayed.** Were plumb-vertical cylinders; real
      gear typically splays outward from the mount for a wider, more
      stable ground stance. Front legs now splay forward+outward, rear
      legs splay aft+outward (`LEG_SPLAY_X=25mm`, `LEG_SPLAY_Y=35mm`),
      widening the ground half-width from 66.6mm to 101.6mm. Stud rings
      added at each leg's top (fuselage) mount.
    - **Stud rings added at the two joints flagged as skipped in item
      11** (too small a scale at the time): pylon-to-pod (all 4 rotors)
      and the leg-top mounts (all 4 legs) -- sized down (`stud_r`
      1.0-1.2mm) to fit those smaller members without looking like
      noise.
    - **Fillets on the propellers and motor cans now succeed** (were
      failing with `ChFi3d_Builder: only 2 faces` in items 10-11).
      Root cause: after `.fuse()`, the boolean leaves redundant
      coincident faces that confuse OCC's fillet face-counting. Fixed
      by calling `.removeSplitter()` right after each fuse (before any
      further transform) -- a standard OCC cleanup that merges those
      redundant faces back down. The 4 lift-rotor pods still can't be
      filleted (`no suitable edges`) -- they're a single smooth loft
      with no distinct edges to round in the first place, so this
      isn't a defect, just nothing to do there.

13. **Strut was still reading as "not attached."** Checked with
    `Shape.BoundBox` and found two separate real issues on the strut
    built in item 12:
    - It was a constant `STRUT_R=6mm` cylinder starting flush against
      the boom's `11mm` face -- a real radius step, not a gap, but a
      visible discontinuity that reads the same way.
    - It stopped exactly at `TAIL_X` (560mm), but `round_edges`'
      fillet on `TailR` pulls that corner back by about 0.5mm
      (confirmed: `TailR`'s actual solid starts at X=560.54, not
      560.0) -- so there was a genuine, if hairline, physical gap
      there too.
    Fixed both: the strut is now built with `cone_between()` (tapers
    from `BOOM_R=11mm` at the boom down to `STRUT_R=6mm`), so it starts
    with the exact same cross-section as the boom (flush, no step), and
    it now ends at `TAIL_X + TAIL_EMBED` (3mm past the tail's nominal
    edge) so it physically overlaps `TailR`'s solid with margin,
    regardless of the fillet. Re-verified via `Shape.BoundBox`:
    `StrutR` now spans the identical Y/Z envelope as `BoomR` at their
    shared X=330, and ends at X=563, safely past `TailR`'s actual start
    (560.54).

14. **Boom-to-tail strut removed outright; boom attached to the MAIN
    wing instead.** The team's read, after seeing items 12-13: the boom
    was never structurally attached to anything real -- items 12/13
    were chasing a connection to the tail that shouldn't have existed
    in the first place. Explicit decision: **the boom does not connect
    to the tail at all.** `Strut{R,L}` and its two stud rings
    (`StudBoomStrut`, `StudStrutTail`) are gone; `BOOM_AFT_X` (330mm)
    is now a genuine free end.
    In their place: a **`WingPillar{R,L}`**, a vertical member from the
    boom's own centerline up to the **main wing's** underside, at the
    boom's spanwise station (`BOOM_Y`) and roughly the wing's mid-chord
    (`PILLAR_X=0`; the wing's chord there runs -117 to +121mm). The
    real problem this solves: the boom sits at a fixed `BOOM_Z=18.8mm`
    along its whole length, but the main wing has a 2-degree dihedral
    rooted at `Z=155*S` -- at the boom's own station that works out to
    an underside of **~76.6mm**, a ~58mm vertical gap with nothing
    bridging it. `wing_underside_z(y)` computes this by replaying the
    exact rotate-then-translate transform `place()` applies to the wing
    (verified against the built shape: `Shape.distToShape()` between
    `WingPillarR` and both `BoomR` and `WingR` returns exactly 0.0,
    i.e. real contact, not just close bounding boxes). The pillar
    embeds 2mm into each solid at both ends (`PILLAR_EMBED`, same
    fillet-inset lesson as item 13) and has a stud ring at each end.

15. **Wing pillar's stud rings changed from a 4-stud decorative
    bolt-circle to 2 larger studs, front and back.** This joint carries
    real fore-aft rocking load from rotor-induced vibration transmitted
    through the boom -- it needs actual bracing there, not a fastener
    pattern. `stud_ring(..., n=2, stud_r=3.0, stud_h=5.0)` at both the
    boom end and the wing end: `n=2` places the pair at local angle
    0/180, which for this "z"-axis ring lands exactly on +-X (fore/aft)
    with no extra angle math needed. Sized up from the 1.2mm/2.2mm
    fastener studs elsewhere to read as a real gusset. Only applied to
    the wing pillar joints (`StudPillarBoom{R,L}`, `StudPillarWing{R,L}`)
    -- the other stud rings (motor, rod, boom-pylon, pylon-pod, leg
    tops) are unchanged 4-stud fastener circles; flag it if you want
    this pattern carried to any of those too.

16. **Two wing pillars per boom, not one.** A single pillar (item 14)
    was still only one pivot point -- team wanted a proper two-point
    mount. Added a second pillar per side: `PILLAR_X_FRONT=-70mm` and
    `PILLAR_X_BACK=+70mm` (the wing chord at `BOOM_Y` runs -117.2 to
    +121.1mm, so both sit with healthy margin from either edge and from
    each other). 4 pillars total (`WingPillarFrontR/L`,
    `WingPillarBackR/L`), each with its own front/back stud pair at
    both ends (item 15's fix, now applied per-pillar). Re-verified with
    `Shape.distToShape()`: both the front and back pillar report 0.0mm
    to the wing and to the boom on both sides.

**Explicitly not modeled** (placeholder, flagged so it's never mistaken
for finished): propeller blades are flat (tapered, but untwisted)
silhouettes, not real airfoil blades; the lift-rotor boom's aft end
(330mm) is a genuine free end, not connected to the tail (item 14 --
explicit team decision). Fine for a patent reference and for aero
work; would need real surfacing before anything manufacturing-facing.

## 4. Verified numbers (check these after any edit)

Run `build_assembly.py`, then check its printed output and the STL
bounding box against these — they should not move unless a real design
number changed:

| Quantity | Expected | Source |
|---|---|---|
| Wingspan | 1499.6mm | `NOTES.md` target span (1500mm) |
| Overall length | ~1081mm | nose tip to pusher disc |
| Ground line Z | −197.4mm | front leg length (`landingStrut.kcl`) |
| Fuselage max radius | ~98mm (196mm dia) | `fuselage.kcl` mid-body station |
| Front/rear rotor-to-wing clearance | +40.0mm each | script-computed, printed every run |
| Fin/keel Y | 246.7mm | must equal tailplane half-span (also printed) |
| Fin X (chordwise) | 579.6mm | tail LE 560, TE 727.8 — fin sits in the aft ~58% of chord (sec. 10) |
| Boom-aft-tip to rear-rotor clearance | +103.2mm | script-computed, printed every run |
| Rod-tip/motor-start to fin-aft-edge clearance | +12.0mm | script-computed, printed every run |
| Pusher prop to tail wing TE clearance | +12.0mm | target ~5mm; actual reflects real motor+shaft length (sec. 10) |
| Fuselage length (real, unstretched) | 1036.2mm | back to real KCL stations (sec. 9) |
| Tailboom rod length | 227.2mm, 4.7° rise | fuselage axis (Z=0) to tail height (Z=18.8) — angled, sec. 11 |
| Rod-to-motor / motor-to-prop centerline | Y=0.000, Z=18.750mm | verified via `Shape.BoundBox`, unchanged by the rod-angle fix |
| Fuselage cross-section at rod start | Y ±14.5mm, Z ±18.15mm, centered Z=0 | verified via `Shape.slice()` — rod now concentric with this, sec. 11 |
| Boom length (each side) | 330.0mm (was 555.0mm) | shortened, sec. 12 |
| Boom overhang past its own rotor mount | +23.8mm | script-computed, printed every run |
| Wing pillars (x4) | 61.8mm each, boom Z=18.8 to wing underside Z=76.6 | 2 per boom, front (x=-70) + back (x=+70) — sec. 16 |
| Pillar-to-wing / pillar-to-boom contact | distToShape() = 0.0mm, all 4 pillars | verified geometrically, not just by bounding box — sec. 14/16 |
| Leg ground half-width | 101.6mm (was 66.6mm plumb) | splayed stance, sec. 12 |
| Overall height (ground to highest point) | 361.7mm | ground line (−197.4) to pusher disc top (+164.3) |

## Housekeeping

- Regenerate outputs: `"E:/proggramming/Freecad/bin/freecadcmd.exe" build_assembly.py`
- One-off verification scripts (e.g. rendering the STL to a quick image
  to eyeball) belong in the session scratchpad, not this folder — they're
  disposable, this folder isn't.
- `.stl` is gitignored (regenerate locally when needed); `.FCStd` and
  `.step` are the two real deliverables and stay committed.
