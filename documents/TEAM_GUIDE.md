# CoconutQuadplane: team guide (October 2026)

This is the starting point for anyone joining the project. It covers what's
new, how to run everything, what we found, and what's still open. The full
numbers live in the documents linked from each section.

## What the project is now

A 1.3 m-span VTOL quadplane that scouts a coconut plantation and finds ripe
bunches for the harvest crew. The October work added three things:

1. **A print-ready airframe** (`airframe/`): 40 parts, all fitting a 220 mm
   bed.
   - Detachable wing halves on a carbon spar.
   - An openable electronics hatch.
   - LW-PLA skins. The airframe weighs **1843 g** with the CG at
     **33% MAC**.
2. **A Gazebo + ArduPilot simulation** (`flight_software/gazebo/`). It flies
   the real ArduPilot QuadPlane firmware in SITL over a **1 ha plantation of
   169 palms**, using a physics model generated from the airframe's CAD.
3. **A simulation study** (`flight_software/*.py`, `documents/sim_results.md`)
   covering:
   - which inspection strategy to fly;
   - how bad the transitions are;
   - how the aircraft copes with wind, sensor faults, bird strikes and a
     motor failure;
   - a week of simulated operations.

**The one-line conclusion:** fly a fixed-wing scout sweep every morning (4
minutes, 16% battery, 4–6 photos of every palm). Hover only over palms where
at least 2 photos agree on "ripe". Never hover at every tree.

## Repo map (new parts)

| Path | What it is |
|---|---|
| `airframe/params.py` | **Single source of truth** for geometry, materials, component masses and positions |
| `airframe/build_airframe.py` | CadQuery model. It writes `print/*.stl`, `out/*.step`, `out/mass_properties.json` and preview PNGs |
| `airframe/BUILD_NOTES.md` | Print settings, mass/CG table, weight cuts, **assembly order** |
| `flight_software/gazebo/` | Gazebo model and world generators, ArduPilot param overlay, `run_demo.sh` (GUI), `setup_wsl.sh` |
| `flight_software/route_planner.py` | Builds and flies missions: `fw_sweep`, `vtol_sweep`, `hover`, `hybrid` |
| `flight_software/sim_runner.py` | One headless scenario end to end: plan → world → SITL → fly → analyse → videos |
| `flight_software/analysis.py` | Flight log → imaging per palm, energy, crown clearance, transition disturbance |
| `flight_software/report_runs.py` | Pass/fail table over all runs |
| `flight_software/schedule_sim.py` | Week-of-operations Monte-Carlo; compares inspection policies |
| `flight_software/demo/` | Plantation layout (`trees.csv`, `layout.json`), disturbance `scenarios/`, `run_batch.sh`, results in `runs/` |
| `documents/sim_results.md` | **Results and recommendations** |
| `documents/build_sim_progress.md` | Running log of the work, decisions and fixes |

## Setup (once per PC)

Everything runs in **WSL2 Ubuntu 24.04** on Windows. A GPU helps for
recording videos, but runs without recording don't need one.

```bash
bash /mnt/c/<your-clone>/flight_software/gazebo/setup_wsl.sh
```

This installs:
- Gazebo Harmonic;
- ArduPilot SITL (`~/ardupilot`);
- the `ardupilot_gazebo` plugin;
- ffmpeg;
- a Python venv `~/venv-ardupilot` with pymavlink, gmsh and CadQuery.

It's safe to re-run, and takes about 1 hour the first time. FreeCAD is
**not** needed.

**Paths:** the scripts find the repo relative to themselves, so any clone
location works. The examples below use `/mnt/c/claude/vtol-quadcopter`.

## How to…

### …regenerate the airframe after changing a dimension

Edit `airframe/params.py`, then:
```bash
source ~/venv-ardupilot/bin/activate
cd airframe && python build_airframe.py
```
- It takes about 4 min.
- Check the `[mass]` line for **total mass** and **CG % MAC**, which must
  stay at 30–35%.
- Check the `[geom]` lines for **skin clearance** of the spar and pin.
- The Gazebo model picks up the new mass, inertia and CG automatically.
- If the shape changed, also refresh the visual mesh with
  `python flight_software/gazebo/mesh_from_step.py`.

### …print and build it

Follow `airframe/BUILD_NOTES.md`: print settings per part type, then the
assembly order. Three points matter most:
- **Leave the stab incidence adjustable** (±2°, shim it) and trim it in
  glide tests before gluing. The sim needed −3.0° rather than the design
  −1.79°.
- Balance with the battery: the CG must sit **88 mm aft of the wing root
  LE**.
- Lift motor pods have a built-in 5° yaw tilt. Check each pod's part name
  against its prop direction.

### …show the visual demo (review)

```bash
bash /mnt/c/claude/vtol-quadcopter/flight_software/gazebo/run_demo.sh
```
- This opens Gazebo and flies the recommended mission: dock takeoff,
  fixed-wing scout sweep, 4 VTOL confirm stops, then landing on the dock.
- To fly something else, set `PLAN_ARGS`, e.g.
  `PLAN_ARGS="--strategy fw_sweep" bash .../run_demo.sh`.
- **Backup videos** are in `flight_software/demo/runs/demo_hybrid4/*.mp4`.
  They're not in git (too large); ask whoever has them, or re-record them
  with the next command.

### …run headless simulations (no window)

```bash
bash /mnt/c/claude/vtol-quadcopter/flight_software/demo/run_batch.sh \
  "my_run --strategy fw_sweep --wind-n -3 --wind-e 4 --gust 2" \
  "my_hover --strategy hover --targets ripe" \
  "my_video --strategy hybrid --targets P0005,P0302 --record"
python flight_software/report_runs.py      # pass/fail table of everything in demo/runs/
```

`sim_runner.py` options:

| Option | What it does |
|---|---|
| `--strategy` | `fw_sweep`, `vtol_sweep`, `hover` or `hybrid` |
| `--targets` | `ripe`, or a list of palm ids |
| `--wind-n/-e` | Mean wind in m/s (the direction the air moves toward) |
| `--gust` | Gust strength |
| `--param-file` | Extra ArduPilot params, e.g. `demo/scenarios/sensor_noise.param` |
| `--events` | Timed disturbances, e.g. `demo/scenarios/bird_strike_events.json` |
| `--record` | Saves chase, overview and nose-camera MP4s plus contact sheets |

Notes:
- A run takes about 5–10 min; a recorded run takes longer.
- Run one at a time, because they share ports.
- **Keep the laptop awake with the lid open.** Windows Modern Standby
  freezes WSL mid-run. A run whose `wall_s` is far larger than its
  `flight_s` was frozen; repeat it.

### …compare operating policies

```bash
python flight_software/schedule_sim.py --weeks 500
```
It reads the flight costs from `demo/runs/fw_calm` and
`demo/runs/hover_ripe`. The ML assumptions are at the top of the file:
per-photo detection 70%, false alarm 4%. **Replace them with measured
numbers once we have a detector.**

## Key results (details: `documents/sim_results.md`)

**Strategy:**

| Option | Cost | Coverage |
|---|---|---|
| Fixed-wing sweep | 7 Wh (16%), 4 min | 4–6 photos per palm |
| VTOL sweep | 3.6× the energy | same as the fixed-wing sweep |
| Hover stop | 1.3 Wh per palm | one palm per stop |

Hovering at all 169 palms would take about 6 batteries a day.

**Photos per palm:** 4–6 is the sweet spot (92–99% detection when 2 photos
must agree). More photos mostly add false alarms.

**Best weekly policy:** daily scout, plus VTOL-confirm the palms where at
least 2 photos agree.
- 149 Wh/week, about 11% of hover-everywhere.
- 95% of the maximum harvest.
- No wasted climbs for the crew.

**Transitions:** starting and stopping the lift motors doesn't upset the
aircraft in calm air (≤ 1 m altitude, no extra roll). In wind, airspeed
dips on downwind turns make the motors cycle → **fit an airspeed
sensor**.

**Disturbances:**
- **Passed:** sensor noise, a 10 m GPS glitch, a bird strike (0.9 g),
  5 m/s wind with gusts.
- **Failed:** 8 m/s wind with gusts. **Operating limit: about 6 m/s
  wind.**
- **A dead lift motor loses the aircraft** (an X-quad can't fly on 3
  motors). This is our biggest open risk; see the next steps.

## ArduPilot settings that came out of the sim

They live in `flight_software/gazebo/coconut_gazebo.param`, and each is
commented with why. Carry them to the real aircraft as starting points:
- `MIXING_GAIN 1.0`, with roll gains halved: pitch authority from the
  elevons.
- `ROLL_LIMIT_DEG 35`.
- `AIRSPEED_CRUISE 15`, `AIRSPEED_MIN 12`, `Q_ASSIST_SPEED 9`.
- `Q_WVANE_ENABLE 1`, `Q_WVANE_GAIN 4`: the nose points along travel in
  VTOL.

Mission rules the planner already handles:
- The waypoint before `VTOL_LAND` must be at least 42 m away (it uses
  60 m).
- Each hover stop is entered via a 15 m lead-in, so the fixed camera faces
  the palm.

## Open items: pick one up

| # | Item | Notes |
|---|---|---|
| 1 | **Lift-motor failure handling** | Check ESC telemetry/RPM before every back-transition and abort to a fixed-wing belly landing if one fails. Alternative: an X8 coaxial lift set (about +150 g). |
| 2 | Airspeed sensor | Add an MS4525/DLVR to the BOM and nose, then enable `ARSPD_*`. That fixes assist cycling in wind. |
| 3 | Camera trigger at 5 fps | Gets 97% of palms to ≥ 2 photos in 5 m/s wind (3 fps gives 92%). Check the ESP32-CAM can sustain it at SVGA. |
| 4 | Ripe-bunch detector | Train on real oblique crown photos; measure per-photo recall and false-alarm rate; feed them into `schedule_sim.py`. |
| 5 | Weight cuts | `BUILD_NOTES.md` lists them. All-PLA isn't viable: CG ends up at 41% MAC. |
| 6 | Hover misses | 2 of 29 hover targets still miss the frame in calm air, and 4 of 29 in wind. |
| 7 | Demo visual polish | A tracking overview camera, a non-rolling chase camera, phase captions on the video. |
| 8 | Real-world trim | Glide tests for the stab incidence; then AUTOTUNE in FBWA/QHOVER. |

## Caveats

The simulation is a design tool, not proof:
- **Aerodynamics:** Gazebo LiftDrag, which has no downwash, prop wash or
  ground effect.
- **Airspeed:** synthetic.
- **Energy:** estimated from momentum theory and drag.

Treat the numbers as ±20% and the comparisons between options as the
reliable part.
