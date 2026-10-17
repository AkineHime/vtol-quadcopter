# Build-ready airframe + deployment simulation: progress log

Hand-over log for the multi-stage job started 2026-10-17. If a session stops
part-way, the next one reads this first.

## Brief (from the user)

1. **Print-ready airframe.** The hull is 3D-printed (PLA / generic filament).
   - All parts interconnect, the wings detach, and the hull has an opening
     hatch for the electronics.
   - Use a minimal, light design that keeps the CG right.
   - Fully printed, no foam: foam is hard to source and shape.
2. **Rescaled scenario.** Dock at the edge of a ~1 ha plantation, palms on
   the standard grid.
3. **Inspection strategy.** No need to hover at every tree: the camera feed
   is post-processed, so decide hover vs fly-over by simulation.
4. **Turbulence when props start/stop in flight.** Analyse why, and fix it.
5. **Real-world disturbances.**
   - Wind and gusts, hot air, GPS/compass/baro faults, battery sag, bird
     strike, frond contact, motor failure.
   - No rain.
6. **Simulated schedule.** Defaulted to a week of operations: scouting pass,
   then daily confirm flights with dynamic pruning.
7. **Headless runs only.** Record MP4s and analyse the frames myself.
   Nobody watches live.
8. **Visual polish last**, only if budget remains.

Decisions taken by default (the user didn't answer):
- Parts split for a 220×220 mm print bed.
- Week-long schedule.
- No commit without the user's OK. The Gazebo demo from 2026-10-16 is still
  **uncommitted**.

## Budget rule

Check `get_usage` at each milestone. If the 5-hour window is ≥ 85% or context
is ≥ 85%:
1. Stop all WSL sim processes (`scratchpad stopall.sh` pattern: pkill route_planner,
   sim_vehicle, arduplane, gz sim).
2. Update this file.
3. Stop.

## Status

| # | Stage | State | Notes |
|---|---|---|---|
| 0 | Stop background tasks | done | 2026-10-17 |
| 1 | Construction research | done | Carbon-tube spar + printed segments (AeroFold, AggieAir, Eclipson). TNAU 7.5 m square spacing. |
| 2 | Print-ready CAD (CadQuery) | done | `airframe/`: 40 parts, all fit 220 mm, LW-PLA build 1843 g, CG 33% MAC. All-PLA isn't viable (CG 41%). Gazebo model + mesh now generated from it. |
| 3 | 1 ha scenario | done | 13×13 palms, 7.5 m spacing. Dock faces south. `sim_runner.py` runs headless, with `--record` for MP4s. |
| 4 | Transition turbulence analysis | done | Calm: lift stop/start add no roll error beyond ordinary cruise tracking; 0.5-1 m altitude. 5 m/s wind: Q_ASSIST cycled on downwind turns (+<=9 deg roll, 1-4 m). Fixed with more airspeed margin (cruise 15, min 12). |
| 5 | Inspection strategy comparison | done | Fixed-wing sweep: 7 Wh for 4-6 frames/palm. Hover stop: 1.3 Wh/palm. Optimum: daily scout + VTOL-confirm palms with >= 2 agreeing frames. See `documents/sim_results.md`. |
| 6 | Disturbance scenarios | done | Noise, GPS glitch, bird strike, 5 m/s wind: pass. 8 m/s wind: fail, so the limit is ~6 m/s. A lift-motor failure loses the aircraft; mitigations are in sim_results. |
| 7 | Week schedule sim | done | `schedule_sim.py`: 6 policies, 500 weeks. |
| 8 | Visual polish | pending (budget permitting) | |

## Log

### 2026-10-17: first 1 ha runs
- **fw_sweep, unrecorded: landed.**
  - 241.6 s and 2269 m flown.
  - 6.3 Wh used (14% of the pack).
  - 165 of 169 palms imaged; median 4 frames per palm at 3 fps.
  - Minimum clearance to a crown: 12.7 m.
  - Two in-flight lift on/off events, with roll errors of 44° (stop) and 25° (start).
- **Recording.** Gazebo's `<save>` works once the frame folders exist, so the
  runner now creates them. The PPM `frame_recorder.py` was redundant and is
  gone. `encode()` sorts the PNGs numerically.
- **First recorded fw_sweep crashed.**
  - What happened: a spiral dive at 40° bank on the turn into the landing
    approach.
  - What the log shows: elevator demand saturated at +4500 for the whole
    cruise, with the pitch integrator at IMAX.
  - Causes, all three fixed:
    1. **Chase-camera link mass.** A 1 g link 7.6 m behind the CG on a fixed
       joint added 0.06 kg·m² to Iyy (+60%), in recorded runs only. It is
       now 10 mg.
    2. **Sim tail incidence.** LiftDrag has no downwash, so the tail at the
       design -1.79 deg made too much lift. It is now -3.0 deg (design minus
       ~1.2 deg mean cruise downwash), and static trim needs about 0 deg of
       elevon at 12.5 m/s.
       *Build note:* make the stab incidence shimmable by ±2 deg and trim it
       in glide tests.
    3. **Bank limit.** `ROLL_LIMIT_DEG` lowered from 45 to 35, which cuts the
       turn load factor from 1.41 to 1.22.
- **Chase video showed clouds instead of ground.** At grazing angles the
  default PBR material mirrored the sky. All materials are now matte.
- **Added:**
  - `schedule_sim.py`: a week-long Monte-Carlo simulation.
  - `--targets ripe`: a new option on the planner and the runner.
  - `analysis.py`: `MASS_KG` is now 1.84, and lift events record
    `des_roll_span` and `alt_change_m`.

### 2026-10-17 (cont.): tuning, strategies, wind
- **Transition "turbulence".** `analysis.py` now measures what each lift-motor
  start/stop adds over normal cruise roll tracking (`cruise_roll_err_p95`).
  - **Calm:** the events sit 13-15 deg *below* that baseline. Altitude
    changes by 0.5-1 m and pitch excursion is <= 10 deg. Switching the
    motors does not upset the aircraft.
  - **Where the earlier 44 deg came from:** the forward transition happened
    inside a 160 deg turn. The dock faced east and the first leg went
    south-west.
  - **Fix:** the dock now has `heading_deg` 180 in `layout.json`, and the
    spawn yaw follows it.
- **Roll tracking lagged 1-1.5 s** (p95 error 35 deg). Raised `RLL_RATE_FF`
  from 0.30 to 0.45, which brought p95 down to 22 deg.
- **fw_wind5 (5 m/s + 2 gust) spiralled to the ground** on the old tuning.
  - It bounced, then lift assist recovered it.
  - The pitch loop barely moved the elevons, about 10% of their throw.
  - **Fix:** `MIXING_GAIN` 0.5 -> 1.0, with the roll gains halved to keep the
    roll loop gain the same. Result: clearance 11.9 m, max roll 41 deg.
- **Wind still made Q_ASSIST cycle 6 times per sweep** on downwind turns
  (synthetic airspeed 8.9 m/s).
  - Stall is ~9.4 m/s level and ~10.4 m/s at 35 deg bank.
  - **Fix:** `AIRSPEED_CRUISE` 15, `AIRSPEED_MIN` 12.
  - **Real build:** fit an airspeed sensor (a DLVR or MS4525 on the nose);
    synthetic airspeed is the weak link in wind.
- **Strategies, old tuning, calm:**
  - **vtol_sweep:** 168/169 palms imaged, 25.9 Wh (58% of the pack).
  - **fw_sweep:** the same coverage for 6.8-7.0 Wh (15%), 3.8x cheaper.
- **Hover stops fixed.**
  - The first hover run imaged only 18/29 targets, and crown clearance was
    0.75 m:
    - the stop sat directly above the crown, outside the 60 deg-down
      forward camera's view;
    - each stop's altitude followed its own palm, so hops passed low over
      taller neighbours.
  - **New stop design:**
    - all stops are at the tallest palm + 10 m;
    - each stop sits d = dh/tan 60 deg short of its palm;
    - the final leg is >= 15 m (a lead-in point is added when needed), so
      ArduPlane's POSITION1 approach turns the nose toward the palm.
- **`VTOL_LAND` pre-arm.** The waypoint before landing must be at least
  37 m away (`RETURN_D` 40 m in the planner).
- **Full matrix re-running on the final tuning:** 11 runs. `report_runs.py`
  turns them into the pass/fail table.

### 2026-10-18: results
- **Full write-up:** `documents/sim_results.md`.
- **Laptop Modern Standby froze WSL** mid-batch twice (19:38-23:24 among
  others). The affected runs were repeated.
- **Hardening:** `fly()` now detects inverted-for-5-s and >6 m/s impacts as
  crashes, and `kill_all` escalates to SIGKILL (a hung gz server survived
  SIGTERM and held UDP 9002).
- **Motor failure.** The first version of the test was invalid: `SERVO7_MAX`
  doesn't limit motors. It now disables `SERVO7`, and the aircraft is lost
  on landing.
- **Hover stops** always go through a 15 m lead-in (27/29 targets imaged).
- **`run_demo.sh`** defaults to the recommended mission (`PLAN_ARGS`
  overrides it): hybrid with 4 targets, i.e. a sweep plus 4 confirm stops.
- **Open items:**
  - Visual polish (stage 8).
  - Fix the 2 hover targets still missed.
  - A 5 fps camera trigger in the planner/firmware notes.
  - An airspeed sensor in the BOM.
  - Commit: the user said "not now, after the review" (2026-10-18).
