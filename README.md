# CoconutQuadplane — VIT BCSE497J Project-I

Autonomous VTOL quadplane for coconut-plantation surveillance (ripeness/yield
and frond-health checks, without climbing the palm). Full mission rationale,
hardware BOM, and architecture decisions: **`documents/vtol_project_summary.md`**
(the original planning doc — some of its "Remaining Work" is now done; see
the status table below for what's current).

This file is a handoff index, not the documentation itself. It exists so
anyone picking this repo up cold can find what's here, run it, and regenerate
any of it. Everything below the airframe is built and tested **in simulation**;
no hardware has been bought or flown yet.

> **New to the project? Start with [`documents/TEAM_GUIDE.md`](documents/TEAM_GUIDE.md)** (how to run everything, results, open items).
> **Setting up a demo laptop?** Use [`setup/demo_laptop/CHECKLIST.md`](setup/demo_laptop/CHECKLIST.md) (double-click scripts; dashboard in ~20–30 min).

## Status snapshot (2026-11-10)

| Area | State | Where |
|---|---|---|
| Real airfoil aerodynamics (SD7037 wing / NACA0009 tail) | Done: trim, fin sizing, control authority all computed | `aero/` |
| Full CAD solid model (patent-reference quality) | Done (FreeCAD, frozen: FreeCAD is no longer installed; new CAD work is CadQuery in `airframe/`) | `models/freecad/` |
| Patent-style line drawings | Done, first pass (3 orthographic views, no reference-numeral callouts yet) | `models/patent_drawings/` |
| **Print-ready airframe** | Done (CadQuery). 44 parts for a 220 mm bed, detachable wing halves on a carbon spar, openable hatch. **Tail elevator added** (30% chord, pod servo) after JSBSim showed the wing elevons reverse pitch; the wing surfaces are now ailerons. 1858 g, CG 33.9% MAC | `airframe/BUILD_NOTES.md`, `airframe/print/` |
| ArduPilot SITL + **JSBSim** (real aero in the loop) | Done and the **default simulator**. 1000 Hz bridge with a measured A2212 1400 KV / APC 10×4.7 rotor model, battery sag and spool lag; the bridge reports battery voltage/current, so ArduPilot's battery % drains (hover check: 12% vs 11.7% from the energy model). The 22-stop database mission flew 2.76 km in 555 s on 32.4 Wh vs 34.6 Wh estimated | `flight_software/jsbsim/`, `documents/sim_results.md` |
| Gazebo visual demo | Done earlier (first prototype); superseded by JSBSim for missions and the review video. Still runs: `bash flight_software/gazebo/run_demo.sh` | `flight_software/gazebo/README.md` |
| Route planner + sim study | Done. Strategies fw_sweep, vtol_sweep, hover, hybrid; racetrack sweep from the lane nearest the dock (dock anywhere), fixed-wing U-turn into the stops. Batch runner, flight analysis, disturbance scenarios, week-of-operations Monte-Carlo | `flight_software/route_planner.py`, `sim_runner.py`, `analysis.py`, `documents/sim_results.md` |
| **Review video** | Done (final, approved). Flight log → Blender replay with FOV wedge, ESP32 view inserts, telemetry HUD and captions | `flight_software/render/`; output `flight_software/demo/runs/js_demo_v4/js_demo_v4_review.mp4` (git-ignored) |
| **Ripeness detection (ML)** | Baseline done. YOLO26s, 3 classes (pre-mature = tender = harvest target, mature, over-mature), split by source video: test mAP50 0.55 overall, 0.72 pre-mature. `detect_pipeline.py` maps detections to palms via the camera model and posts them to the dashboard. Ground-level training images: aerial accuracy still to be measured | `ml/README.md` |
| **Ground-station dashboard** | Done (built on Caser's dashboard). Per-palm SQLite (maturity, health, status, history), ripeness prediction, next mission planned from the database within 80% of the battery (export `.waypoints`), map lenses, alerts + go/no-go, flight recorder with replay and post-flight report, photos at palm stops, phone camera (IP Webcam MJPEG relay or browser WebRTC, local CA for HTTPS), colour-card reader as a stand-in classifier, Excel export, tablet layout. 48 automated tests pass | `ground_station/README.md`, colour cards: `documents/dashboard/colour_cards.pdf` |
| Demo-laptop setup | Done. Double-click scripts for the dashboard, optional WSL + ArduPilot + JSBSim (pinned ArduPilot commit), and launchers (dashboard / fake aircraft / live JSBSim flight); repo found relative to the scripts | `setup/demo_laptop/` |
| Health detection (pests, frond damage) | Not started: nothing detects health yet; the database and dashboard can already store it | — |
| Real hardware, AUTOTUNE, real flights | Not started: parts not purchased. Planned bill of materials (estimates) is in the Project-I report (Table 7.3) | `documents/vtol_project_summary.md` |

## Repo map

| Folder | What's in it |
|---|---|
| `documents/` | Project summary, design-decision writeups (tail/airfoil choice), Review 2 experiment notes, figures already pulled into the report |
| `aero/` | Airfoil polars → 3D coefficients → trim/fin-sizing pipeline. Has its own `README.md` and `RESULTS.md`. |
| `models/freecad/` | The CAD model. **Exactly two authored files by design** — `build_assembly.py` (the model, run it to regenerate everything) and `DESIGN_NOTES.md` (why every number is what it is, and the full history of corrections). Read `DESIGN_NOTES.md` before changing anything. |
| `models/patent_drawings/` | `generate_patent_sheet.py` builds the 3-view line drawing directly from the FreeCAD model (headless, via FreeCAD's TechDraw module) → `patent_sheet.svg` / `.png`. |
| `3d model files/` | The original reference CAD (KittyCAD/Zoo `.kcl` source, zipped) that `build_assembly.py`'s numbers trace back to — a Raefly VT240 Pro reference photo, reverse-engineered. Keep this; it's the ground truth for every "real" dimension in the model. |
| `flight_software/` | ArduPilot SITL setup, ground-station script, mission verification. Has its own detailed `README.md` — start there. |
| `flight_software/gazebo/` | The visual demo: Gazebo model/world generators, param overlay, one-command `run_demo.sh`, WSL setup script. Its `README.md` lists what's real vs simplified and the design findings from bring-up (motor yaw-tilt, elevon modelling, weathervaning, assist speed). |
| `flight_software/demo/` | The 1 ha plantation (`trees.csv`, `layout.json`, `make_plantation.py`), disturbance `scenarios/`, `run_batch.sh`, and per-run results in `runs/` (summaries and contact sheets; logs and videos are git-ignored). |
| `airframe/` | Print-ready airframe (CadQuery): `params.py` (all dimensions), `build_airframe.py`, `BUILD_NOTES.md`, the STLs in `print/`. |
| `flight_software/jsbsim/` | The JSBSim aircraft model (real aero) and the bridge that connects it to ArduPilot. `BRIDGE.md` explains the bridge design, `BRIDGE_RESULTS.md` has the test results and exactly what's still wrong, `PROPULSION_NOTES.md` covers the motor/prop modeling gap. |
| `report/` | Review 2 report source (`build_report.py`, `content.py`, a Word template) and the built `.docx`/`.pdf`. |
| `flight_software/render/` | Review video: `extract_track.py` (flight log → track), `blender_replay.py`, `assemble_video.py` (HUD, captions, cards). |
| `ml/` | Ripeness dataset prep, YOLO26s training, `detect_pipeline.py` (frames + flight log → per-palm observations, `--post` to the dashboard), `check_projection.py`. Results in `ml/README.md`. |
| `ground_station/` | The dashboard: FastAPI backend (`backend/`), React frontend (`frontend/`), tests (`tests/`), `tools/colour_cards.py`, and `snapshots/` (a shareable copy of the team's farm database with one recorded JSBSim flight; how to load it: `ground_station/README.md`, Database). Full feature list, API and test table in its `README.md`. |
| `setup/demo_laptop/` | Setup and run scripts for a new Windows laptop, plus `CHECKLIST.md` for demo day. |
| `documents/dashboard/` | Dashboard spec, UI reference, printable colour cards. |

## Regenerating things

**FreeCAD model** (Windows, FreeCAD installed at `E:/proggramming/Freecad/`):
```
"E:/proggramming/Freecad/bin/freecadcmd.exe" models/freecad/build_assembly.py
```
Rewrites `coconut_quadplane_assembly.FCStd/.step/.stl` in that folder and
prints every verification number (clearances, lengths, angles) the model is
supposed to hold — check the printed output against the tables in
`DESIGN_NOTES.md` after any change.

**Patent drawing sheet** (same FreeCAD, needs the model above to exist first):
```
"E:/proggramming/Freecad/bin/freecadcmd.exe" models/patent_drawings/generate_patent_sheet.py
```

**Aero pipeline** (WSL2 Ubuntu, venv already set up on this machine):
```
wsl -d Ubuntu-24.04
source ~/venv-ardupilot/bin/activate
cd "/mnt/e/proggramming/semester proj/aero"
python analyze.py
```

**ArduPilot SITL** and **JSBSim bridge**: see `flight_software/README.md` §3
and `flight_software/jsbsim/BRIDGE.md` respectively — both need WSL2 with
the ArduPilot build already in place (full from-scratch rebuild steps are
in `flight_software/README.md` §6, or run `setup/demo_laptop/SETUP-3-simulator.cmd`).

**Dashboard** (Windows; details in `ground_station/README.md`):
```
setup\demo_laptop\SETUP-1-dashboard.cmd      # once: tools, packages, build, certificate
setup\demo_laptop\RUN-demo-with-sim.cmd      # dashboard + JSBSim flight of the next mission
```
`RUN-demo.cmd` starts the dashboard alone, `RUN-demo-fake.cmd` adds a fake aircraft
(no WSL needed). If the simulator link drops, just run `RUN-demo-with-sim.cmd` again:
the dashboard reconnects by itself and closes the old flight after 30 s.

**Tests**: `cd ground_station && .venv\Scripts\python -m pytest -q` (48 tests).

## Tooling this repo assumes

- **FreeCAD 1.1.3** at `E:/proggramming/Freecad/` (Windows) — only needed for
  `models/freecad/` and `models/patent_drawings/`.
- **WSL2, Ubuntu 24.04**, with ArduPilot cloned + built at `~/ardupilot` and a
  Python venv at `~/venv-ardupilot` (`pymavlink`, `matplotlib`, `aerosandbox`,
  `numpy`, `scipy`) — needed for everything under `flight_software/` and `aero/`.
- **`uv`** (Python package runner) — used for any one-off Python script that
  isn't part of the WSL venv, e.g. `uv run --with matplotlib --with numpy
  --with numpy-stl python script.py`.
- `.mcp.json` at the repo root wires up a FreeCAD MCP server for Claude Code;
  irrelevant if you're not using Claude Code against this repo.

## For whoever writes up the report

The **engineering content is real and checkable** — every number in
`models/freecad/DESIGN_NOTES.md` and `aero/RESULTS.md` traces to either the
KCL reference geometry or a computed result, not a guess. What's missing is
the write-up and imagery pulling it together:

- **Patent drawing**: `models/patent_drawings/patent_sheet.svg` has clean
  line art (FIG. 1 perspective / FIG. 2 top / FIG. 3 side) but **no numbered
  reference callouts yet** (10 = fuselage, 12 = wing, etc., with leader
  lines) — real patent figures need these tied to the description text.
- **Report figures**: `documents/review2_figures/` and `report/figs/` have
  what was pulled in so far; the CAD renders there predate the current
  FreeCAD model (`models/freecad/`) and JSBSim bridge results
  (`flight_software/jsbsim/captures/bridge_mission.png` is the latest, most
  accurate flight-test plot).
- **Dashboard figures**: the Project-I report revision (2026-10-28) has
  regenerated architecture/DFD/use-case/class diagrams and dashboard
  screenshots; sequence and screenshots can be re-taken from a running
  dashboard with a JSBSim flight (`RUN-demo-with-sim.cmd`).
- **Known-wrong/in-progress items to state honestly, not gloss over**: all
  flights are simulated; the camera is a smartphone standing in for the
  aircraft's camera module (not yet chosen); the ripeness model is trained on
  ground-level images and the prediction is rule-based; the colour-card
  reader is a demo stand-in; nothing detects health yet; the drone's bill of
  materials is mostly estimates, not quotes.
