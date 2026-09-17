# ArduPilot ↔ JSBSim bridge — test results

Run: `python bridge_mission_test.py` (WSL). Artifacts in `captures/`.

## The bridge works

ArduPilot's QuadPlane firmware now flies on the **real** CoconutQuadplane
aerodynamics (SD7037 / NACA 0009, from `aero/`) instead of its built-in
generic model. `arduplane --model JSON:127.0.0.1` ⇄ `jsbsim_bridge.py` on
UDP 9002, one JSBSim step per servo packet, **~400 fps, lockstep stable**,
**no NaN in the bridge across a full mission**.

## Check 1 — elevon sign convention: **VERIFIED (after a fix)**

First attempt: signs **inverted** → positive feedback → PIO → the vehicle
departed and ArduPilot hit an FP exception and crashed. Root cause: the
bridge's elevon de-mix had the wrong sign relative to ArduPilot's SERVO
function-77/78 output.

Fix (now the default): `elevator = -(nL+nR)/2`, `aileron = -(nL-nR)/2`.

Re-verified:
| command | result |
|---|---|
| roll-right stick (FBWA) | settles at **+13° bank** ✓ |
| roll-left stick | settles at **−11° bank** ✓ |
| pitch-up stick (rate-pulse test) | **+9°/s nose-up, +9° net** ✓ |
| pitch-down stick | **−18°/s, −22° net** ✓ |
| roll input → stays in roll (≤1.5° pitch bleed) | ✓ |

Commanded roll produces roll, commanded pitch produces pitch, correct
direction, axes not swapped. (An FBWA-based pitch re-test was inconclusive —
the small angle demand didn't excite enough with the conservative gains — but
the rate-pulse test and the fact that **every mission transition tracked
upright instead of inverting** both confirm the pitch sign.)

## Check 2 — full mission through the real aero: **completes, but flies badly**

VTOL takeoff → transition → survey grid → VTOL land → disarm: **all phases
reached, vehicle lands and disarms, bridge NaN-free.** Mission upload
round-trips. So the loop is closed and the real SD7037 aero is in it.

**But the flight quality is poor** — see `captures/bridge_mission.png`:

- The aircraft **porpoises through the whole survey phase** — repeatedly
  dives to ~0 m AGL and climbs back to 10–18 m instead of holding 32 m.
- **Airspeed swings 2 → 25 → 3 → 22 m/s** — never settles at the 12 m/s
  target (the waypoints are ~25 m apart, too close to establish cruise, so it
  is constantly turning, decelerating below transition speed, and re-hovering).
- **Roll swings ±40°, pitch ±30°** repeatedly during the turns/recoveries.
- **VTOL landing overshoots the pad ~55–75 m** every run before recapture.
- Run-to-run **variability**: one earlier run had a transient inversion
  (roll ≈ 160°, pitch ≈ 85°) during a transition that recovered; another was
  cleaner. Not repeatably stable.

## Check 3 — hover / transition: **NOT trustworthy — flagged, as expected**

Cause: the JSBSim propulsion model can't run near zero airspeed (NaNs — see
`PROPULSION_NOTES.md`), so the bridge drives all 5 motors with **simple
hand-calibrated thrust curves** — no rotor momentum drag, no real
prop-in-climb behaviour, soft forward thrust. Combined with **untuned control
gains** and waypoint spacing that never lets it reach cruise, the hover and
transition dynamics above are **not flight-validated** and must not be read
as such.

**To make hover/transition trustworthy:**
1. Feed a **measured** motor+prop thrust-vs-airspeed table into the bridge
   (or a JSBSim DIRECT thruster) — replaces the placeholder curves.
2. Run ArduPilot **`AUTOTUNE`** — the full-span elevons have ~10× a normal
   plane's control power (`aero/control_authority.py`); default gains PIO and
   the conservative hand-set gains here are still not right.
3. Tune the QuadPlane transition / TECS params (`Q_TRANS_*`, `TECS_*`,
   `WP_*` speeds) and space the survey rows to the ~55 m fixed-wing turn
   radius so it isn't perpetually re-transitioning.

## Not started (correctly — this was the milestone, next is tuning)

- Measured propulsion data / DIRECT thruster
- AUTOTUNE + a tuned param set
- Q_* transition tuning (Q_TRANS_*, TECS_*, WP speeds)
