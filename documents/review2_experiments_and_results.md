# Review 2 — "Experiments and Results" slide content

Figures: `documents/review2_figures/` (presentation resolution, 200 dpi).

---

## Slide 1 — narrative (bullets)

**1. Simulation validation (ArduPilot SITL).**
A full autonomous mission was flown in ArduPilot SITL — VTOL takeoff,
transition to forward flight, a multi-row survey grid at 12 m/s, and a VTOL
landing back at home. Every checkpoint passed: parameter load (44/44),
mission upload round-trip, and all five flight phases (takeoff, transition,
waypoints, land, auto-disarm). *[Fig. 1]*

**2. Real aerodynamic analysis drove two design corrections.**
Section data for the SD7037 wing and NACA 0009 tail (NeuralFoil) was reduced
to a 3-D model (AeroSandbox) and produced two changes: **wing incidence 2° →
1°** and **cruise speed 16 → 12 m/s** (2° trimmed at a negative angle of
attack for this light wing loading), and the **vertical fin enlarged ~60 %**
(210 → 340 cm²), lifting yaw stiffness from an unstable-margin **C\_nβ ≈ +0.02
to +0.07 /rad**. *[Fig. 2]*
Both were verified by a power-off glide + disturbance test on the corrected
model — **8/8 checks pass**: glide L/D ≈ 12, a pitch disturbance decays from
1.3° to 0.3°, the phugoid stays bounded, and a 10° sideslip washes out to
0.04° in ~3 s (the enlarged fin working).

**3. The verification process caught a real bug.**
Integrating the ArduPilot ↔ JSBSim bridge, a built-in elevon **sign-inversion
check found the roll and pitch commands were inverted** — the aircraft rolled
left on a right command, producing positive feedback. On real hardware this
is a guaranteed loss of control on the first flight; it was caught here only
because the sign check was written into the integration procedure, and fixed
before any further testing.

**4. Current status — survey-phase instability, diagnosed, fix in progress.**
Running the same mission on the *real* aerodynamics (not ArduPilot's generic
model) completes all phases but shows altitude and airspeed instability
through the survey — airspeed swings 2–25 m/s against a 12 m/s target and the
aircraft porpoises. Root cause is identified: survey waypoints spaced tighter
than the fixed-wing turn radius, a placeholder propulsion model (the detailed
motor model is numerically unstable near hover), and control gains not yet
auto-tuned. Each has a defined fix — this is the active work item, not a
dead end. *[Fig. 3]*

---

## Key numbers (slide table)

| Metric | Result |
|---|---|
| SITL mission — flight-phase checks | all pass (takeoff · transition · grid · land · disarm) |
| Flight-dynamics verification checks | **8 / 8 pass** |
| Wing incidence (before → after) | 2° → **1°** |
| Cruise speed (before → after) | 16 → **12 m/s** |
| Vertical-fin yaw stiffness C\_nβ (before → after) | +0.02 → **+0.07 /rad** (fin area +60 %) |
| Cruise glide L/D (power-off test) | **12.1** |
| Static margin / trim α / tail incidence (3-D analysis) | 27 % MAC / +1.3° / −1.8° |
| Elevon sign bug | found & fixed in simulation (would crash on hardware) |

---

## Figures

| file | use |
|---|---|
| `review2_figures/1_sitl_mission.png` | SITL mission — planned vs flown grid + altitude/airspeed timeline |
| `review2_figures/2_aero_coefficients.png` | real 3-D C\_L / C\_D / C\_m vs α (SD7037 + NACA 0009) |
| `review2_figures/3_bridge_survey_instability.png` | mission on real aero — the survey-phase instability under diagnosis |

Recommended layout: **Slide 1** = bullets 1–2 + Fig 1 (or Fig 2) + the table.
**Slide 2** (if used) = bullets 3–4 + Fig 3.
