#!/usr/bin/env python3
"""
verify_model.py — sanity-check the CoconutQuadplane JSBSim model's AERODYNAMICS.

The model loads and the DJI 9450 prop data is real, but the DJI E305 brushless
motor model does not throttle down to this airframe's ~1 N cruise thrust
(propulsion sizing is a separate task). So the aero model is exercised
**power-off**: a stabilised glide plus pitch and yaw disturbances. That tests
exactly the coefficients that were just replaced with real airfoil-derived data.

Writes captures/jsbsim_cruise.png + captures/jsbsim_results.json.

    python verify_model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import jsbsim

HERE = Path(__file__).resolve().parent
CAP = HERE / "captures"
CAP.mkdir(exist_ok=True)

H_SL_FT = 3000.0
DT = 1.0 / 120.0
MS2FT = 3.280839895
AUW_KG = 1.40
W_LBS = AUW_KG * 2.2046226
RHO = 1.225
S_W = 0.30


def make_fdm():
    fdm = jsbsim.FGFDMExec(str(HERE), None)
    fdm.set_debug_level(0)
    assert fdm.load_model("CoconutQuadplane"), "load_model failed"
    fdm.set_dt(DT)
    return fdm


def glide(elevator_cmd, v0_ms=13.0, seconds=14.0, beta0=0.0, elev_pulse=None):
    fdm = make_fdm()
    fdm["ic/h-sl-ft"] = H_SL_FT
    fdm["ic/vt-fps"] = v0_ms * MS2FT
    fdm["ic/alpha-deg"] = 2.0
    fdm["ic/gamma-deg"] = -4.0
    fdm["ic/beta-deg"] = beta0
    fdm["propulsion/engine[0]/set-running"] = 0
    fdm["fcs/throttle-cmd-norm"] = 0.0
    fdm.run_ic()
    rows = []
    n = int(seconds / DT)
    for i in range(n):
        e = elevator_cmd
        if elev_pulse and elev_pulse[0] <= i * DT < elev_pulse[1]:
            e += elev_pulse[2]
        fdm["fcs/elevator-cmd-norm"] = e
        fdm.run()
        L = abs(fdm["forces/fwz-aero-lbs"])
        D = abs(fdm["forces/fwx-aero-lbs"])
        rows.append(dict(
            t=round(i * DT, 3), alt=fdm["position/h-sl-ft"],
            alpha=fdm["aero/alpha-deg"], beta=fdm["aero/beta-deg"],
            theta=fdm["attitude/theta-deg"], phi=fdm["attitude/phi-deg"],
            gamma=fdm["flight-path/gamma-deg"], vt=fdm["velocities/vt-fps"] / MS2FT,
            q=fdm["velocities/q-rad_sec"] * 57.2958,
            r=fdm["velocities/r-rad_sec"] * 57.2958,
            LD=L / max(D, 1e-6),
            lift=L,
        ))
    return rows


def steady(rows, key, frac=0.4):
    v = np.array([r[key] for r in rows])
    return float(np.mean(v[int(len(v) * (1 - frac)):]))


def find_glide_trim():
    """Elevator that gives the flattest steady glide."""
    best = None
    for e in np.arange(-0.14, 0.02, 0.02):
        rws = glide(float(e), seconds=16.0)
        g = steady(rws, "gamma")
        qq = abs(steady(rws, "q"))
        if best is None or (abs(g) + qq) < best[0]:
            best = (abs(g) + qq, float(e), rws)
    _, e, rws = best
    return dict(
        elevator_cmd=e,
        elevator_pos_deg=57.2958 * np.mean([0]) if False else
        float(np.degrees(0.30 * e)),  # aerosurface_scale range ±0.30
        alpha_deg=steady(rws, "alpha"),
        gamma_deg=steady(rws, "gamma"),
        vt_ms=steady(rws, "vt"),
        LD=steady(rws, "LD"),
        lift_over_weight=steady(rws, "lift") / W_LBS,
    )


def analyse(trim, pitch_rows, yaw_rows):
    tp = np.array([r["t"] for r in pitch_rows])
    ap = np.array([r["alpha"] for r in pitch_rows])
    vp = np.array([r["vt"] for r in pitch_rows])
    altp = np.array([r["alt"] for r in pitch_rows])
    # pitch disturbance recovery: peak deviation after the pulse vs residual
    after = tp > 3.5
    a_ss = np.mean(ap[tp < 2.5])
    dev = ap[after] - a_ss
    peak = np.max(np.abs(dev))
    resid = np.mean(np.abs(dev[-int(len(dev) * 0.25):]))
    pitch_recovers = resid < 0.4 * peak + 0.3

    tb = np.array([r["t"] for r in yaw_rows])
    bb = np.array([r["beta"] for r in yaw_rows])
    b0 = abs(np.mean(bb[tb < 0.3]))
    b_end = np.max(np.abs(bb[tb > tb[-1] - 3.0]))
    yaw_washes = b_end < 0.25 * b0

    checks = {
        "loads_runs_no_NaN": bool(np.all(np.isfinite(altp)) and
                                  np.all(np.isfinite(ap))),
        # best-L/D glide runs a touch faster than the 12 m/s powered cruise,
        # so CL (hence alpha) is lower; slightly negative alpha is correct for
        # this cambered section at the glide CL.
        "glide_alpha_sane_-2_to_6deg": -2.0 <= trim["alpha_deg"] <= 6.0,
        "glide_LD_9_to_15": 9.0 <= trim["LD"] <= 15.0,
        "glide_speed_10_to_18": 10.0 <= trim["vt_ms"] <= 18.0,
        "lift_equals_weight_0.9_1.1": 0.9 <= trim["lift_over_weight"] <= 1.1,
        "pitch_disturbance_recovers": bool(pitch_recovers),
        "phugoid_speed_bounded_<4ms": float(np.ptp(vp[tp > 2])) < 4.0,
        "yaw_10deg_sideslip_washes_out": bool(yaw_washes),
    }
    return dict(trim=trim, checks=checks, passed=all(checks.values()),
               metrics=dict(
                   pitch_peak_dev_deg=float(peak),
                   pitch_residual_deg=float(resid),
                   yaw_beta0_deg=float(b0), yaw_beta_end_deg=float(b_end)))


def plot(pitch_rows, yaw_rows, out):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    tp = [r["t"] for r in pitch_rows]
    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    ax[0, 0].plot(tp, [r["alpha"] for r in pitch_rows], label="α")
    ax[0, 0].plot(tp, [r["theta"] for r in pitch_rows], label="θ")
    ax[0, 0].axvspan(5.0, 5.4, color="orange", alpha=.3)
    ax[0, 0].legend(); ax[0, 0].set_title("power-off glide — pitch pulse @ 5 s")
    ax[0, 1].plot(tp, [r["vt"] for r in pitch_rows])
    ax[0, 1].set_title("airspeed (m/s)")
    ax[1, 0].plot(tp, [r["LD"] for r in pitch_rows])
    ax[1, 0].set_title("instantaneous L/D")
    tb = [r["t"] for r in yaw_rows]
    ax[1, 1].plot(tb, [r["beta"] for r in yaw_rows], label="β")
    ax[1, 1].plot(tb, [r["r"] for r in yaw_rows], label="r deg/s")
    ax[1, 1].plot(tb, [r["phi"] for r in yaw_rows], label="φ")
    ax[1, 1].legend(); ax[1, 1].set_title("10° sideslip release")
    for x in ax.ravel():
        x.grid(alpha=.3); x.set_xlabel("t (s)")
    fig.suptitle("CoconutQuadplane JSBSim — aero model check (power-off)")
    fig.tight_layout(); fig.savefig(out, dpi=110)
    print(f"wrote {out}")


def main():
    make_fdm()  # smoke: constructs + loads
    print("model loads OK")

    trim = find_glide_trim()
    print(f"glide trim: α={trim['alpha_deg']:.2f}°  γ={trim['gamma_deg']:.2f}°  "
          f"V={trim['vt_ms']:.2f} m/s  L/D={trim['LD']:.2f}  "
          f"L/W={trim['lift_over_weight']:.3f}  elev_cmd={trim['elevator_cmd']:.3f}")

    pitch_rows = glide(trim["elevator_cmd"], seconds=40.0,
                       elev_pulse=(5.0, 5.4, 0.10))
    yaw_rows = glide(trim["elevator_cmd"], v0_ms=trim["vt_ms"],
                     seconds=14.0, beta0=10.0)

    res = analyse(trim, pitch_rows, yaw_rows)
    plot(pitch_rows, yaw_rows, CAP / "jsbsim_cruise.png")
    (CAP / "jsbsim_results.json").write_text(json.dumps(res, indent=2))

    print("\n=== CHECKS ===")
    for k, v in res["checks"].items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print("\nmetrics:", json.dumps(res["metrics"], indent=2))
    print(f"\nOVERALL: {'PASS' if res['passed'] else 'FAIL'}")


if __name__ == "__main__":
    main()
