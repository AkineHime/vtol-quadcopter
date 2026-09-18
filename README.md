# CoconutQuadplane — VIT BCSE497J Project-I

Autonomous VTOL quadplane for coconut-plantation surveillance (ripeness/yield
and frond-health checks, without climbing the palm). Full mission rationale,
hardware BOM, and architecture decisions: **`documents/vtol_project_summary.md`**
(the original planning doc — some of its "Remaining Work" is now done; see
the status table below for what's current).

This file is a handoff index, not the documentation itself — **full written
documentation and report imagery are still to be done** (see "For whoever
writes up the report" at the bottom). It exists so anyone picking this repo
up cold can find what's here and regenerate any of it.

## Status snapshot (2026-09-19)

| Area | State | Where |
|---|---|---|
| Real airfoil aerodynamics (SD7037 wing / NACA0009 tail) | Done — trim, fin sizing, control authority all computed | `aero/` |
| Full CAD solid model (patent-reference quality) | Done — iteratively corrected against real KCL reference geometry through many review passes | `models/freecad/` |
| Patent-style line drawings | Done, first pass (3 orthographic views, no reference-numeral callouts yet) | `models/patent_drawings/` |
| ArduPilot SITL (generic aero) | Done — full VTOL mission (takeoff/transition/survey/land) passes | `flight_software/` |
| ArduPilot ↔ JSBSim bridge (real aero in the loop) | Working but **not flight-tuned** — completes a mission, flies badly (porpoising, no stable cruise). Root causes and next steps are written down, not guessed at | `flight_software/jsbsim/BRIDGE_RESULTS.md` |
| Propulsion (measured thrust curves) | Not started — currently hand-calibrated placeholder curves | `flight_software/jsbsim/PROPULSION_NOTES.md` |
| AUTOTUNE / transition tuning | Not started | — |
| Review 2 report | Drafted | `report/report.docx`, `report/report.pdf` |
| Detection pipelines, route planner, dashboard | Not started (scoped in the summary doc) | — |

## Repo map

| Folder | What's in it |
|---|---|
| `documents/` | Project summary, design-decision writeups (tail/airfoil choice), Review 2 experiment notes, figures already pulled into the report |
| `aero/` | Airfoil polars → 3D coefficients → trim/fin-sizing pipeline. Has its own `README.md` and `RESULTS.md`. |
| `models/freecad/` | The CAD model. **Exactly two authored files by design** — `build_assembly.py` (the model, run it to regenerate everything) and `DESIGN_NOTES.md` (why every number is what it is, and the full history of corrections). Read `DESIGN_NOTES.md` before changing anything. |
| `models/patent_drawings/` | `generate_patent_sheet.py` builds the 3-view line drawing directly from the FreeCAD model (headless, via FreeCAD's TechDraw module) → `patent_sheet.svg` / `.png`. |
| `3d model files/` | The original reference CAD (KittyCAD/Zoo `.kcl` source, zipped) that `build_assembly.py`'s numbers trace back to — a Raefly VT240 Pro reference photo, reverse-engineered. Keep this; it's the ground truth for every "real" dimension in the model. |
| `flight_software/` | ArduPilot SITL setup, ground-station script, mission verification. Has its own detailed `README.md` — start there. |
| `flight_software/jsbsim/` | The JSBSim aircraft model (real aero) and the bridge that connects it to ArduPilot. `BRIDGE.md` explains the bridge design, `BRIDGE_RESULTS.md` has the test results and exactly what's still wrong, `PROPULSION_NOTES.md` covers the motor/prop modeling gap. |
| `report/` | Review 2 report source (`build_report.py`, `content.py`, a Word template) and the built `.docx`/`.pdf`. |

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
in `flight_software/README.md` §6 if starting on a new machine).

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
- **Known-wrong/in-progress items to state honestly, not gloss over**: the
  JSBSim bridge flies but isn't tuned (`BRIDGE_RESULTS.md` lists exactly
  why); propulsion is a placeholder curve, not measured data; detection
  pipelines and the dashboard haven't been started.
