# CoconutQuadplane — Aerodynamic Analysis Results

Method: NeuralFoil (XFOIL-surrogate) 2D section data + AeroSandbox AeroBuildup
(component build-up, finite-span) for the 3D aircraft. Cross-checked against
AeroSandbox VLM. n_crit = 7.0 (matte foam surface). Cruise Re ≈ 191325
at V = 12.0 m/s, MAC = 236 mm.

## Wing planform (committed 1.30 m span)
| | value |
|---|---|
| area S_w | 0.3 m² |
| span b | 1.3 m |
| root / tip chord | 288 / 173 mm |
| MAC | 236 mm |
| aspect ratio | 5.63 |
| wing incidence | 1.0° (refined down from the memo's 2° — see trim note) |

## 2D sections at cruise Re ≈ 200k (NeuralFoil, n_crit 7)
| | SD7037 (wing) | NACA 0009 (tail) |
|---|---|---|
| lift slope a₀ (/rad) | 6.193 | 6.902 |
| α (L=0) | -3.32° | 0.07° |
| Cd,min | 0.0086 | 0.0086 |
| Cl,max | 1.296 @ 13.0° | 0.950 |
| Cm,ac | -0.081 | 0.000 |

## 3D aircraft derivatives (about wing AC ref; NP/SM below)
| coefficient | value | note |
|---|---|---|
| C_Lα | 5.318 /rad | whole aircraft |
| C_L0 | 0.430 | at α=0 (incl. wing incidence + camber) |
| C_D0 | 0.0196 | parasite (wing+tail+pod+booms) |
| k (C_Di = k·C_L²) | 0.0713 | → Oswald e ≈ 0.793 |
| C_mα | -1.671 /rad | **negative = statically stable** |
| C_m0 | -0.068 | |
| C_nβ | 0.0215 /rad | current fins — weakly stable, below target (see fin sizing) |
| C_lβ | 0.0028 /rad | dihedral effect |
| C_mq | -10.133 /rad | pitch damping |
| C_nr | -0.0416 /rad | yaw damping |
| C_lp | -0.443 /rad | roll damping |

## Neutral point & static margin
- x_np = 152 mm aft of wing-LE-MAC (**59.9% MAC**)
- **design CG = 33% MAC → static margin = 27% MAC**
- for reference: SM = 35% at 25% MAC CG, 20% at 40% MAC CG

> The generous H-tail (V_H ≈ 0.45) puts the NP well aft, so the aircraft is
> quite stable at any conventional CG. ~25% SM is high but fine here — pitch
> control is by the wing elevons (ample authority) and high stability suits an
> autonomous survey platform. A future iteration could trim V_H toward 0.35.

## Cruise trim (1.4 kg AUW, 12.0 m/s)
- required C_L = 0.519
- **trim α = 1.25°**, **tail incidence i_h = -1.79°
  relative to the fuselage** (≈ -2.79° relative to the
  wing chord) — replaces the −1.5° placeholder
- at a 40%-MAC CG the trim tail incidence would be -0.58°
- cruise L/D ≈ 13.5; solver converged: True

> **Trim study finding:** at the memo's 2° wing incidence the aircraft trims at
> a *negative* α for every sensible speed (the SD7037 + 2° built-in lift is too
> much for this light wing loading). Reducing wing incidence to **1°** and
> setting cruise to **12 m/s** gives a healthy +1–2° trim α and better L/D.
> Recommend updating the memo (i_w) and the SITL `AIRSPEED_CRUISE` (16 → ~12).

## Vertical fin sizing
The current twin fins give only **C_nβ ≈ 0.004 /rad**
at ~200 cm² — weakly stable, well below what a rudderless UAV doing autonomous
nav near the canopy needs. Target **C_nβ ≥ 0.07 /rad**
(pod + boom keel area is destabilising and there is no rudder to help).

Analytical body term (Munk slender-body): C_nβ,pod = -0.0273,
C_nβ,booms = -0.0029 /rad.

| S_v total (cm²) | V_V | C_nβ fins+wing | C_nβ + bodies (analytic) | C_nβ AeroBuildup |
|---|---|---|---|---|
| 100 | 0.013 | +0.0269 | -0.0034 | -0.0034 |
| 150 | 0.019 | +0.0346 | +0.0043 | +0.0043 |
| 200 | 0.026 | +0.0483 | +0.0181 | +0.0181 |
| 250 | 0.032 | +0.0665 | +0.0363 | +0.0363 |
| 300 | 0.038 | +0.0862 | +0.0559 | +0.0559 |
| 350 | 0.045 | +0.1051 | +0.0749 | +0.0749 |
| 400 | 0.051 | +0.1223 | +0.0921 | +0.0921 |

- combined-analytic method → S_v,total ≈ 337 cm²
- AeroBuildup method → S_v,total ≈ 337 cm²
- **recommended: S_v,total ≈ 340 cm²
  (170 cm² per fin), V_V ≈ 0.044**
  (current ≈ 210 cm², V_V ≈ 0.027 — a
  62% area increase)
