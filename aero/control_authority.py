#!/usr/bin/env python3
"""
control_authority.py — do the two wing elevons alone give this airframe enough
PITCH and ROLL authority?  The horizontal tail is FIXED (passive stability
only), so every trim change and every manoeuvre comes from the elevons, and
pitch + roll share the same surface.

Model: AeroSandbox AeroBuildup (VLM ignores control-surface deflection; the
build-up model applies it through NeuralFoil's flapped-section data). Wing has
a full-span trailing-edge elevon (28% chord). "elevator" = both elevons the
same way; "aileron" = opposite.

Design point: V = 12 m/s, CG 33% MAC, tail incidence -1.8 deg (from
aero/RESULTS.md). Elevon mechanical travel +/- 22 deg (MG90S on foam).

Outputs: aero/control_authority.json + a plain verdict.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
import aerosandbox as asb

HERE = Path(__file__).resolve().parent
AF = HERE / "airfoils"

V = 12.0
RHO = 1.225
S_W, B_W, MAC = 0.30, 1.30, 0.2356
AUW = 1.40
W = AUW * 9.80665
Q = 0.5 * RHO * V ** 2
CL_CRUISE = W / (Q * S_W)
ELEVON_MAX = 22.0
IXX, IYY = 0.045, 0.030

c_root = S_W * 2 / (B_W * (1 + 0.6))
c_tip = c_root * 0.6
x_le_mac = (B_W / 6) * (1 + 2 * 0.6) / (1 + 0.6) * np.tan(np.radians(2))

_WAF = asb.Airfoil("SD7037", coordinates=str(AF / "SD7037.dat"))
_TAF = asb.Airfoil("NACA0009", coordinates=str(AF / "NACA0009.dat"))


def s(x):
    return float(np.asarray(x).ravel()[0])


def plane(elevon=0.0, aileron=0.0, i_h=-1.8, cg_frac=0.33):
    """elevon = symmetric deflection (deg); aileron = antisymmetric (deg)."""
    e_sym = [asb.ControlSurface(name="e", symmetric=True, deflection=elevon,
                                hinge_point=0.72)]
    a_anti = [asb.ControlSurface(name="a", symmetric=False, deflection=aileron,
                                 hinge_point=0.72)]
    wing = asb.Wing(name="Wing", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=c_root, twist=1.0, airfoil=_WAF,
                     control_surfaces=e_sym + a_anti),
        asb.WingXSec(xyz_le=[0.5 * B_W * np.tan(np.radians(2)), B_W / 2, 0],
                     chord=c_tip, twist=1.0, airfoil=_WAF,
                     control_surfaces=e_sym + a_anti),
    ])
    htail = asb.Wing(name="HTail", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[0, 0, 0], chord=0.148, twist=i_h, airfoil=_TAF),
        asb.WingXSec(xyz_le=[0.02, 0.25, 0], chord=0.104, twist=i_h, airfoil=_TAF),
    ]).translate([0.55, 0, 0.02])
    return asb.Airplane(name="CQ", wings=[wing, htail],
                        xyz_ref=[x_le_mac + cg_frac * MAC, 0, 0])


def run(ap, alpha, p=0.0):
    op = asb.OperatingPoint(velocity=V, alpha=alpha, beta=0.0)
    if p:
        op.p = p
    return asb.AeroBuildup(airplane=ap, op_point=op).run()


# ---------------------------------------------------------------------------
def _cm_de_sign():
    """Return +1 if positive `elevon` arg is nose-up, else -1."""
    lo = s(run(plane(elevon=-10), 3.0)["Cm"])
    hi = s(run(plane(elevon=+10), 3.0)["Cm"])
    return 1.0 if hi > lo else -1.0


def pitch_authority():
    out = {}
    de = np.array([-15, -7.5, 0, 7.5, 15.0])
    cm = [s(run(plane(elevon=d), 3.0)["Cm"]) for d in de]
    cl = [s(run(plane(elevon=d), 3.0)["CL"]) for d in de]
    Cm_de = float(np.polyfit(np.radians(de), cm, 1)[0])
    CL_de = float(np.polyfit(np.radians(de), cl, 1)[0])
    out["Cm_delta_e_per_rad"] = Cm_de
    out["CL_delta_e_per_rad"] = CL_de
    nose_up = "positive elevon arg" if _cm_de_sign() > 0 else "negative elevon arg"
    out["nose_up_direction"] = nose_up

    # Cm_alpha about each CG (needed for the manoeuvre estimate)
    def cm_alpha(cg):
        c1 = s(run(plane(cg_frac=cg), 1.0)["Cm"])
        c2 = s(run(plane(cg_frac=cg), 5.0)["Cm"])
        return (c2 - c1) / np.radians(4)

    # trim elevon at each CG: elevon for Cm=0 with alpha holding cruise CL
    trims = {}
    for cg in (0.25, 0.33, 0.40):
        def cm_at_elevon(d):
            a = brentq(lambda al: s(run(plane(elevon=d, cg_frac=cg), al)["CL"])
                       - CL_CRUISE, -8, 12)
            return s(run(plane(elevon=d, cg_frac=cg), a)["Cm"]), a
        try:
            d_tr = brentq(lambda d: cm_at_elevon(d)[0], -8.0, 8.0)
            _, a_tr = cm_at_elevon(d_tr)
        except ValueError:
            d_tr, a_tr = float("nan"), float("nan")
        trims[f"cg_{int(cg*100)}"] = dict(
            elevon_deg=float(d_tr), alpha_deg=float(a_tr),
            travel_used_pct=float(abs(d_tr) / ELEVON_MAX * 100),
            Cm_alpha_per_rad=float(cm_alpha(cg)))
    out["trim"] = trims

    worst = max((abs(t["elevon_deg"]) for t in trims.values()
                 if np.isfinite(t["elevon_deg"])), default=ELEVON_MAX)
    spare_deg = ELEVON_MAX - worst
    out["elevon_spare_for_maneuver_deg"] = float(spare_deg)

    # manoeuvre pull-up with the spare elevon, at CG 33% MAC:
    #   d(alpha) = -(Cm_de / Cm_alpha) * d(elevon);  dCL = CL_alpha*dα + CL_de*dδ
    Cma = cm_alpha(0.33)
    r_a = s(run(plane(cg_frac=0.33), 1.0)["CL"])
    r_b = s(run(plane(cg_frac=0.33), 5.0)["CL"])
    CL_alpha = (r_b - r_a) / np.radians(4)
    dd = np.radians(spare_deg)
    d_alpha = -(Cm_de / Cma) * dd
    dCL = CL_alpha * d_alpha + CL_de * dd
    CL_reachable = CL_CRUISE + dCL
    # a real UAV can't exceed its wing CLmax
    CLmax_3d = 1.33     # aero/RESULTS.md 3D CL table peak
    n_elevon_limited = CL_reachable / CL_CRUISE
    n_stall_limited = CLmax_3d / CL_CRUISE
    out["pullup_load_factor_g"] = float(min(n_elevon_limited, n_stall_limited))
    out["pullup_is_stall_limited"] = bool(n_stall_limited < n_elevon_limited)
    out["pullup_load_factor_if_no_stall_g"] = float(n_elevon_limited)

    M = Q * S_W * MAC * abs(Cm_de) * dd
    out["pitch_accel_rad_s2"] = float(M / IYY)
    return out


def roll_authority():
    out = {}
    da = np.array([-15, -7.5, 7.5, 15.0])
    cl_roll = [s(run(plane(aileron=d), 3.0)["Cl"]) for d in da]
    Cl_da = float(np.polyfit(np.radians(da), cl_roll, 1)[0])
    out["Cl_delta_a_per_rad"] = Cl_da

    r0 = s(run(plane(), 3.0, p=0.0)["Cl"])
    pnd = 0.1                                  # p*b/2V
    r1 = s(run(plane(), 3.0, p=pnd * 2 * V / B_W)["Cl"])
    Cl_p = float((r1 - r0) / pnd)
    out["Cl_p_per_rad"] = Cl_p

    for name, frac in (("full_elevon", 1.0), ("half_saved_for_pitch", 0.5)):
        d = np.radians(ELEVON_MAX * frac)
        p_ss = abs(-(Cl_da * d) / Cl_p * (2 * V / B_W))      # rad/s
        tau = abs(IXX / (Q * S_W * B_W * (B_W / (2 * V)) * Cl_p))
        # bank angle from a step aileron: phi(t)=p_ss*(t - tau(1-e^-t/tau))
        import math
        tt = np.linspace(0, 3, 600)
        phi = np.degrees(p_ss * (tt - tau * (1 - np.exp(-tt / tau))))
        t45 = float(np.interp(45, phi, tt)) if phi[-1] > 45 else float("nan")
        out[name] = dict(roll_rate_deg_s=float(np.degrees(p_ss)),
                         roll_time_const_s=float(tau),
                         time_to_45deg_bank_s=t45)
    return out


def main():
    print(f"design point V={V} m/s  CL_cruise={CL_CRUISE:.3f}  "
          f"elevon +/-{ELEVON_MAX} deg  (28% chord, full span)")
    P = pitch_authority()
    R = roll_authority()

    tmax = max((t["travel_used_pct"] for t in P["trim"].values()
                if np.isfinite(t["travel_used_pct"])), default=100.0)
    verdict = {
        "pitch_trim_under_40pct_travel": tmax < 40.0,
        "pitch_pullup_ge_2g": P["pullup_load_factor_g"] >= 2.0,
        "pitch_accel_ge_2_rad_s2": P["pitch_accel_rad_s2"] >= 2.0,
        "roll_rate_full_ge_60deg_s": R["full_elevon"]["roll_rate_deg_s"] >= 60.0,
        "roll_rate_pitch_shared_ge_30deg_s":
            R["half_saved_for_pitch"]["roll_rate_deg_s"] >= 30.0,
    }
    res = dict(design_point=dict(V=V, CL_cruise=CL_CRUISE, elevon_max_deg=ELEVON_MAX),
               pitch=P, roll=R, verdict=verdict, passed=all(verdict.values()))
    (HERE / "control_authority.json").write_text(json.dumps(res, indent=2))

    print("\n--- PITCH ---")
    print(f"Cm_de = {P['Cm_delta_e_per_rad']:+.3f} /rad   "
          f"CL_de = {P['CL_delta_e_per_rad']:+.3f} /rad   "
          f"(nose-up = {P['nose_up_direction']})")
    for k, t in P["trim"].items():
        print(f"  trim {k}% MAC: elevon {t['elevon_deg']:+.1f} deg  "
              f"alpha {t['alpha_deg']:+.1f} deg  "
              f"({t['travel_used_pct']:.0f}% of travel)")
    print(f"  spare elevon for manoeuvre : {P['elevon_spare_for_maneuver_deg']:.0f} deg")
    lim = "wing-stall limited" if P["pullup_is_stall_limited"] else "elevon limited"
    print(f"  pull-up load factor        : {P['pullup_load_factor_g']:.2f} g  ({lim}; "
          f"elevon alone could reach {P['pullup_load_factor_if_no_stall_g']:.1f} g)")
    print(f"  nose-up pitch accel        : {P['pitch_accel_rad_s2']:.1f} rad/s^2")

    print("\n--- ROLL ---")
    print(f"Cl_da = {R['Cl_delta_a_per_rad']:+.4f} /rad   Cl_p = {R['Cl_p_per_rad']:+.3f} /rad")
    for k in ("full_elevon", "half_saved_for_pitch"):
        d = R[k]
        print(f"  {k:22s}: {d['roll_rate_deg_s']:4.0f} deg/s steady, "
              f"45 deg bank in {d['time_to_45deg_bank_s']:.2f} s")

    print("\n--- VERDICT ---")
    for k, v in verdict.items():
        print(f"  [{'OK' if v else 'MARGINAL'}] {k}")
    print(f"\nOVERALL: {'ADEQUATE' if res['passed'] else 'SEE NOTES — not a clean pass'}")


if __name__ == "__main__":
    main()
