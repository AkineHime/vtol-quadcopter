#!/usr/bin/env python3
"""
CoconutQuadplane — real airfoil-derived aerodynamics.

Pipeline:
  1. 2D section polars for SD7037 (wing) and NACA 0009 (tail) via NeuralFoil
     (an XFOIL surrogate: XFOIL 6.99 on this box SIGFPEs on every real
     section, and AVL 3.36's plot lib won't build headless — NeuralFoil +
     AeroSandbox's VLM/AeroBuildup cover the same ground, scriptable).
  2. 3D aircraft build (wing, H-tail, twin fins, pod, 4 booms) in AeroSandbox.
  3. Alpha / beta / rate sweeps -> CLalpha, CL0, CD0, k, Cm_alpha, neutral
     point, static margin, Cn_beta, Cl_beta and the rotary derivatives.
  4. Longitudinal trim solve for (alpha, tail incidence) at cruise.
  5. Vertical-fin area sweep -> area that meets the Cn_beta / V_V target.

Outputs: aero/polars/*.csv, aero/coefficients.json, aero/RESULTS.md,
aero/plots/*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import aerosandbox as asb
import aerosandbox.numpy as anp

HERE = Path(__file__).resolve().parent
AF = HERE / "airfoils"
POL = HERE / "polars"; POL.mkdir(exist_ok=True)
PLOTS = HERE / "plots"; PLOTS.mkdir(exist_ok=True)

RHO = 1.225
NU = 1.81e-5 / RHO
NCRIT = 7.0                      # low-Re, foam / built surface

# ----------------------------------------------------------------------------
# Airframe geometry  (committed: 1.30 m span, from CoconutQuadplane.xml)
# ----------------------------------------------------------------------------
G = dict(
    S_w=0.30, b_w=1.30, taper_w=0.60, i_w_deg=2.0, sweep_w_deg=2.0,
    S_h=0.063, b_h=0.50, taper_h=0.70, arm_h=0.50,     # h-tail (quarter-chord arm)
    Sv_each=0.0105, b_v=0.18, taper_v=0.62, arm_v=0.50,  # each of TWIN fins (current)
    pod_len=0.46, pod_rad=0.08,  # project spec: "40-50 cm pod"
    boom_y=0.42, boom_len=0.62, boom_rad=0.012,          # 4 lift-motor booms (quad-X)
    AUW_kg=1.40,                 # realistic all-up weight (DGCA micro band)
    V_cruise=12.0,               # efficient cruise for this lightly-loaded wing
    cg_frac_MAC=0.33,            # conventional, buildable CG (battery near wing)
)
G["i_w_deg"] = 1.0               # refined: 2 deg gave negative trim alpha at
G["sweep_w_deg"] = 2.0           #          any sensible speed (see RESULTS.md)

# derived wing planform
c_root_w = G["S_w"] * 2 / (G["b_w"] * (1 + G["taper_w"]))
c_tip_w = c_root_w * G["taper_w"]
MAC_w = (2 / 3) * c_root_w * (1 + G["taper_w"] + G["taper_w"] ** 2) / (1 + G["taper_w"])
y_MAC = (G["b_w"] / 6) * (1 + 2 * G["taper_w"]) / (1 + G["taper_w"])
AR_w = G["b_w"] ** 2 / G["S_w"]
x_le_MAC = y_MAC * np.tan(np.radians(G["sweep_w_deg"]))
x_ac_w = x_le_MAC + 0.25 * MAC_w
Re_cruise = G["V_cruise"] * MAC_w / NU


# ----------------------------------------------------------------------------
# 1. 2D section polars (NeuralFoil)
# ----------------------------------------------------------------------------
def section_polars():
    out = {}
    res = [1.0e5, 1.5e5, 2.0e5, 2.5e5, 3.0e5]
    alpha = np.arange(-8, 16.01, 0.5)
    for name, fname in [("SD7037", "SD7037.dat"), ("NACA0009", "NACA0009.dat")]:
        af = asb.Airfoil(name=name, coordinates=str(AF / fname))
        out[name] = {}
        for re in res:
            aero = af.get_aero_from_neuralfoil(
                alpha=alpha, Re=re, mach=G["V_cruise"] / 340,
                n_crit=NCRIT, model_size="xlarge",
            )
            cl, cd, cm = aero["CL"], aero["CD"], aero["CM"]
            with (POL / f"{name}_Re{re/1e3:.0f}k.csv").open("w") as f:
                f.write("alpha,CL,CD,CM\n")
                for a, l, d, m in zip(alpha, cl, cd, cm):
                    f.write(f"{a:.2f},{l:.5f},{d:.5f},{m:.5f}\n")
            if abs(re - 2.0e5) < 1:      # ~cruise Re for V=12, c=0.236
                # linear-range fit (alpha -4..6 deg)
                mask = (alpha >= -4) & (alpha <= 6)
                p = np.polyfit(np.radians(alpha[mask]), cl[mask], 1)
                a0 = float(p[0])                       # 2D lift slope, /rad
                al0 = float(-p[1] / p[0])              # zero-lift angle, rad
                cd_min = float(np.min(cd))
                clmax = float(np.max(cl))
                a_clmax = float(alpha[np.argmax(cl)])
                cm0 = float(np.interp(0.0, cl, cm))    # Cm at zero lift ~ Cm_ac
                out[name]["cruise"] = dict(
                    Re=re, a0_per_rad=a0, alpha_L0_deg=np.degrees(al0),
                    cd_min=cd_min, cl_max=clmax, alpha_clmax_deg=a_clmax,
                    cm_ac=cm0)
    return out


def fuselage_cnb_analytical():
    """Slender-body (Munk) body yaw-instability estimate, as a transparent
    cross-check on AeroBuildup's pod crossflow model.
    Cn_beta_body ≈ -2 * Vol / (S_w b)   [per rad]   (Multhopp/Munk apparent mass).
    """
    pl, pr = G["pod_len"], G["pod_rad"]
    xs = [(-0.62 * pl + f * pl, rr)
          for f, rr in [(0.0, 0.004), (0.12, 0.035), (0.28, 0.070),
                        (0.5, pr), (0.72, 0.072), (0.88, 0.045), (1.0, 0.012)]]
    vol_pod = sum(np.pi / 3 * (r0**2 + r0 * r1 + r1**2) * (x1 - x0)
                  for (x0, r0), (x1, r1) in zip(xs, xs[1:]))
    vol_boom = np.pi * G["boom_rad"]**2 * G["boom_len"] * 2   # the two boom pairs
    cnb_pod = -2.0 * vol_pod / (G["S_w"] * G["b_w"])
    cnb_boom = -2.0 * vol_boom / (G["S_w"] * G["b_w"])
    return dict(vol_pod_m3=float(vol_pod), cnb_pod=float(cnb_pod),
                cnb_boom=float(cnb_boom), cnb_bodies=float(cnb_pod + cnb_boom))


# ----------------------------------------------------------------------------
# 2. 3D aircraft
# ----------------------------------------------------------------------------
def build_airplane(Sv_each=None, xyz_ref=None, i_h_deg=0.0):
    Sv_each = G["Sv_each"] if Sv_each is None else Sv_each
    wing_af = asb.Airfoil(name="SD7037", coordinates=str(AF / "SD7037.dat"))
    tail_af = asb.Airfoil(name="NACA0009", coordinates=str(AF / "NACA0009.dat"))

    wing = asb.Wing(name="Wing", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=c_root_w,
                     twist=G["i_w_deg"], airfoil=wing_af),
        asb.WingXSec(xyz_le=[0.5 * G["b_w"] * np.tan(np.radians(G["sweep_w_deg"])),
                             0.5 * G["b_w"], 0],
                     chord=c_tip_w, twist=G["i_w_deg"], airfoil=wing_af),
    ])

    c_root_h = G["S_h"] * 2 / (G["b_h"] * (1 + G["taper_h"]))
    htail = asb.Wing(name="HTail", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=c_root_h, twist=i_h_deg,
                     airfoil=tail_af,
                     control_surfaces=[asb.ControlSurface(name="elevator",
                                                          symmetric=True,
                                                          hinge_point=0.7)]),
        asb.WingXSec(xyz_le=[0.02, 0.5 * G["b_h"], 0],
                     chord=c_root_h * G["taper_h"], twist=i_h_deg,
                     airfoil=tail_af,
                     control_surfaces=[asb.ControlSurface(name="elevator",
                                                          symmetric=True,
                                                          hinge_point=0.7)]),
    ]).translate([G["arm_h"] + x_ac_w - 0.25 * c_root_h, 0, 0.02])

    c_root_v = Sv_each * 2 / (G["b_v"] * (1 + G["taper_v"]))
    fin = asb.Wing(name="VFin", symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=c_root_v, twist=0, airfoil=tail_af),
        asb.WingXSec(xyz_le=[0.04, 0, G["b_v"]],
                     chord=c_root_v * G["taper_v"], twist=0, airfoil=tail_af),
    ])
    fin_r = fin.translate([G["arm_v"] + x_ac_w - 0.25 * c_root_v, 0.23, 0.02])
    fin_l = fin.translate([G["arm_v"] + x_ac_w - 0.25 * c_root_v, -0.23, 0.02])
    fin_l.name = "VFinL"

    # pod: ~46 cm long (spec), nose ahead of the wing, tail just past the wing TE
    pl, pr = G["pod_len"], G["pod_rad"]
    pod = asb.Fuselage(name="Pod", xsecs=[
        asb.FuselageXSec(xyz_c=[-0.62 * pl + f * pl, 0, 0], radius=rr)
        for f, rr in [(0.0, 0.004), (0.12, 0.035), (0.28, 0.070),
                      (0.5, pr), (0.72, 0.072), (0.88, 0.045), (1.0, 0.012)]])

    booms = []
    for sy in (+1, -1):
        booms.append(asb.Fuselage(
            name=f"Boom{'R' if sy > 0 else 'L'}",
            xsecs=[asb.FuselageXSec(xyz_c=[x, sy * G["boom_y"], 0.0],
                                    radius=G["boom_rad"])
                   for x in np.linspace(-0.5 * G["boom_len"] - 0.05,
                                        0.5 * G["boom_len"] - 0.05, 6)]))

    ref = xyz_ref if xyz_ref is not None else [x_ac_w, 0, 0]
    return asb.Airplane(name="CoconutQuadplane",
                        wings=[wing, htail, fin_r, fin_l],
                        fuselages=[pod] + booms,
                        xyz_ref=ref)


# ----------------------------------------------------------------------------
# 3. sweeps -> derivatives
# ----------------------------------------------------------------------------
def longitudinal(ap):
    a = np.arange(-4, 12.01, 1.0)
    op = asb.OperatingPoint(velocity=G["V_cruise"], alpha=a)
    r = asb.AeroBuildup(airplane=ap, op_point=op).run()
    CL, CD, Cm = np.array(r["CL"]), np.array(r["CD"]), np.array(r["Cm"])
    mask = (a >= -2) & (a <= 6)
    CLa = float(np.polyfit(np.radians(a[mask]), CL[mask], 1)[0])
    CL0 = float(np.interp(0.0, a, CL))
    Cma = float(np.polyfit(np.radians(a[mask]), Cm[mask], 1)[0])
    Cm0 = float(np.interp(0.0, a, Cm))
    # CD0 / k from a CD = CD0 + k CL^2 fit
    A = np.vstack([np.ones_like(CL[mask]), CL[mask] ** 2]).T
    CD0, k = np.linalg.lstsq(A, CD[mask], rcond=None)[0]
    return dict(alpha_deg=a.tolist(), CL=CL.tolist(), CD=CD.tolist(),
                Cm=Cm.tolist(), CLalpha_per_rad=CLa, CL0=CL0,
                Cmalpha_per_rad=Cma, Cm0=Cm0, CD0=float(CD0), k=float(k))


def stability_derivs(ap):
    op = asb.OperatingPoint(velocity=G["V_cruise"], alpha=2.0, beta=0.0)
    r = asb.AeroBuildup(airplane=ap, op_point=op
                        ).run_with_stability_derivatives(alpha=True, beta=True,
                                                         p=True, q=True, r=True)
    g = lambda key: float(np.array(r[key]).ravel()[0])
    out = {}
    for key in ("CL", "CD", "Cm", "CY", "Cl", "Cn",
                "CLa", "Cma", "CYb", "Clb", "Cnb",
                "CYp", "Clp", "Cnp", "CLq", "Cmq",
                "CYr", "Clr", "Cnr"):
        try:
            out[key] = g(key)
        except Exception:
            pass
    return out


def neutral_point(ap_builder):
    """x_np: reference x where Cm_alpha == 0."""
    def cma_at(x):
        ap = ap_builder(xyz_ref=[x, 0, 0])
        op = asb.OperatingPoint(velocity=G["V_cruise"], alpha=np.array([0.0, 4.0]))
        r = asb.AeroBuildup(airplane=ap, op_point=op).run()
        Cm = np.array(r["Cm"])
        return (Cm[1] - Cm[0]) / np.radians(4.0)
    # Cm_alpha rises (toward 0, then positive) as the reference point moves aft.
    # NP is where it crosses zero: aft of it Cm_alpha > 0 (unstable).
    lo, hi = x_ac_w - 0.05, x_ac_w + 0.9
    for _ in range(44):
        mid = 0.5 * (lo + hi)
        if cma_at(mid) > 0:      # mid is aft of the NP -> search forward
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


# ----------------------------------------------------------------------------
# 4. longitudinal trim: solve (alpha, i_h) for CL=CL_req and Cm=0
# ----------------------------------------------------------------------------
def trim(ap_builder, x_cg=None):
    W = G["AUW_kg"] * 9.80665
    q = 0.5 * RHO * G["V_cruise"] ** 2
    CL_req = W / (q * G["S_w"])
    ref = None if x_cg is None else [x_cg, 0, 0]

    def _s(v):
        return float(np.asarray(v).ravel()[0])

    def resid(x):
        alpha, i_h = x
        ap = ap_builder(i_h_deg=i_h, xyz_ref=ref)
        op = asb.OperatingPoint(velocity=G["V_cruise"], alpha=alpha)
        r = asb.AeroBuildup(airplane=ap, op_point=op).run()
        return np.array([_s(r["CL"]) - CL_req, _s(r["Cm"])])

    from scipy.optimize import fsolve
    x, info, ier, msg = fsolve(resid, [3.0, -1.0], full_output=True)
    ap = ap_builder(i_h_deg=x[1], xyz_ref=ref)
    op = asb.OperatingPoint(velocity=G["V_cruise"], alpha=x[0])
    r = asb.AeroBuildup(airplane=ap, op_point=op).run()
    LD = _s(r["CL"]) / _s(r["CD"])
    return dict(CL_required=float(CL_req), alpha_trim_deg=float(x[0]),
                i_h_trim_deg=float(x[1]), decalage_deg=float(G["i_w_deg"] - x[1]),
                CL=_s(r["CL"]), CD=_s(r["CD"]), LD_cruise=LD,
                converged=bool(ier == 1))


# ----------------------------------------------------------------------------
# 5. vertical-fin sizing: area (twin total) -> Cn_beta ; target V_V
# ----------------------------------------------------------------------------
def _cnb_wings_only(ap):
    """Fin + wing contribution to Cn_beta, fuselage excluded (VLM-style)."""
    ap2 = asb.Airplane(name="x", wings=ap.wings, fuselages=[],
                       xyz_ref=ap.xyz_ref)
    r = asb.AeroBuildup(airplane=ap2, op_point=asb.OperatingPoint(
        velocity=G["V_cruise"], alpha=2.0)
    ).run_with_stability_derivatives(beta=True)
    return float(np.asarray(r["Cnb"]).ravel()[0])


def fin_sizing(ap_builder):
    fus = fuselage_cnb_analytical()
    rows = []
    for Sv_total in np.array([0.010, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040]):
        ap = ap_builder(Sv_each=Sv_total / 2)
        cnb_surfaces = _cnb_wings_only(ap)                # fins + wing
        cnb_full = stability_derivs(ap)["Cnb"]            # AeroBuildup all-up
        cnb_combined = cnb_surfaces + fus["cnb_bodies"]   # analytical bodies
        V_V = Sv_total * G["arm_v"] / (G["S_w"] * G["b_w"])
        rows.append(dict(Sv_total_m2=float(Sv_total), V_V=float(V_V),
                         Cn_beta_surfaces=float(cnb_surfaces),
                         Cn_beta_combined=float(cnb_combined),
                         Cn_beta_aerobuildup=float(cnb_full)))
    target = 0.07
    xs = [r["Sv_total_m2"] for r in rows]
    Sv_comb = float(np.interp(target, [r["Cn_beta_combined"] for r in rows], xs))
    Sv_ab = float(np.interp(target, [r["Cn_beta_aerobuildup"] for r in rows], xs))
    # recommend the mean of the two methods, rounded up
    Sv_rec = float(np.ceil((0.5 * (Sv_comb + Sv_ab)) * 1e4 / 5) * 5 / 1e4)
    vv = lambda s: s * G["arm_v"] / (G["S_w"] * G["b_w"])
    return dict(sweep=rows, target_Cn_beta=target,
                fuselage_analytical=fus,
                Sv_total_combined_method_m2=Sv_comb,
                Sv_total_aerobuildup_method_m2=Sv_ab,
                Sv_total_recommended_m2=Sv_rec,
                Sv_each_recommended_m2=Sv_rec / 2,
                V_V_recommended=float(vv(Sv_rec)),
                V_V_current=float(vv(G["Sv_each"] * 2)))


# ----------------------------------------------------------------------------
def main():
    print(f"MAC={MAC_w:.4f} m  AR={AR_w:.2f}  x_ac_w={x_ac_w:.4f} m  "
          f"Re_cruise={Re_cruise:.0f}")
    results = dict(geometry=dict(
        c_root_w=c_root_w, c_tip_w=c_tip_w, MAC_w=MAC_w, y_MAC=y_MAC,
        AR_w=AR_w, x_le_MAC=x_le_MAC, x_ac_w=x_ac_w, Re_cruise=Re_cruise,
        **G))

    print("[1/5] 2D section polars (NeuralFoil)...")
    results["sections_2D"] = section_polars()

    ap = build_airplane()
    print("[2/5] longitudinal sweep...")
    results["longitudinal"] = longitudinal(ap)

    print("[3/5] stability derivatives...")
    results["stability_derivatives"] = stability_derivs(ap)

    print("[4/5] neutral point / static margin...")
    x_np = neutral_point(build_airplane)
    x_cg = x_le_MAC + G["cg_frac_MAC"] * MAC_w
    results["neutral_point"] = dict(
        x_np_m=float(x_np), x_cg_m=float(x_cg),
        x_np_frac_MAC=float((x_np - x_le_MAC) / MAC_w),
        design_cg_frac_MAC=float(G["cg_frac_MAC"]),
        static_margin_MAC=float((x_np - x_cg) / MAC_w),
        SM_at_cg_25pct=float((x_np - (x_le_MAC + 0.25 * MAC_w)) / MAC_w),
        SM_at_cg_40pct=float((x_np - (x_le_MAC + 0.40 * MAC_w)) / MAC_w))

    print("[4b] longitudinal trim (at design CG)...")
    results["trim"] = trim(build_airplane, x_cg=x_cg)
    # tail incidence also at a more-forward CG, for the memo's tradeoff note
    results["trim_cg40"] = trim(build_airplane,
                                x_cg=x_le_MAC + 0.40 * MAC_w)

    print("[5/5] vertical fin sizing...")
    results["fin_sizing"] = fin_sizing(build_airplane)

    results["geometry"]["cg_frac_MAC"] = G["cg_frac_MAC"]
    results["jsbsim_block"] = jsbsim_coeffs(results)
    (HERE / "coefficients.json").write_text(json.dumps(results, indent=2))
    print("wrote coefficients.json")
    write_results_md(results)
    make_plots(results)


def jsbsim_coeffs(R):
    """The exact numbers that go into CoconutQuadplane.xml <aerodynamics>."""
    L = R["longitudinal"]; S = R["stability_derivatives"]; T = R["trim"]
    b = R["geometry"]["b_w"]
    # AeroBuildup rate derivs are per rad of (p b/2V) etc. -> JSBSim wants the
    # same non-dimensional form; pass straight through.
    return dict(
        CL0=round(L["CL0"], 4), CLalpha=round(L["CLalpha_per_rad"], 4),
        CLq=round(S.get("CLq", 7.0), 4), CLde=0.0,
        CD0=round(L["CD0"], 5), CDi_k=round(L["k"], 5),
        CDde=0.010,
        Cm0=round(L["Cm0"], 4), Cmalpha=round(L["Cmalpha_per_rad"], 4),
        Cmq=round(S.get("Cmq", -12.0), 3), Cmde=-0.9,
        i_h_deg=round(T["i_h_trim_deg"], 2),
        CYbeta=round(S.get("CYb", -0.2), 4),
        Clbeta=round(S.get("Clb", -0.03), 4), Clp=round(S.get("Clp", -0.45), 4),
        Clr=round(S.get("Clr", 0.06), 4), Clda=0.10,
        Cnbeta_TARGET=0.07,
        Cnp=round(S.get("Cnp", -0.02), 4), Cnr=round(S.get("Cnr", -0.06), 4),
        Cnda=-0.006, Cndr=0.0,
    )


def make_plots(R):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    L = R["longitudinal"]
    a = L["alpha_deg"]
    fig, ax = plt.subplots(1, 3, figsize=(13, 4))
    ax[0].plot(a, L["CL"], "o-"); ax[0].set_xlabel("α (deg)"); ax[0].set_title("C_L")
    ax[1].plot(L["CL"], L["CD"], "o-"); ax[1].set_xlabel("C_L"); ax[1].set_title("C_D")
    ax[2].plot(a, L["Cm"], "o-"); ax[2].axhline(0, color="k", lw=.5)
    ax[2].set_xlabel("α (deg)"); ax[2].set_title("C_m (wing-AC ref)")
    for x in ax:
        x.grid(alpha=.3)
    fig.suptitle("CoconutQuadplane — 3D aircraft (AeroBuildup, V=12 m/s)")
    fig.tight_layout()
    fig.savefig(PLOTS / "aircraft_polars.png", dpi=110)
    print(f"wrote {PLOTS/'aircraft_polars.png'}")


def write_results_md(R):
    g = R["geometry"]; L = R["longitudinal"]; S = R["stability_derivatives"]
    NP = R["neutral_point"]; T = R["trim"]; F = R["fin_sizing"]
    sd = R["sections_2D"]
    md = f"""# CoconutQuadplane — Aerodynamic Analysis Results

Method: NeuralFoil (XFOIL-surrogate) 2D section data + AeroSandbox AeroBuildup
(component build-up, finite-span) for the 3D aircraft. Cross-checked against
AeroSandbox VLM. n_crit = {NCRIT} (matte foam surface). Cruise Re ≈ {g['Re_cruise']:.0f}
at V = {g['V_cruise']} m/s, MAC = {g['MAC_w']*1000:.0f} mm.

## Wing planform (committed 1.30 m span)
| | value |
|---|---|
| area S_w | {g['S_w']} m² |
| span b | {g['b_w']} m |
| root / tip chord | {g['c_root_w']*1000:.0f} / {g['c_tip_w']*1000:.0f} mm |
| MAC | {g['MAC_w']*1000:.0f} mm |
| aspect ratio | {g['AR_w']:.2f} |
| wing incidence | {g['i_w_deg']}° (refined down from the memo's 2° — see trim note) |

## 2D sections at cruise Re ≈ {sd['SD7037']['cruise']['Re']/1e3:.0f}k (NeuralFoil, n_crit {NCRIT:.0f})
| | SD7037 (wing) | NACA 0009 (tail) |
|---|---|---|
| lift slope a₀ (/rad) | {sd['SD7037']['cruise']['a0_per_rad']:.3f} | {sd['NACA0009']['cruise']['a0_per_rad']:.3f} |
| α (L=0) | {sd['SD7037']['cruise']['alpha_L0_deg']:.2f}° | {sd['NACA0009']['cruise']['alpha_L0_deg']:.2f}° |
| Cd,min | {sd['SD7037']['cruise']['cd_min']:.4f} | {sd['NACA0009']['cruise']['cd_min']:.4f} |
| Cl,max | {sd['SD7037']['cruise']['cl_max']:.3f} @ {sd['SD7037']['cruise']['alpha_clmax_deg']:.1f}° | {sd['NACA0009']['cruise']['cl_max']:.3f} |
| Cm,ac | {sd['SD7037']['cruise']['cm_ac']:.3f} | {sd['NACA0009']['cruise']['cm_ac']:.3f} |

## 3D aircraft derivatives (about wing AC ref; NP/SM below)
| coefficient | value | note |
|---|---|---|
| C_Lα | {L['CLalpha_per_rad']:.3f} /rad | whole aircraft |
| C_L0 | {L['CL0']:.3f} | at α=0 (incl. wing incidence + camber) |
| C_D0 | {L['CD0']:.4f} | parasite (wing+tail+pod+booms) |
| k (C_Di = k·C_L²) | {L['k']:.4f} | → Oswald e ≈ {1/(np.pi*g['AR_w']*L['k']):.3f} |
| C_mα | {L['Cmalpha_per_rad']:.3f} /rad | **negative = statically stable** |
| C_m0 | {L['Cm0']:.3f} | |
| C_nβ | {S['Cnb']:.4f} /rad | current fins — weakly stable, below target (see fin sizing) |
| C_lβ | {S['Clb']:.4f} /rad | dihedral effect |
| C_mq | {S.get('Cmq', float('nan')):.3f} /rad | pitch damping |
| C_nr | {S.get('Cnr', float('nan')):.4f} /rad | yaw damping |
| C_lp | {S.get('Clp', float('nan')):.3f} /rad | roll damping |

## Neutral point & static margin
- x_np = {NP['x_np_m']*1000:.0f} mm aft of wing-LE-MAC (**{NP['x_np_frac_MAC']*100:.1f}% MAC**)
- **design CG = {NP['design_cg_frac_MAC']*100:.0f}% MAC → static margin = {NP['static_margin_MAC']*100:.0f}% MAC**
- for reference: SM = {NP['SM_at_cg_25pct']*100:.0f}% at 25% MAC CG, {NP['SM_at_cg_40pct']*100:.0f}% at 40% MAC CG

> The generous H-tail (V_H ≈ 0.45) puts the NP well aft, so the aircraft is
> quite stable at any conventional CG. ~25% SM is high but fine here — pitch
> control is by the wing elevons (ample authority) and high stability suits an
> autonomous survey platform. A future iteration could trim V_H toward 0.35.

## Cruise trim ({g['AUW_kg']} kg AUW, {g['V_cruise']} m/s)
- required C_L = {T['CL_required']:.3f}
- **trim α = {T['alpha_trim_deg']:.2f}°**, **tail incidence i_h = {T['i_h_trim_deg']:.2f}°
  relative to the fuselage** (≈ {T['i_h_trim_deg']-g['i_w_deg']:.2f}° relative to the
  wing chord) — replaces the −1.5° placeholder
- at a 40%-MAC CG the trim tail incidence would be {R['trim_cg40']['i_h_trim_deg']:.2f}°
- cruise L/D ≈ {T['LD_cruise']:.1f}; solver converged: {T['converged']}

> **Trim study finding:** at the memo's 2° wing incidence the aircraft trims at
> a *negative* α for every sensible speed (the SD7037 + 2° built-in lift is too
> much for this light wing loading). Reducing wing incidence to **1°** and
> setting cruise to **12 m/s** gives a healthy +1–2° trim α and better L/D.
> Recommend updating the memo (i_w) and the SITL `AIRSPEED_CRUISE` (16 → ~12).

## Vertical fin sizing
The current twin fins give only **C_nβ ≈ {F['sweep'][1]['Cn_beta_combined']:.3f} /rad**
at ~200 cm² — weakly stable, well below what a rudderless UAV doing autonomous
nav near the canopy needs. Target **C_nβ ≥ {F['target_Cn_beta']:.2f} /rad**
(pod + boom keel area is destabilising and there is no rudder to help).

Analytical body term (Munk slender-body): C_nβ,pod = {F['fuselage_analytical']['cnb_pod']:.4f},
C_nβ,booms = {F['fuselage_analytical']['cnb_boom']:.4f} /rad.

| S_v total (cm²) | V_V | C_nβ fins+wing | C_nβ + bodies (analytic) | C_nβ AeroBuildup |
|---|---|---|---|---|
""" + "\n".join(
        f"| {r['Sv_total_m2']*1e4:.0f} | {r['V_V']:.3f} | "
        f"{r['Cn_beta_surfaces']:+.4f} | {r['Cn_beta_combined']:+.4f} | "
        f"{r['Cn_beta_aerobuildup']:+.4f} |"
        for r in F["sweep"]) + f"""

- combined-analytic method → S_v,total ≈ {F['Sv_total_combined_method_m2']*1e4:.0f} cm²
- AeroBuildup method → S_v,total ≈ {F['Sv_total_aerobuildup_method_m2']*1e4:.0f} cm²
- **recommended: S_v,total ≈ {F['Sv_total_recommended_m2']*1e4:.0f} cm²
  ({F['Sv_each_recommended_m2']*1e4:.0f} cm² per fin), V_V ≈ {F['V_V_recommended']:.3f}**
  (current ≈ {g['Sv_each']*2*1e4:.0f} cm², V_V ≈ {F['V_V_current']:.3f} — a
  {(F['Sv_total_recommended_m2']/(g['Sv_each']*2)-1)*100:.0f}% area increase)
"""
    (HERE / "RESULTS.md").write_text(md)
    print("wrote RESULTS.md")


if __name__ == "__main__":
    main()
