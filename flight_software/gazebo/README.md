# Gazebo visual demo: plantation inspection mission

The real ArduPilot QuadPlane firmware, in SITL, flies the CoconutQuadplane in
Gazebo Harmonic. The model is the printed build from `airframe/` (1.84 kg).
The setting is a 1 ha block of 169 palms on 7.5 m spacing, with a dock 15 m
south of the field. The default mission is the recommended daily operation
from `documents/sim_results.md`:

1. VTOL takeoff straight up from the dock.
2. Transition, then a **fixed-wing scout sweep**: 7 lanes at 36 m, giving
   4-6 nose-camera frames of every palm.
3. Transition back to VTOL, then **confirm stops at 4 flagged palms**. Each
   stop is entered via a lead-in so the fixed camera faces the crown.
4. Return and VTOL land on the dock.

Choose another mission with `PLAN_ARGS`, e.g.
`PLAN_ARGS="--strategy fw_sweep"` or `"--strategy hover --targets ripe"`.
For unattended headless runs (videos, analysis, disturbances) use
`../sim_runner.py` and `../demo/run_batch.sh`.

## Run it

Inside WSL (Ubuntu 24.04), after a one-time `bash setup_wsl.sh`:

```bash
bash /mnt/c/claude/vtol-quadcopter/flight_software/gazebo/run_demo.sh
```

This opens the Gazebo window with a chase camera, boots SITL and flies the
mission. It prints each phase and a per-tree hover check
(`OVERALL: PASS/FAIL`). Results land in `../demo/captures/`:
`telemetry.csv`, `track.png` (planned vs flown) and `results.json`.

- **Review-day backup:** screen-record one clean run of the Gazebo window
  (Windows Game Bar, `Win+Alt+R`) and keep the MP4. `--record` writes
  Gazebo's own state log instead, but that's ~1 GB per run.
- `--no-fly` brings everything up without flying, for manual
  testing with `flight_test.py hover|transition`.
- **QGroundControl** (Windows) can show the route and live position on a
  map: add a TCP link to `127.0.0.1:5762`.

## Files

| File | What |
|---|---|
| `setup_wsl.sh` | One-shot install: Gazebo Harmonic, ArduPilot SITL, the ardupilot_gazebo plugin, the Python venv |
| `gen_sdf.py` | Writes `models/coconut_quadplane/model.sdf`. Every aero number traces to `aero/coefficients.json` |
| `mesh_from_step.py` | Turns the committed CAD STEP into the visual mesh (gmsh, no FreeCAD needed) |
| `gen_world.py` | Builds `worlds/coconut_plantation.sdf` from `../demo/plan.json`: palms, pad, route line, red stop rings |
| `coconut_gazebo.param` | Gazebo-only parameter deltas on top of `../coconut_quadplane.param` |
| `run_demo.sh` | The one-command demo |
| `flight_test.py` | Staged bring-up tests (hover / fixed-wing circuit) |

## What is real and what is simplified

**Real:**
- The flight controller (ArduPilot QuadPlane, unmodified), with the
  airframe's own servo/motor layout. That includes real elevon mixing (77/78),
  which the generic SITL model can't do.
- Wing, tail and fin lift/drag come from the SD7037 / NACA 0009 analysis in
  `aero/`.
- Mass, inertia and rotor/pusher positions come from the JSBSim model and
  the CAD.

**Simplified:**
- Prop thrust/torque uses Gazebo's stock blade-element rotors (iris /
  zephyr-derived), not measured A2212 + 1045 data. See
  `../jsbsim/PROPULSION_NOTES.md`.
- No airspeed sensor in the sim. ArduPilot flies on its synthetic estimate.
- The gains are hand-set starting points, not AUTOTUNEd.

## Design findings from bring-up

These are worth carrying into the report and the real build:

1. **The elevons pitch the nose through the flap moment aft of the CG.** An
   early model put the elevon effect at the wing's aerodynamic centre, which
   sits ahead of the CG. Trailing-edge-up then pitched the nose *down*, and
   the aircraft departed in its first fixed-wing loiter. The fix is separate
   trailing-edge lift elements for the elevons.
2. **VTOL yaw authority vs. fin weathervaning.** With rotor drag torque
   alone, the 340 cm² fins swung the nose 50° during a slow 4 m/s VTOL
   sidestep, with yaw output saturated. Tilting each lift motor 5°
   tangentially cut that to 24°, recovered in ~4 s. **Recommend building the
   real lift-motor mounts with ~5° yaw tilt.**
3. **Fixed-wing roll gains:** ArduPilot's quadplane defaults weave ±20° on
   these full-span elevons, consistent with `aero/control_authority.py`'s
   ~10× roll power. Gains were roughly halved here. AUTOTUNE on the real
   aircraft.
4. **Don't arrive at the first inspection tree straight out of the
   back-transition.** The planner adds a "descend to canopy height" VTOL
   waypoint 15 m short of it.
5. **Lift rotors off in cruise.** With cruise 12 m/s and `Q_ASSIST_SPEED`
   9, the synthetic airspeed (~10 m/s) kept dipping under the assist
   threshold, and the lift motors re-engaged every few seconds. Here cruise
   is 13 m/s, the minimum 10 m/s, and assist 7 m/s (just under the 7.5 m/s
   stall). The lift motors are now fully off on both cruise legs and only
   spin during transitions.
6. **Nose along the direction of travel on VTOL hops.** QuadPlane only
   auto-yaws toward the waypoint on long post-transition approaches. On
   short tree-to-tree hops it holds heading, so the aircraft crabbed
   sideways like a multicopter. Weathervaning (`Q_WVANE_ENABLE 1`,
   `Q_WVANE_GAIN 4`, speed/climb limits off) turns the nose into the
   relative airflow, i.e. the hop direction. Heading-vs-track error during
   hops was a median of 32° at gain 2 and is **6° at gain 4** (96% of
   samples under 30°). The fins now help instead of fighting the yaw
   controller.
7. **The pusher only runs in cruise.** ArduPilot commands it off for every
   VTOL phase. The Gazebo speed controller originally couldn't brake the
   prop, so it visibly coasted through the hovers. Now fixed.

More findings from the 1 ha study (2026-10-17/18) are in
`documents/sim_results.md` §4:
- stab incidence −3.0° in the sim;
- `MIXING_GAIN` 1.0 for pitch authority;
- cruise/minimum airspeed 15/12 m/s;
- the 35° bank limit;
- camera-aware VTOL stops;
- a 60 m return leg before `VTOL_LAND`.
