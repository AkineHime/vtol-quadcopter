# Flight Software — ArduPilot SITL + ground-station link

Person 1 deliverable: a working QuadPlane simulation of the coconut-surveillance
airframe, plus the `pymavlink` link the route planner will build on.

**Simulation only — no hardware involved.** Status: **built and flying in SITL.**

---

## 1. What's in this folder

| File | Purpose |
|---|---|
| `coconut_quadplane.param` | Parameter overlay for the real airframe: 4 lift + 1 forward motor, 2 elevons, transition/ESC/battery starting values |
| `upload_mission.py` | Ground-station library: connect, build a survey grid, upload it (MAVLink mission protocol), verify the round-trip, stream telemetry |
| `sitl_verify.py` | Automated bring-up + flight test: loads params, reboots, uploads a grid, flies it in AUTO, writes `captures/` |
| `captures/` | Output of the last `sitl_verify.py` run — `telemetry.csv`, `track.png`, `results.json` |
| `README.md` | This file |

The ArduPilot source tree is **not** kept here — it is cloned inside WSL at
`~/ardupilot` (building under `/mnt/e/...` is very slow and permission-fragile,
per ArduPilot's own docs).

---

## 2. Environment (already set up on this machine)

- **WSL2 + Ubuntu 24.04** — `wsl -d Ubuntu-24.04`
- ArduPilot cloned at `~/ardupilot` (shallow, with submodules)
- Build prereqs installed via `Tools/environment_install/install-prereqs-ubuntu.sh`
- Python venv at `~/venv-ardupilot` (activate before running anything)
- `arduplane` SITL binary built: `~/ardupilot/build/sitl/bin/arduplane`
- `pymavlink` + `matplotlib` installed in the venv

To reproduce from scratch on another machine, see **§6**.

---

## 3. Run a simulated flight

### 3.1 Start SITL (inside WSL)

```bash
wsl -d Ubuntu-24.04
source ~/venv-ardupilot/bin/activate
cd ~/sitlrun
env -u DISPLAY ~/ardupilot/Tools/autotest/sim_vehicle.py -v ArduPlane \
    -f quadplane -w --no-mavproxy --no-rebuild --speedup 3 \
    --out=udp:127.0.0.1:14550
```

- `-f quadplane` loads the QuadPlane physics model + `quadplane.parm` defaults
  (Q_ENABLE on, quad-X lift motors on outputs 5–8, plane surfaces on 1–4).
- `--speedup 3` runs 3× real time — fast enough to watch, slow enough for a
  ground-station script to keep up. Use `--speedup 1` for the cleanest data.
- `-w` wipes params to defaults (first run only).
- Leave `--no-mavproxy` off if you want the interactive MAVProxy console/map.

### 3.2 Automated check (from WSL, SITL already running)

```bash
source ~/venv-ardupilot/bin/activate
cd "/mnt/e/proggramming/semester proj/flight_software"
python sitl_verify.py --connect tcp:127.0.0.1:5760 --rows 3
```

This loads `coconut_quadplane.param`, reboots the FC, waits for GPS+EKF,
uploads a 3-row survey grid, flies it in AUTO, and writes `captures/`.
Expected tail: `OVERALL: PASS`.

### 3.3 Just the ground-station script (from Windows or WSL)

```bash
python upload_mission.py --connect udpin:127.0.0.1:14550            # upload + verify
python upload_mission.py --connect udpin:127.0.0.1:14550 --fly --watch 300   # + fly it
```

---

## 4. Results of the last run (`captures/`)

`results.json` from a passing run:

| Check | Result |
|---|---|
| All 44 airframe parameters loaded & verified | ✅ |
| Mission upload → download round-trip identical | ✅ |
| VTOL takeoff to 35 m | ✅ |
| Transition to forward flight (0 → ~20 m/s, "Transition done") | ✅ |
| All survey waypoints reached in sequence (within `WP_RADIUS` 25 m) | ✅ |
| VTOL landing at home, touchdown ≈ 0.5 m/s, auto-disarm | ✅ |
| Max altitude / airspeed | 37.7 m / 20.6 m/s |

`track.png` — planned grid vs flown track (left), altitude & airspeed vs
time (right). The teardrop turns at each row end are the fixed-wing turn
radius (~55 m at 16 m/s); `row_spacing` is set to 70 m to match.

---

## 5. Parameters — `coconut_quadplane.param`

Key deltas from the SITL quadplane defaults (full list + rationale in the
file's comments):

| Param | Value | Why |
|---|---|---|
| `Q_ENABLE` / `Q_FRAME_CLASS` / `Q_FRAME_TYPE` | 1 / 1 / 1 | QuadPlane, quad-X lift |
| `SERVO1_FUNCTION` / `SERVO2_FUNCTION` | 77 / 78 | **Elevon left / right** — the real airframe has no separate aileron/elevator |
| `SERVO3_FUNCTION` | 70 | Throttle → forward/cruise motor |
| `SERVO4_FUNCTION` | 0 | disabled — no rudder surface |
| `SERVO5-8_FUNCTION` | 33–36 | lift motors 1–4 |
| `Q_ASSIST_SPEED` | 8 | m/s floor for VTOL-assist during transition |
| `AIRSPEED_MIN/CRUISE/MAX` | 12 / 16 / 25 | small foam wing envelope, m/s |
| `WP_RADIUS` / `WP_LOITER_RAD` | 25 / 60 | AUTO nav tracking for the survey grid |

### ⚠️ Elevons in SITL

`sitl_verify.py` loads the elevon functions (77/78) but then, **for the
simulation only**, sets channels 1/2 back to aileron (4) + elevator (19).
Reason: ArduPilot's mixing is identical either way, but SITL's *generic*
quadplane aero model decodes roll/pitch from PWM channels 1/2 by position,
not by `SERVOn_FUNCTION` — so feeding it elevon-mixed outputs corrupts pitch
and roll control (the aircraft becomes uncontrollable in forward flight).
On real hardware the elevon functions are correct and this override does not
apply. Pass `--real-elevons` with a `quadplane-elevon` SITL model if you
want to exercise the elevon path in sim.

---

## 6. Full rebuild from scratch (other machines)

```bash
# 1. WSL2 (admin PowerShell, then reboot)
wsl --install -d Ubuntu-24.04

# 2. clone + prereqs (inside WSL)
cd ~ && git clone --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/ArduPilot/ardupilot.git
cd ardupilot
Tools/environment_install/install-prereqs-ubuntu.sh -y
. ~/.profile

# 3. build
python3 waf configure --board sitl
python3 waf plane            # ~2 min on 16 cores, ~15-40 min on 4

# 4. python deps for the GCS scripts
source ~/venv-ardupilot/bin/activate
pip install pymavlink matplotlib
```

---

## 7. Known limitations (state these in the report)

- **Generic aerodynamics.** SITL uses ArduPilot's built-in QuadPlane model,
  *not* our wing/airfoil. Transition speed, stall, cruise efficiency, and
  endurance are representative, not predictive. Next fidelity step: a JSBSim
  model built from the chosen airfoil
  (`documents/airframe_tail_airfoil_decision.md`).
- **Parameters are starting values.** ESC PWM band, `MIXING_GAIN`,
  `Q_ASSIST_SPEED`, and all TECS/transition tuning need a real tuning pass.
- **No wind / sensor noise** by default. Add `--wind` and sensor-noise params
  for a harder demo.
- **Landing overshoot.** The QuadPlane arrives at the land point fast and
  overshoots ~70 m before the position controller recaptures it — cosmetic
  for the demo, tune `Q_TRANS_DECEL` / approach speed later.
- **Battery model is nominal 3S** — real endurance comes from the JSBSim
  model + measured draw.
