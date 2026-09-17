# Airframe Decision — Tail Configuration & Airfoil Selection

**Status:** Tail configuration decided. Airfoil chosen and **now backed by real
2D+3D analysis** (§2, §4). Vertical fin re-sized (§3). Tail incidence solved (§4).
**Feeds:** Review 2 Hardware Specification section; the FreeCAD fin model
(`models/freecad/vertical_fin.FCStd`); the JSBSim model
(`flight_software/jsbsim/aircraft/CoconutQuadplane/`).
**Supersedes:** the "open decision, not yet resolved" wording in
`vtol_project_summary.md` (§4) and `quadplane_roadmap.md`; and the −1.5°
tail-incidence / V_V ≈ 0.02 placeholders previously in this file.

> **Analysis method (§6 for detail):** SD7037 and NACA 0009 run through
> **NeuralFoil** (an XFOIL surrogate — the packaged XFOIL 6.99 SIGFPEs on every
> real section on this machine, and AVL 3.36 won't build headless) at the
> cruise Reynolds number; the 3D aircraft through **AeroSandbox AeroBuildup**
> (component build-up) cross-checked with its **VLM** and a Munk slender-body
> fuselage term. Everything is scripted in `aero/analyze.py`; raw output in
> `aero/RESULTS.md` and `aero/coefficients.json`. **XFLR5's GUI was not
> required** — see §6.

---

## 1. Decision: tailed, conventional layout

The aircraft is **tailed** — a main wing plus a separate fixed horizontal
stabiliser and twin vertical fins at the end of the tail booms. This was the
lean in `quadplane_roadmap_2.md` and is now confirmed.

**Why tailed, not a flying wing:**

| Factor | Tailed | Tailless (flying wing) |
|---|---|---|
| Pitch stability | Tail provides it — wing airfoil is free to be efficient | Needs a **reflexed** airfoil (Eppler 186, MH45), which carries a built-in drag and CLmax penalty |
| Airfoil choice | Any cambered section; huge catalogue of well-documented low-Re airfoils | Small set of reflexed sections, thinner, harder to build in foam |
| CG sensitivity | Forgiving — usable CG range is wide | Very tight; a 5–10 mm CG error is a real handling problem |
| Build (foam + booms) | Booms already carry the lift motors; adding tail surfaces on them is nearly free | Saves the tail, but the payoff is undermined by the reflex-airfoil and CG cost |
| Pitch authority in VTOL→cruise transition | Fixed tail keeps the aircraft tracking while airspeed builds and elevons are still marginally effective | Relies entirely on elevons + Q_ASSIST through the low-speed regime |
| ArduPilot fit | Standard `QUADPLANE` with plane surfaces; nothing unusual | Supported (`plane-tailsitter`/elevon frames) but less of the tuning base applies |

The decisive points for this project: (a) the tail lets us pick a **normal
cambered airfoil with published low-Re polars**, which removes the need for
any original aerodynamic design; (b) the tail booms exist regardless, so the
tail is cheap to add; (c) a wide CG range matters for a student build where
the battery/payload position will shift during integration.

### 1.1 Control-surface note (a real tradeoff we are accepting)

The spec is **2 elevons on the main wing, fixed (non-moving) tail, no tail
elevator, no rudder**. So the wing elevons provide *all* active pitch and roll
control; the tail and fins are passive stabilisers only.

- **Upside:** two servos total, no tail control linkage down the boom, no
  rudder mixing.
- **Checked (`aero/control_authority.py`, AeroBuildup with a full-span 28%c
  elevon, V = 12 m/s):**

  | | value | verdict |
  |---|---|---|
  | C_mδe | 0.38 /rad | |
  | C_lδa | 0.72 /rad | full-span elevons — very powerful |
  | trim elevon, CG 25 / 33 / 40 % MAC | +1.8° / +0.1° / −1.4° | **1–8% of travel** — the −1.8° tail incidence keeps trim near neutral |
  | pull-up load factor (spare elevon) | **2.6 g** (wing-stall limited; elevon alone could force 3.9 g) | adequate |
  | nose-up pitch accel at full elevon | 27 rad/s² | very high |
  | steady roll rate, full elevon | **≈ 650 °/s** | far more than needed |
  | steady roll rate, half throw kept for pitch | ≈ 330 °/s | still ample |

- **Verdict: authority is not marginal — it is abundant.** No hinged tail
  elevator is needed. The real work is the *opposite*: ArduPilot must
  rate-/throw-limit the elevons (they can stall the wing in pitch and roll
  faster than 600 °/s), and the mixer must give pitch trim priority over roll
  when both are commanded (`MIXING_GAIN`, servo endpoints, `RLL2SRV`/`PTCH2SRV`).
- **One caveat:** this is the cruise point. Elevon effectiveness falls with V²,
  so near stall / low-speed approach the margin shrinks and a hard roll input
  could provoke tip stall. Mitigated here because landing is VTOL — the
  low-speed fixed-wing regime is only briefly crossed in transition (Q_ASSIST
  active). Confirm on the first real flights.

---

## 2. Wing airfoil

### 2.1 Operating point (now committed)

| Quantity | Value | Basis |
|---|---|---|
| Span | **1.30 m** | committed — matches the "compact" goal and the JSBSim/CAD models |
| Wing area / MAC / AR | 0.30 m² / **236 mm** / **5.63** | trapezoid, taper 0.6 |
| Cruise speed | **12 m/s** | refined down from 16 (see §4 trim note) |
| **Cruise Reynolds number** | **≈ 1.9 × 10⁵** | ρ·V·MAC/μ; envelope ~1.5–2.5 × 10⁵ |
| AUW | 1.4 kg | mid DGCA-Micro band |
| Wing incidence | **1.0°** | refined down from 2° (§4) |

Low-Reynolds-number territory — the SD7037 was picked for exactly this band.

### 2.2b Real 2D section polars (NeuralFoil, Re ≈ 2 × 10⁵, n_crit 7)

| | **SD7037** (wing) | **NACA 0009** (tail) |
|---|---|---|
| 2D lift slope a₀ | 6.19 /rad | 6.90 /rad |
| zero-lift angle α₀ | −3.3° | 0.0° (symmetric) |
| minimum profile Cd | 0.009 | 0.009 |
| Cl,max | **1.30 @ 13°** (gentle) | 0.95 |
| Cm,ac | −0.081 | 0.000 |

SD7037's soft, high stall and low drag at this Re are confirmed — it remains
the right pick. NACA 0009 behaves as a clean symmetric section.

### 2.2 Shortlist

| Airfoil | Thick / camber | Character at Re ≈ 2×10⁵ | Foam buildability |
|---|---|---|---|
| **SD7037** *(recommended)* | 9.2% / 2.5% | Designed for this exact Re band; high L/D, gentle stall, well-documented polars | Slightly cambered lower surface — cuttable, needs a proper root/tip jig |
| **NACA 2412** *(low-effort fallback)* | 12% / 2% | Benign, docile stall, enormous data set; a bit more drag than SD7037 | Easy — thick enough to hot-wire cleanly and hold a straight TE; this is the current placeholder value |
| **Clark Y** *(build-simplicity option)* | 11.7% / 3.4% flat-bottom | Good CLmax, more abrupt stall, higher drag | Easiest — flat bottom sits on the build board, simplest spar jig |
| S3021 | 9.2% / 3.6% | Similar to SD7037, slightly higher lift, thinner TE | Similar to SD7037 |
| AG35 / AG37 | ~7% / low | Excellent efficiency, but very thin trailing edge | Hard in foam — thin TE crushes; better suited to moulded/D-box |

### 2.3 Recommendation

**Primary: SD7037.** Best cruise efficiency in the shortlist at our Reynolds
number, which directly serves the mission (endurance over a whole plantation),
and its gentle stall matters for a fixed-tail aircraft whose only pitch
control is wing-mounted. Polars are published on airfoiltools.com for
Re = 50k–1M, so XFLR5 validation is a cross-check, not original work.

**If build risk dominates: NACA 2412.** Keeps the placeholder model's airfoil,
so nothing downstream changes; thick section is the most forgiving to cut and
assemble straight; small efficiency cost is tolerable for Review 2.

Do **not** pick a reflexed airfoil — that was only needed for the (rejected)
tailless option and would waste performance here.

### 2.4 Tail airfoil

**NACA 0009** (symmetric, 9%). Symmetric because the stabiliser is set near
zero lift; 9% rather than thinner so a foam tail is stiff enough to not flutter
and is easy to cut. NACA 0010–0012 is an acceptable substitute if the foam
stock or cutter favours a thicker section.

---

## 3. Tail volumes and the vertical-fin re-size

Committed geometry: S_w = 0.30 m², b = 1.30 m, MAC = 236 mm, tail arm 0.50 m.

| Quantity | Value | Target | Verdict |
|---|---|---|---|
| Horizontal tail area S_h | 0.063 m² | — | — |
| **Horizontal tail volume V_H** | **0.45** | 0.4 – 0.6 | **OK — keep** (if anything slightly generous; see §4 SM note) |
| Vertical fin area (twin, *current* KCL) | ≈ 210 cm² total | — | — |
| **V_V current** | **≈ 0.027** | — | too small |
| Aircraft **C_nβ with current fins** | **≈ +0.02 /rad** | **≥ 0.07** | **fails** — weakly stable, gust-marginal |

### The fin is undersized — enlarge it ~60%

The pod (46 cm) and the four lift booms sit ahead of the CG and are
destabilising in yaw. Two independent estimates agree:

- AeroBuildup (crossflow pod model): fins must reach **≈ 340 cm² total** for
  C_nβ ≥ 0.07.
- Munk slender-body pod term (C_nβ,bodies ≈ −0.030) + VLM fin effectiveness:
  same answer, ≈ 340 cm².

| S_v total | V_V | C_nβ (fins+wing) | C_nβ (with bodies) |
|---|---|---|---|
| 210 cm² (current) | 0.027 | +0.049 | +0.021 |
| **340 cm² (recommended)** | **0.044** | **+0.101** | **+0.071** |

**Decision: vertical fins → 170 cm² each (340 cm² total), V_V ≈ 0.044.**
Keep the twin-fin layout (boom end-plates, induced-drag benefit, redundancy).
New fin geometry is built parametrically in
`models/freecad/vertical_fin.FCStd` (**root 104 mm, tip 57 mm, height 210 mm,
LE sweep 22°, NACA 0009, 14 mm thick** — driven by a Spreadsheet). JSBSim
`<metrics><vtailarea>` and the `C_nβ` term are set to the enlarged fin.

The JSBSim power-off check confirms it: a 10° sideslip release now washes out
to <0.1° within ~3 s (well-damped dutch roll).

---

## 4. Tail incidence, CG and stability — solved

3D aircraft coefficients (AeroBuildup, cross-checked with VLM), V = 12 m/s:

| Coefficient | Value | Note |
|---|---|---|
| C_Lα | 5.32 /rad | |
| C_L0 | 0.43 | wing incidence + camber |
| C_D0 | 0.020 | build-up |
| k (C_Di = k·C_L²) | 0.071 | Oswald e ≈ 0.79 |
| C_mα (wing-AC ref) | −1.67 /rad | statically stable |
| C_mq | −10.1 /rad | strong short-period damping |
| Neutral point | **60% MAC** | generous H-tail pushes it well aft |

**Refined design point:**

| Parameter | Was | **Now** | Why |
|---|---|---|---|
| Wing incidence | 2° | **1.0°** | 2° trimmed at *negative* α at any sensible speed for this light wing loading |
| Cruise speed | 15–16 | **12 m/s** | efficient for this wing; also better for camera stability |
| Design CG | 28–32% MAC | **33% MAC** | conventional/buildable (battery near wing) |
| Static margin | target 10–15% | **≈ 27%** | the H-tail (V_H 0.45) makes it inherently very stable; acceptable — pitch is by wing elevons (ample authority) and high stability suits an autonomous survey platform. A later pass could trim V_H toward 0.35. |
| **Tail incidence** | −1.5° (guess) | **−1.8° vs fuselage** (−2.8° vs wing chord) | solves C_m = 0 at cruise C_L = 0.52, elevons neutral, CG 33% MAC |

At a 40%-MAC CG the trim tail incidence would be −0.6°; −1.8° corresponds to
the conventional 33% CG. Cruise trim: **α ≈ +1.3°, L/D ≈ 13.5**.

**Verified in JSBSim** (`flight_software/jsbsim/verify_model.py`, power-off
glide + disturbances): loads and runs clean, glide L/D ≈ 11.8, lift = weight,
a pitch pulse recovers (1.3° peak → 0.2° residual), phugoid bounded, 10°
sideslip washes out. All 8 checks pass.

Still open: elevon *control-authority* / hinge-moment check across the CG range
(elevons-only vs. adding a hinged tail elevator). That needs a control-surface
model — either an AVL run with a wing flap, or a bench measurement.

---

## 5. Open items before the wing is built

1. ~~Span mismatch~~ — **resolved: 1.30 m** committed everywhere.
2. ~~Run the 3D stability analysis~~ — **done** (§4), scripted, JSBSim-verified.
   (XFLR5 GUI figures optional for the slide deck — see §6.)
3. ~~Elevon control authority~~ — **done (§1.1): abundant, no tail elevator
   needed.** Bench-confirm elevon effectiveness near stall on the first flights.
4. ~~Fin size~~ — **decided: 340 cm² total** (§3), CAD model built.
5. Add ~3° wing dihedral (assumed in the JSBSim `C_lβ`; not yet in the CAD).
6. Carry SD7037 + NACA 0009 `.dat` files (`aero/airfoils/`) into the wing/tail
   CAD. Reduce H-tail toward V_H ≈ 0.35 if a lower static margin is wanted.
7. Update `AIRSPEED_CRUISE` 16 → 12 (and `AIRSPEED_MIN` ~9) in
   `flight_software/coconut_quadplane.param` to match the refined cruise.

## 6. On XFLR5 / tooling (why the GUI wasn't needed)

| Need | Tool used | GUI? |
|---|---|---|
| 2D airfoil polars | **NeuralFoil** (XFOIL-trained surrogate) | no — scripted |
| 3D C_Lα, C_D0, C_mα, NP, C_nβ, all derivatives | **AeroSandbox AeroBuildup + VLM** | no — scripted |
| Fuselage yaw term | Munk slender-body (hand formula) | no |
| Cruise trim (α, tail incidence) | Newton solve on the above | no |
| Dynamic modes | JSBSim time-domain (`verify_model.py`) | no |

XFOIL 6.99 (Debian package) SIGFPEs on every real section here; AVL 3.36's
plot library will not compile headless. NeuralFoil and AeroSandbox's VLM are
the same physics (XFOIL data / vortex-lattice) in scriptable form, so the
XFLR5 **GUI is not required** for any of the numbers above. It would only add
its own plots for the report and a click-through dynamic-mode view. If those
figures are wanted: import `aero/airfoils/*.dat`, build the plane from the §2
/ §3 / §4 geometry, and analyse at Re 1.9 × 10⁵, V 12 m/s, CG 33% MAC.

## Sources

---

## Sources

- Selig, *New Airfoils for R/C Sailplanes*, UIUC — <https://m-selig.ae.illinois.edu/uiuc_lsat/saAirfoils.html> (SD7037 coordinates)
- NeuralFoil (Sharpe, MIT) — XFOIL-surrogate used for the 2D polars — <https://github.com/peterdsharpe/NeuralFoil>
- AeroSandbox (Sharpe, MIT) — AeroBuildup + VLM for the 3D coefficients — <https://github.com/peterdsharpe/AeroSandbox>
- Multhopp / Munk slender-body fuselage yaw term — standard result, see Etkin & Reid, *Dynamics of Flight*, §3
- SD7037 aerodynamic performance study, ScienceDirect — <https://www.sciencedirect.com/science/article/abs/pii/S2214785321036270>
- Sadraey, *Aircraft Design: A Systems Engineering Approach*, Ch. 6 "Tail Design" (tail volume coefficient ranges) — mirrored at <http://aero.us.es/adesign/Slides/Extra/Stability/Design_Tail/Chapter%206.%20Tail%20Design.pdf>
- Scholz et al., *Empennage Sizing with the Tail Volume Complemented with a Method for Dorsal Fins*, INCAS Bulletin Vol.13 No.3 (2021) — <https://www.fzt.haw-hamburg.de/pers/Scholz/Aero/AERO_PUB_INCAS_TailVolume_Vol13No3_2021.pdf>
