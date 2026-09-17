# Quadplane Project — Review 2 Roadmap (2-Day Sprint)

## Scope note (read first)
**Current scope, in one line:** a small custom quadplane, controlled by
ArduPilot QuadPlane firmware, flying a pre-computed route over a coconut
plantation to detect (1) coconut ripeness/yield and (2) frond pruning needs —
built and tested entirely in simulation for now, no physical hardware
purchased yet.

## Urgent — do today, before anything else
- [ ] **Email your guide now** requesting approval for Review 2 components
      (per Slide 2 of the PPT template) — the stated deadline (01-09-2026)
      has already passed.
- [ ] **Raise the project title question with your guide directly.** Review 2
      guidelines state titles cannot change after Review 1, and your Review 1
      title was the mango-harvesting system. Get explicit guidance on how to
      handle this before building the report/PPT around the quadplane.

---

## Reference: Finalized Design (for all three people to pull from)

### Mission
Two-tier "scout-then-confirm" architecture:
1. **Scouting pass** (in advance): maps approximate tree/bunch positions,
   ripeness confidence, frond condition.
2. **Route planning**: computes an efficient path across only *active*
   waypoints; trees marked "cleared" after harvest are dynamically pruned
   from future routes.
3. **Live confirm**: during the actual flight, each waypoint is re-detected
   (still there / still ripe / exact position) with real-time obstacle
   avoidance, since the aircraft follows a precomputed route but the canopy
   is not static.

### Airframe — Quadplane (Hybrid VTOL Fixed-Wing)
- Chosen over tilt-rotor/tailsitter for mechanical simplicity, mature
  ArduPilot firmware support, and real hobbyist precedent.
- Reference/benchmark: Raefly VT240 Pro (commercial ArduPilot-based VTOL) —
  used as a design reference, not a product being purchased or copied exactly.
- Pod/body: ~40–50cm.
- Wing: ~1.2–1.5m span (target ~1.3m), EPP or EPO foam (not rigid EPS —
  needed for crash-resistance/reusability), reinforced with a carbon spar.
- **Open decision, not yet resolved: tailed vs. tailless (flying wing)
  configuration.** This determines airfoil choice (a tailless layout needs a
  reflexed airfoil, e.g. Eppler 186 or MH45, for pitch stability — a normal
  airfoil will not be stable without a tail).

### Propulsion
| Part | Spec |
|---|---|
| Lift motors ×4 | A2212 2200KV, standard quad-X arrangement (2 front, 2 back) |
| Forward/cruise motor ×1 | A2212 2200KV, nose or pusher mounted |
| ESCs ×5 | SimonK 30A |
| Propellers | 1045 (10×4.5), 2 CW + 2 CCW for lift, +1 for forward |

### Flight Control
- **Flight controller:** Darkmatter Brahma F4 MK-III (STM32F405) — confirmed
  official ArduPilot support, 9 PWM outputs (covers 5 motors + 2 elevon
  servos with headroom to spare).
- **Firmware:** ArduPilot QuadPlane (not custom, not ESP32-based) — the
  hover-to-cruise transition, motor mixing, and VTOL Assist safety logic are
  configured via parameters, not written from scratch.
- **Control surfaces:** 2 elevons (combined aileron+elevator per wing, since
  there's no separate tail-mounted elevator) — TowerPro MG90S digital
  metal-gear servos.
- **Control mode:** fully autonomous, no RC transmitter — waypoint missions
  uploaded from the ground station.

### Sensors & Camera
- **VL53L1X Time-of-Flight sensor** — altitude/ranging.
- **Camera (ESP32-CAM class)** — RGB, essential since both detection tasks
  are color-based (ripeness = brown/green change; frond health = color +
  droop). No thermal sensor in the current design (explicitly dropped).

### Compute Architecture
- No heavy onboard compute. Detection inference runs on a laptop.
- Given this is pure surveillance (no live pick/action decision), the
  architecture favors **recording onboard, processing after landing**
  over continuous live streaming — avoids the WiFi-range/canopy-dropout
  problem for a mission that doesn't need instant results.

### Software Stack
| Layer | Tool/Approach |
|---|---|
| Flight firmware | ArduPilot QuadPlane (configured, not coded) |
| Simulation | ArduPilot SITL — built-in QuadPlane physics model, no external simulator required to start |
| Higher-fidelity aerodynamics (later) | JSBSim, for a custom aerodynamic model of the actual wing once the basic SITL loop works |
| Ground-station link | `pymavlink` / `DroneKit` (Python, MAVLink protocol) — mission upload, telemetry reads |
| Route planner | Custom Python: computes route over active waypoints, applies dynamic pruning, exports a MAVLink-compatible mission |
| Persistent data store | Per-tree/per-bunch status (last visit, confidence, active/cleared) — SQLite or structured files, not a heavy DB |
| Detection models | **Two separate models** (not merged): (1) coconut ripeness/yield, (2) frond pruning/health — both RGB-based |
| Dashboard | Backend bridges MAVLink telemetry via WebSocket; frontend (map view via Leaflet, mission time-remaining, live status) |
| 3D/CAD | FreeCAD + AirPlaneDesign workbench (NACA rib generator); airfoil sourced from airfoiltools.com; XFLR5/XFOIL for free aerodynamic validation |

### Cost (for context/report — not being spent in this 2-day sprint)
New-purchase estimate ≈ ₹8,200–10,900 (confirmed: motor/ESC/prop bulk combo
₹4,370, servos ₹538; estimated: flight controller, ToF, camera). **No
hardware is being purchased for this review — everything is simulated.**

### Regulatory context (for feasibility section)
Estimated AUW places this in India's DGCA "Micro" category (250g–2kg):
registration required for real future flight, recreational altitude limit
well above what a coconut palm (15–30m) requires — not a constraint on the
mission itself, just a compliance step before any real-world flight.

---

## Work Split — 2 Days, 3 People

### Person 1 — Simulation & Flight Software
**Goal: a running SITL demo to show live or record for the "Experiments and Results" slide.**
- [ ] Clone and build ArduPilot; launch SITL with the built-in QuadPlane
      physics model.
- [ ] Configure QuadPlane parameters matching the finalized spec: 5 motors
      (4 lift + 1 forward), 2 elevon outputs, Q_ENABLE and frame class/type
      set for a standard quad-X lift layout.
- [ ] Connect Mission Planner or QGroundControl to SITL; verify arm, takeoff,
      hover, and a basic transition to forward flight.
- [ ] Write a small `pymavlink` script that uploads a simple multi-waypoint
      mission and logs telemetry — this is the seed of the ground-station
      link the route planner will eventually use.
- [ ] Capture screenshots/screen recording of a working SITL flight —
      this is your primary source material for the Experiments and Results
      slide and report section.
- [ ] Document current parameter set and known limitations (e.g., default
      generic aerodynamics, not yet your specific wing/airfoil).

### Person 2 — Detection Pipeline & Route Logic
**Goal: a demonstrable (even if small-scale) proof of concept for the two detection tasks, plus the planning logic.**
- [ ] Source a small sample image set for coconut ripeness (even a handful
      of representative images is enough for a Review 2 proof of concept —
      full dataset collection is post-review work).
- [ ] Set up a basic classification/detection model skeleton for ripeness
      (transfer learning on a small pretrained model is reasonable given
      the timeline).
- [ ] Do the same, separately, for frond health/pruning — keep the two
      models separate, not merged, per the finalized design decision.
- [ ] Implement the per-tree data store (status, last-visit, confidence) —
      SQLite is enough.
- [ ] Implement the route planner: given a list of active waypoints,
      compute a visiting order; implement the "dynamic pruning" rule that
      drops cleared trees from future runs.
- [ ] Produce sample output (even synthetic/mocked detection results) to
      demonstrate the pipeline end-to-end for the demo.

### Person 3 — Documentation, Literature, and Presentation
**Goal: report draft + PPT deck, built on what Persons 1 and 2 produce.**
- [ ] Send the guide-approval email today (see Urgent section above).
- [ ] Gather literature specific to the **current** scope: VTOL/quadplane
      UAV design, ArduPilot QuadPlane systems, agricultural/plantation drone
      surveillance, palm/coconut health monitoring via UAV or computer
      vision. (Prior mango/coconut-harvesting-mechanism papers are out of
      scope now — new references are needed for this literature review.)
- [ ] Write report sections: Introduction (Background/Motivation/Scope),
      Literature Review, Research Gap, Objectives (SMART-format), Problem
      Statement, Feasibility Study (Technical/Economic/Social — technical
      feasibility content already exists from the design work above).
- [ ] Fill Hardware and Software Specification sections directly from the
      Reference section of this document.
- [ ] Build the Data Flow Diagram and Use Case Diagram (mandatory) per the
      guidance in the chat — data flow across the camera → detection →
      dashboard → route planner → flight controller chain; use cases for
      the Operator and Flight Controller actors. Class/Sequence diagrams
      are optional — include only if time allows, scoped to the software
      layer (detection pipeline, route planner), not the airframe.
- [ ] Assemble the PPT from the Review 2 template: Aim, Abstract, Literature
      Review, Research Gap, Objectives (SDGs + outcome type — carry over
      from Review 1 unless the guide says otherwise given the scope change),
      Framework/Architecture/Block Diagram, Functional Requirements, Modules,
      Experiments and Results (from Person 1's SITL capture and Person 2's
      pipeline demo), Conclusion, References.

## Coordination checkpoints
- **End of Day 1:** Person 1 has a working SITL flight; Person 2 has the
  route planner logic working (even on mock data); Person 3 has the guide
  approval sorted and literature review drafted.
- **Day 2 morning:** Person 3 pulls Persons 1 and 2's outputs into the
  report and PPT; leave the afternoon for a full run-through and Q&A prep.
