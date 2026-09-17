# Forward-motor propulsion — investigation & status

**Question (last session's open item):** the DJI E305 motor model "won't
throttle down to the cruise thrust this airframe needs" — genuine hardware
mismatch, or a modelling artefact?

**Answer: both.**

## 1. What the airframe needs

At the refined 12 m/s cruise, drag ≈ 1.0–1.3 N, so the forward motor needs
**~1 N of thrust in cruise** and enough for climb/transition (static thrust
ideally ≥ ~0.5 × AUW ≈ 7 N so forward-motor T/W ≈ 0.5).

## 2. The DJI E305 + DJI 9450 stand-in (previous model)

Characterised in JSBSim (throttle sweep, speed pinned at 12 m/s):

| throttle | RPM | thrust | note |
|---|---|---|---|
| 0.06–0.30 | 800–4100 | **≈ 0 N** | prop windmilling — high advance ratio, below its useful RPM |
| 0.45 | 5900 | 1.0 N | first usable cruise point |
| 0.60 | 7600 | 2.4 N | |
| static, 0.75 | 9100 | **4.9 N** | T/W ≈ 0.35 |

So with the E305 there was **no throttle below ~0.45 that produced any
forward thrust at cruise speed** — the reported symptom. Static thrust
(4.9 N) also undersized the transition/climb margin.

## 3. Root causes

**Genuine mismatch:** the E305 is a 960 Kv motor; the airframe's actual choice
(roadmap spec) is **A2212 2200 KV + 1045**. Also — a **2200 Kv** motor on a
10-inch prop is itself a marginal pairing (high-speed / low-torque motor,
largish prop): it works in real F450-class builds but draws high current and
is a poor static-thrust performer. For a VTOL forward motor doing mixed
static + cruise duty, **A2212 1400 KV + 1045** would be better matched — worth
raising with the team.

**Modelling limitation:** JSBSim's `brushless_dc_motor` + a fixed-pitch
`type="internal"` propeller table is a simple torque-balance. At this size it
**cannot match static thrust and current draw simultaneously**, and with a
high-Kv motor it **fails to converge at V ≈ 0** (the model NaNs at static —
the motor can't hold the prop at a stable RPM). It is built for larger
multirotor motors like the E305 it ships with.

## 4. What was changed

The JSBSim engine is now **`A2212_2200KV.xml` (brushless_dc_motor) +
`APC_1045.xml`** (a 9.4-in `DJI_9450` table relabelled — same 4.5-in pitch,
close enough), matching the stated hardware. `coilresistance` is set to a
**lumped** 0.14 Ω (winding + ESC + wiring) as a compromise.

Result at 12 m/s (speed pinned):

| throttle | RPM | thrust | amps |
|---|---|---|---|
| 0.25 | 5600 | 0.4 N | 4 A |
| **0.33–0.35** | **6600–6900** | **~1.0 N** | **8–9 A** | ← cruise |
| 0.45 | 8200 | 1.8 N | 14 A |
| 0.60 | 10200 | 2.6 N | 21 A |

**There is now a real cruise throttle (~0.34).** Peak thrust is modelled low
(~3–5 N vs ~7–8 N real) and current runs a bit high; **treat climb rate and
endurance from this model as conservative.** Static still NaNs — a known
limitation, not a regression.

## 5. Recommendation

- **For the cruise-aero work this model exists for:** current state is fine.
  `verify_model.py` uses a power-off glide so it is unaffected; for powered
  runs, start airborne and use throttle ≈ 0.34, never trim from static.
  JSBSim's `do_simple_trim` does not converge with a brushless motor (it holds
  time so the motor never spins up) — use the manual/decoupled trim in
  `verify_model.py`.
- **For real propulsion numbers** (static thrust, transition acceleration,
  climb rate, endurance): do not rely on JSBSim's electric model at this
  scale. Take a measured thrust-vs-airspeed curve (bench test, or eCalc /
  manufacturer data) and feed it in as a `<thruster type="DIRECT">` lookup
  table — that decouples propulsion fidelity from the motor model entirely.
- **Hardware:** re-examine 2200 KV for the forward motor. 1400 KV + 1045 is
  the better static+cruise compromise; if 2200 KV is kept, pair it with a
  smaller prop (8×4.5 / 9×4.5) for the forward unit.
