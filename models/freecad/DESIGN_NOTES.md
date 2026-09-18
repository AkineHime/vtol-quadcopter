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

## Housekeeping

- Regenerate outputs: `"E:/proggramming/Freecad/bin/freecadcmd.exe" build_assembly.py`
- One-off verification scripts (e.g. rendering the STL to a quick image
  to eyeball) belong in the session scratchpad, not this folder — they're
  disposable, this folder isn't.
- `.stl` is gitignored (regenerate locally when needed); `.FCStd` and
  `.step` are the two real deliverables and stay committed.
