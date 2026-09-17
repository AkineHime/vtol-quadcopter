# ArduPilot SITL  <->  JSBSim bridge

Runs ArduPilot's QuadPlane firmware on top of the **real** CoconutQuadplane
aerodynamics (SD7037 wing / NACA 0009 tail, from `aero/`) instead of
ArduPilot's built-in generic model, via ArduPilot's generic external-physics
backend (`--model JSON`).

```
  ArduPilot SITL (arduplane --model JSON:127.0.0.1)
        |  UDP 9002  servo/PWM packet  (16 ch)          ^  UDP  JSON state
        v                                               |
  jsbsim_bridge.py  --  decodes PWM, drives JSBSim, returns pos/att/vel/imu
        |
  CoconutQuadplane.xml  (JSBSim: real aero + external_reactions for 5 motors)
```

## Files

| file | role |
|---|---|
| `jsbsim_bridge.py` | the bridge — UDP server on 9002, one JSBSim step per servo packet |
| `bridge_mission_test.py` | orchestrator: starts the stack, runs the sign check + a full mission |
| `aircraft/CoconutQuadplane/CoconutQuadplane.xml` | + `<external_reactions>` (4 lift + 1 fwd + yaw couple), 4-leg gear, alpha/beta clamp for VTOL |
| `run_bridge_sitl.sh` | manual launcher (bridge + SITL) |

## Run it

```bash
wsl -d Ubuntu-24.04
source ~/venv-ardupilot/bin/activate
cd flight_software/jsbsim
python bridge_mission_test.py            # sign check + mission
python bridge_mission_test.py --signs    # just the elevon-sign check
```

Manual:
```bash
python jsbsim_bridge.py --root . --model CoconutQuadplane --rate 400 &
cd ~/sitlrun
~/ardupilot/build/sitl/bin/arduplane --model JSON:127.0.0.1 \
    --defaults ".../coconut_quadplane.param" -w \
    --home -35.363261,149.165237,584,0 -I0
```

## Control mapping (verified — check 1)

| ArduPilot output | bridge -> JSBSim |
|---|---|
| SERVO1/2 (elevon L/R, fn 77/78) | de-mixed: `elevator = -(nL+nR)/2`, `aileron = -(nL-nR)/2` |
| SERVO3 (throttle, fn 70) | forward pusher thrust |
| SERVO5-8 (motors 1-4, fn 33-36) | 4 lift-rotor thrusts + a yaw-reaction couple |

**Elevon sign was inverted on the first attempt** (positive feedback -> PIO ->
departure -> ArduPilot FPE crash). The `-1/-1` de-mix (`--elevon-pitch/-roll`,
now the default) gives correct response: stick-right rolls right, stick-back
pitches up. This is the sign check the last session deferred; it is done.

## Thrust model — IMPORTANT

All 5 motors are **simple calibrated force models** in the bridge (not the
JSBSim brushless-motor model, which NaNs near zero airspeed — see
`PROPULSION_NOTES.md`):

- lift rotor:  `T = 11 * throttle^1.6` N  (static; ignores prop-in-climb losses)
- forward:     `T = 6 * throttle^2 * (1 - V/42)` N

So **the fixed-wing cruise / survey segment rides on the real aero and is
trustworthy; hover and transition dynamics are only as good as these thrust
curves** — treat them as indicative, not validated. See the test results and
the "known limitations" below.

## Also added to the JSBSim model for the bridge

- **4-point landing gear** in a rectangle round the CG (the old 3-point layout
  tipped the model over on the ground).
- **alpha / beta clamped to ±25°** in the aero derivative terms — the model is
  a cruise fit; a linear extrapolation to the ±90° AoA of a vertical climb
  blew up. Clamping keeps the bridge stable; it also means hover/transition
  aero is approximate.
- **Control tuning** in `coconut_quadplane.param`: the full-span elevons have
  ~10x a normal plane's control power (`aero/control_authority.py`), so
  default ArduPlane gains PIO. Added conservative `RLL2SRV_*`/`PTCH2SRV_*`
  gains, rate limits, and `SERVO1/2` throw limits. **AUTOTUNE on the first
  real flights.**

## Known limitations (do not treat a green mission as flight-validated)

1. Hover/transition thrust is a hand-tuned model, not measured — see above.
2. Aero above ±25° AoA/sideslip is clamped, not real.
3. Control gains are conservative guesses, not tuned.
4. ArduPilot SITL is built with FP-exception trapping: any divergence crashes
   arduplane outright (a blunt but clear failure signal).
