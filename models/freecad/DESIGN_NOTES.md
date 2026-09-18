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
     now at boom height and the pusher mounted flush at the fuselage's
     own tail tip (Y=0, Z=0 — the fuselage's own centerline height
     there), no offset exists to bridge. Checked clear of the fin
     (aft edge 698.2mm) by 56mm.
   - **Fuselage lengthened** from 1081mm to 1445mm (the "increase the
     fuselage size" the team authorized) — the last two loft stations
     are now a computed stretch, not real KCL numbers, specifically
     sized to fit the relocated tail and pusher with real clearance
     margins rather than crowding them. Flagged as SCHEMATIC (stretched)
     in the fuselage section, same as the original last-two stations
     were real.
   - Re-verified the wing/rotor clearance fix from item 5 still holds
     (40mm each side, unaffected by any of this — the wing and front
     boom half didn't move).

**Explicitly not modeled** (placeholder, flagged so it's never mistaken
for finished): propeller blades are flat rectangular silhouettes, not
real airfoil-twisted blades; joints (boom-to-pod, brace-to-fin) are
simple cylinders, not filleted/blended. Fine for a patent reference and
for aero work; would need real surfacing before anything manufacturing-
facing.

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
| Boom-aft-tip to rear-rotor clearance | +103.2mm | script-computed, printed every run |
| Pusher-to-fin clearance | +56.2mm | script-computed, printed every run |
| Fuselage length | 1444.9mm | was 1081.2mm before the tail relocation (sec. 8) |
| Overall height (ground to highest point) | 342.9mm | ground line (−197.4) to pusher disc top (+145.6) |

## Housekeeping

- Regenerate outputs: `"E:/proggramming/Freecad/bin/freecadcmd.exe" build_assembly.py`
- One-off verification scripts (e.g. rendering the STL to a quick image
  to eyeball) belong in the session scratchpad, not this folder — they're
  disposable, this folder isn't.
- `.stl` is gitignored (regenerate locally when needed); `.FCStd` and
  `.step` are the two real deliverables and stay committed.
