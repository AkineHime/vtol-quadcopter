# Simulation results: 1 ha plantation, Gazebo + ArduPilot SITL

**Date:** 2026-10-17/18.
**Simulator:** ArduPlane 4.8-dev QuadPlane firmware in SITL, flying the
printed-build model (1.84 kg, CG 33% MAC) in Gazebo Harmonic. Every run is
headless and unattended, via `flight_software/sim_runner.py`.
**Generated results:**
- `flight_software/demo/runs/<run>/` holds `summary.json`, `analysis.json`,
  `mission.log`, `plan.json` and the contact sheets.
- The `.BIN` logs and `.mp4` videos stay local; they're git-ignored.
- `python report_runs.py` rebuilds the table below.

## Scenario

- **Field:** 1 ha (100 × 100 m), coconut on TNAU 7.5 m square spacing.
  - 13 × 13 = **169 palms**, 12–16 m tall, 4 m crown radius.
  - 29 ripe; 20 with frond damage.
  - Source: `demo/make_plantation.py`, seed 7.
- **Dock:** on the southern track, 15 m south of the field, facing south.
  - The aircraft climbs straight up to 30 m, transitions, flies the job and
    lands back on the dock.
- **Camera:** nose ESP32-CAM, 60 × 46° FOV, fixed 60° below the horizon,
  3 fps. A palm counts as "imaged" in a frame only when its whole crown is
  in the frame within 30 m.

## Results table (final tuning)

| run | strategy | wind | disturbance | flight s | Wh | batt % | imaged ≥ 2 frames | min clear m | max roll | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **demo_hybrid4 (recorded, review demo)** | sweep + 4 confirm stops | 0 | – | 326 | 14.0 | 32 | 163/169 palms; 4/4 targets (median 22 frames) | 5.4 | 43 | **PASS** |
| fw_calm (recorded) | fixed-wing sweep | 0 | – | 250 | 7.1 | 16 | 162/169 palms | 15.0 | 41 | **PASS** |
| fw_sensor_noise | fixed-wing sweep | 0 | GPS 0.6 m noise, IMU noise | 253 | 7.2 | 16 | 163/169 | 14.7 | 42 | **PASS** |
| fw_gps_glitch | fixed-wing sweep | 0 | 10 m GPS step mid-lane | 245 | 7.1 | 16 | 161/169 | 14.8 | 40 | **PASS** |
| fw_bird | fixed-wing sweep | 0 | 25 N + 1.5 N·m hit, 0.15 s (0.9 g measured) | 246 | 7.3 | 16 | 161/169 | 14.1 | 42 | **PASS** |
| fw_wind5 | fixed-wing sweep | 5 m/s + 2 gust | – | 250 | 9.8 | 22 | 156/169 (161 at 5 fps) | 11.1 | 48 | **PASS** for safety; imaging 92% |
| fw_wind8 | fixed-wing sweep | 8 m/s + 3 gust | – | 330 | 41.5 | 93 | 120/169 | **−0.8** | **101** | **FAIL**: outside the envelope |
| fw_motor_fail | fixed-wing sweep | 0 | lift motor 3 dead from mid-sweep | – | – | – | – | – | – | **FAIL**: hits the ground at 10.5 m/s on landing |
| vtol_sweep | VTOL lawn-mower | 0 | – | 350 | 25.8 | 58 | 167/169 | 9.3 | 8 | PASS, 3.6× the energy |
| hover_ripe | hover at 29 ripe palms | 0 | – | 516 | 37.7 | 85 | 27/29 targets (median 15 frames) | 5.4 | 16 | marginal |
| hover_wind5 | hover at 29 ripe palms | 5 m/s + 2 gust | – | 469 | 35.3 | 80 | 25/29 targets | 5.3 | 18 | marginal |
| hybrid_ripe | sweep + 29 hover stops | 0 | – | 662 | 38.2 | 86 | 29/29 targets | 5.4 | 40 | over the 80% battery rule |

## 1. Inspection strategy: don't stop at every tree

- **Fixed-wing sweep (recommended scout).**
  - 7 lanes, 15 m apart, flown at 36 m and about 15 m/s.
  - Takes 4.2 min and **7 Wh (16% of the pack)**.
  - Gives **4–6 oblique frames of nearly every palm** (162–168 of 169 with
    ≥ 2 frames).
- **VTOL sweep.** Same coverage for 3.6× the energy.
- **Hover stop.** About **1.3 Wh and 18 s per palm**. Hovering at all 169
  palms would take ~220 Wh: about 6 batteries a day.

### How many images per palm? (`schedule_sim.py`)

Assumptions: per-frame ML recall 0.70, false-positive rate 4%, and a palm
counts as detected when 2 frames agree.

| frames per palm | recall | false votes per scout (140 non-ripe palms) |
|---|---|---|
| 2 | 0.49 | 0.2 |
| 4 | 0.92 | 1.3 |
| 5 | 0.97 | 2.1 |
| 6 | 0.99 | 3.0 |
| 10 | 1.00 | 8.1 |

**4–6 frames is the sweet spot.** More frames mostly add false votes, which
is the point that tens of images per tree aren't needed. The sweep already
delivers 4–6.

### A week of operations (Monte-Carlo, 500 weeks)

- Palms ripen at about 1 bunch per palm per month.
- 12% of days are no-fly.
- The crew harvests the day after a palm is reported.

| policy | Wh/week | sorties/week | harvested/week | latency (days) | wasted climbs/week |
|---|---|---|---|---|---|
| hover at every palm daily | 1366 | 44 | 60.9 | 1.14 | 0 |
| daily scout, confirm any 1-frame hit | 359 | 19 | 59.0 | 1.16 | 0 |
| scout every 2nd day + confirm | 230 | 11 | 51.3 | 1.48 | 0 |
| daily scout, report ≥ 2 votes, confirm 1-vote | 257 | 15 | 58.8 | 1.14 | 14 |
| **daily scout, confirm ≥ 2 votes, ignore 1-vote** | **149** | 13 | **57.6** | **1.24** | **0** |
| daily scout, report without confirming | 44 | 6 | 58.8 | 1.13 | 151 |

**Recommendation:**
- Fly a **fixed-wing scout every morning**.
- Run ML on the 4–6 frames per palm, and **VTOL-confirm only palms where at
  least 2 frames agree**. That's typically 2–13 stops a day after the first
  day's backlog.
- Ignore single-frame hits: tomorrow's scout looks again.

This gets 95% of the maximum harvest for 11% of the energy of hovering
everywhere, with no wasted climbs. Scout plus confirm fits in **one battery
on a typical day**. The first day's backlog (about 40 stops) needs two.

## 2. Turbulence when the lift motors start and stop (transitions)

`analysis.py` measures every in-flight lift-motor on/off event. For each one
it records peak attitude error, altitude change, and the roll error **in
excess of ordinary cruise roll tracking** (that run's cruise p95).

- **Calm.** One forward transition and one back-transition per flight.
  - Roll error is 13–15° *below* the cruise baseline.
  - Altitude changes by 0.5–1 m; pitch excursion is ≤ 10°.
  - **The motor start/stop itself doesn't upset the aircraft.**
  - The 44° "transition roll error" first seen was a commanded 160° turn
    during the transition: the dock faced east, the first leg went
    south-west. Facing the dock toward the first leg removed it.
- **5 m/s wind.** On downwind turns the synthetic airspeed dropped below
  `Q_ASSIST_SPEED`, so the lift motors came in for about 6 s, up to 6 times
  per sweep.
  - Each stop adds at most ~9° of roll error beyond cruise, and 1–4 m of
    altitude.
  - Raising cruise/minimum airspeed to 15/12 m/s reduced this. **A real
    airspeed sensor is the proper fix**: Q_ASSIST then acts on true
    airspeed instead of a wind-estimate guess.

## 3. Real-world disturbances

| disturbance | result | what to do |
|---|---|---|
| GPS/IMU noise, 10 sats | no effect | – |
| 10 m GPS glitch | EKF absorbed it, no warning | – |
| bird strike (0.9 g lateral) | no visible effect | – |
| 5 m/s wind + 2 m/s gusts | safe; imaging 92% (97% at 5 fps); assist cycles in turns | fit an airspeed sensor; trigger the camera at 5 fps |
| 8 m/s wind + 3 m/s gusts | **unsafe:** long assisted phases, one downwind turn hit the ground | **operating limit about 6 m/s mean wind**; the dock holds the aircraft on windier days (the 12% no-fly days in the schedule) |
| one lift motor dead | **aircraft lost:** an X-quad can't hold attitude on 3 motors; 33 m fall at 10.5 m/s | see below |

**Lift-motor failure is the single-point failure.** Options, cheapest first:
1. ESC telemetry (RPM). Check each lift motor's spin-up before every
   back-transition. If one fails, abort to a fixed-wing belly landing on
   the track; the aircraft can glide.
2. An X8 coaxial lift set (+4 motors and props, about +150 g). Keeps
   attitude with one motor out.
3. A parachute for the dock area.

Option 1 costs nothing in hardware and should be in the firmware plan.

## 4. Model and tuning findings that carry over to the real build

All live in `flight_software/gazebo/coconut_gazebo.param` and
`airframe/BUILD_NOTES.md`.

- **Stab incidence.** The sim needed −3.0° (design −1.79°) for near-neutral
  elevons at cruise. **Make the stab incidence shimmable ±2°** and trim it
  in glide tests.
- **Elevon pitch authority.**
  - The elevons sit on a 0.16 m arm and the stab is fixed. With
    `MIXING_GAIN` 0.5 the pitch loop couldn't stop a nose drop in a 35°
    bank, and the result was spiral dives.
  - Fix: use `MIXING_GAIN` 1.0 (full throw to pitch), halve the roll gains,
    and set `ROLL_LIMIT_DEG` 35.
- **Airspeed margin.** Stall is ~9.4 m/s level and ~10.4 m/s at 35° bank.
  Cruise at 15 m/s, minimum 12 m/s.
- **VTOL heading.** The nose can't be commanded in VTOL AUTO. ArduPlane
  points it along a POSITION1 approach leg, so every inspection stop is
  entered via a 15 m lead-in on the palm's bearing. The stop sits
  dh/tan 60° short of the crown, so the crown is centred in the fixed
  camera. Stops are flown at tallest palm + 10 m, which clears every crown
  by more than 5 m.
- **Mission rule.** The last waypoint before `VTOL_LAND` must be at least
  the stopping distance away (42 m at 15 m/s); the planner uses 60 m.

## Media

`flight_software/demo/runs/fw_calm/` and `.../demo_hybrid4/` hold
`chase.mp4`, `overview.mp4`, `esp32cam.mp4` and a contact sheet for each.
- **demo_hybrid4** is the review demo mission: the scout sweep, then 4
  VTOL confirm stops, then landing.
- **The ESP32-CAM frames** show whole crowns obliquely; ripe palms show as
  yellow fronds and nuts in the sim.

## Caveats

- The aero is Gazebo LiftDrag with real airfoil slopes, but it has no
  downwash, prop wash or ground effect.
- Airspeed is synthetic.
- The ML performance numbers (70% / 4% per frame) are assumptions; replace
  them with measured ones once a detector exists.
- Energy uses momentum theory plus drag×speed, with η 0.45 / 0.50.
- **Laptop standby froze WSL twice mid-run** (Windows events 506/507). Those
  runs were discarded and repeated. Keep the PC awake and the lid open for
  long batches.
