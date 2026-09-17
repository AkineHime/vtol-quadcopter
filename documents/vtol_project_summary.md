# VTOL Quadplane Project — Complete Summary

## 1. Mission

An autonomous VTOL quadplane for **coconut plantation surveillance**, built to
answer two questions per tree without a human having to climb it first:

1. **Ripeness/yield** — which trees (or bunches) currently have coconuts
   ready to harvest.
2. **Frond health** — which fronds are dead, dying, or pest-damaged and need
   pruning.

**Core motivation:** manual coconut-tree climbing is genuinely dangerous;
the drone's entire value is removing unnecessary climbs, not automating the
harvest itself. This is explicitly a **surveillance-only** system —
harvesting mechanisms (dual-arm gripper, iris capture, single-nut picking)
were designed through in detail but set aside on cost/complexity grounds.
An intruder/security-detection feature was proposed and is **on hold**, not
part of current scope.

## 2. Why This Architecture

- Coconut palms (15–30m) put the target well above what ground robots or
  short-hop multirotors handle efficiently.
- A pure multirotor gets ~30–45 min of flight time on a mapping mission;
  hybrid VTOL platforms routinely exceed 90–150 min — the efficiency gain
  matters directly for covering a whole plantation.
- **Quadplane** (fixed lift motors + fixed forward motor, nothing tilts) was
  chosen over tilt-rotor and tailsitter specifically for build simplicity,
  ArduPilot's mature QuadPlane firmware support, and real hobbyist precedent.
- Benchmarked against two commercial references, both rejected as products
  but useful as design context: the **Raefly VT240 Pro** (ArduPilot-based,
  confirmed the architecture is sound, but priced and sized for commercial
  surveying, not a student build) and the **ThunderB-VTOL** (a military
  ISTAR platform — wrong category entirely, export-controlled).

## 3. Mission Architecture — Scout, Plan, Confirm

1. **Scouting pass** (run in advance): maps approximate tree/bunch
   positions, a ripeness confidence score, and frond condition per tree.
2. **Route planning**: computes an efficient path across only *active*
   waypoints. **Dynamic pruning** drops trees already marked "cleared" from
   future routes — no repeat visits to trees with nothing left to check.
3. **Live confirm**: during the actual flight, each waypoint gets
   re-detected against three checks — still there, still relevant/ripe, and
   exact current position — with real-time obstacle avoidance, since the
   canopy shifts between the scouting pass and the real flight.

## 4. Finalized Hardware

| System | Choice | Why |
|---|---|---|
| Airframe | Custom quadplane, ~40–50cm pod, ~1.2–1.5m wing (target ~1.3m) | Small pod fits the "compact body" goal; wing sized for stable transition per real-world VTOL guidance |
| Wing material | EPP or EPO foam + carbon spar | Crash-resistant and reusable (not rigid EPS, which shatters) |
| Lift motors | 4× A2212 2200KV, standard quad-X | Real bulk pricing confirmed; ~3:1 thrust margin on estimated AUW |
| Forward motor | 1× A2212 2200KV | Same part number as lift motors — simpler sourcing/spares |
| Propellers | 1045 (10×4.5), 2 CW + 2 CCW + 1 forward | Matched pairing to the A2212 combo |
| ESCs | 5× SimonK 30A | Current draw for this motor combo (~10–14A) fits comfortably within rating |
| Flight controller | Darkmatter Brahma F4 MK-III (STM32F405) | Confirmed official ArduPilot support; 9 PWM outputs covers 5 motors + 2 servos with headroom |
| Control surfaces | 2 elevons | Combined pitch+roll control (no separate tail elevator) |
| Servos | TowerPro MG90S, digital, metal gear | Confirmed real spec (not an inflated listing); ₹269 each, confirmed via Robu.in |
| Ranging sensor | VL53L1X (Time-of-Flight) | Better than ultrasonic against thin/angled obstacles like branches |
| Camera | ESP32-CAM class, RGB | Both detection tasks are color-based — this is the sensor doing the mission's real work |
| Onboard compute | None (deliberately) | Detection runs on a laptop; footage recorded onboard, processed after landing rather than streamed live, since surveillance isn't time-critical |
| Control mode | Fully autonomous | No RC transmitter for normal operation (keep one on hand for safety override during test flights) |

**Open decision, not yet resolved: tailed vs. tailless (flying wing).** This
determines airfoil choice — a tailless layout needs a reflexed airfoil
(e.g. Eppler 186, MH45) for pitch stability; a normal airfoil only works
with a separate tail.

### Rejected/superseded choices, and why (context for the report's design-rationale section)
- **ESP32 as flight controller / multiple ESP32s** — not real-time
  deterministic, and loses ArduPilot's tested QuadPlane transition logic
  entirely; multi-ESP32 adds a distributed-sync problem on top.
- **Thermal sensor (MLX90640)** — ~₹5,000 alone (the entire original
  budget), and doesn't serve color-based detection or reliably see
  ambient-temperature obstacles like branches.
- **Ultrasonic ranging** — poor reflection off thin, angled obstacles;
  superseded by the VL53L1X ToF sensor.
- **3-motor tricopter lift** — would need an added yaw-control tilt servo
  and gives up motor redundancy; standard 4-motor quad-X was simpler.
- **BotWing F405 flight controller** — likely only 4 motor outputs,
  insufficient for 5 motors + 2 servos (7 needed); superseded by Brahma F4.
- **SG90 / "S3003 12kg" servos** — plastic gears (fail under VTOL vibration)
  and analog control (risk of overheating on ArduPilot's shared 400Hz PWM
  groups); the S3003 listing's torque spec was also confirmed fake.
- **MG946R servo** — genuinely metal-gear and digital, but 55g and 13kg-cm
  is real overkill for a small elevon; superseded by the lighter MG90S.
- **Motor-only directional control (no elevons)** — lift motors throttle
  down during cruise for efficiency, so differential thrust isn't available
  then; a single forward motor can't produce roll/pitch alone. ArduPilot's
  Q_ASSIST exists for emergency motor-assist but is a safety net, not a
  substitute for continuous elevon control.

## 5. Software Architecture

| Layer | Approach |
|---|---|
| Flight firmware | ArduPilot QuadPlane — configured via parameters, not custom-coded |
| Simulation | ArduPilot SITL — has a **built-in** QuadPlane physics model, no external simulator needed to start |
| Higher-fidelity aerodynamics (later) | JSBSim, for a custom model of the actual wing once the basic SITL loop works |
| Ground-station link | `pymavlink`/`DroneKit` — mission upload, telemetry reads |
| Route planner | Custom Python — route over active waypoints + dynamic pruning, exports a MAVLink-compatible mission |
| Data store | Per-tree/bunch status (last visit, confidence, active/cleared) — SQLite is enough at this scale |
| Detection | **Two separate models** — ripeness/yield and frond health — kept separate rather than merged; both need Tamil Nadu-specific labeled data (no existing literature covers TN-predominant cultivars, which is real novelty) |
| Dashboard | Backend bridges MAVLink telemetry over WebSocket; frontend shows live path (Leaflet map), time-remaining, battery, detection results |
| CAD | FreeCAD + AirPlaneDesign workbench (has a NACA rib generator) — chosen over Blender for engineering precision; airfoil selected from airfoiltools.com (established, published designs — no aerodynamics expert required to select one); XFLR5/XFOIL for free stability/performance validation |

## 6. Cost (planning reference — nothing purchased yet)
New-purchase estimate ≈ **₹8,200–10,900** (motor/ESC/prop bulk combo and
servos are confirmed real prices; flight controller/ToF/camera are
estimates). Full total including already-sourced foam and battery ≈
**₹9,500–14,200**. Current sprint is simulation-only — no hardware bought.

## 7. Regulatory Context
Estimated AUW places this in India's DGCA "Micro" category (250g–2kg):
registration required before any real flight, but the altitude ceiling
(60–120m depending on source) comfortably clears what a coconut palm
(15–30m) requires — not a mission constraint, just a pre-flight compliance
step for later.

## 8. Progress So Far
- **Review 1 PPT** filled (VIT SCOPE template) — note: built around the
  original mango-harvesting title; the project has since pivoted, and the
  title-change restriction for Review 2 needs direct clarification from
  your guide.
- **Placeholder 3D model** generated (STL, NACA 2412 airfoil, placeholder
  dimensions) — a rough proportional mockup, not final engineering geometry.
- **Review 2 roadmap** created — 3-person work split (Simulation/Flight
  Software, Detection Pipeline/Route Logic, Documentation/Presentation),
  with two urgent flagged items (overdue guide-approval email, title
  conflict).
- **ArduPilot SITL build attempted** in a sandboxed environment — cloned,
  configured, and compiled roughly half the codebase (~690/1426 files)
  before the sandbox's single-core/time-limited environment stopped making
  reliable progress. Full build commands were handed off for you to run on
  normal multi-core hardware, where this should complete in one pass.

## 9. Remaining Work
- [ ] Resolve tailed vs. tailless configuration (blocks airfoil choice)
- [ ] Select a real airfoil (airfoiltools.com), validate in XFLR5, build the
      actual wing geometry in FreeCAD
- [ ] Complete the ArduPilot SITL build on real hardware; configure QuadPlane
      parameters to match the finalized 5-motor/2-elevon layout
- [ ] Build and test the `pymavlink` ground-station script (mission upload,
      telemetry read)
- [ ] Build both detection pipelines (ripeness, frond health) — even a
      small proof-of-concept is enough for Review 2
- [ ] Build the route planner and persistent per-tree data store
- [ ] Build the dashboard (WebSocket backend + map/status frontend)
- [ ] Resolve the Review 1 title conflict with your faculty guide
- [ ] Send the overdue guide-approval email for Review 2
- [ ] Write the report sections and assemble the Review 2 PPT
- [ ] *(Post-review)* actual physical procurement/build, DGCA registration
      before any real-world flight
