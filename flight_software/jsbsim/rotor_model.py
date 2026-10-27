#!/usr/bin/env python3
"""
rotor_model.py -- physical motor + propeller model for the JSBSim bridge.

Each rotor is an A2212 1400KV outrunner on an APC Slow-Flyer-class 10 in prop
(the airframe's 1045), on a shared 3S pack:

  ESC     : motor terminal voltage = throttle * bus voltage
  motor   : I = (V - w/Kv) / Rm ;  Q_motor = Kt * (I - I0)
  prop    : T = CT(J) rho n^2 D^4 ;  Q_prop = CP(J)/(2 pi) rho n^2 D^5
  rotor   : dw/dt = (Q_motor - Q_prop) / J_rotor   -> spool lag emerges
  battery : V_bus = V_oc - R_pack * sum(I)

CT/CP vs advance ratio J = V_axial / (n D) are MEASURED (UIUC Propeller
Database vol. 1, APC SF 10x4.7: propdata/). Motor constants are typical
A2212/10T 1400KV listing values (no bench data exists for this exact combo);
`python rotor_model.py` prints the static check against the seller figure
(~850-950 g per motor at full throttle).
Not modelled: rotor H-force drag in edgewise flow, vortex-ring state.
"""
from __future__ import annotations

import math

RHO = 1.13                      # kg/m^3, 35 C at ~300 m (same as Gazebo/analysis)
D = 0.254                       # m (10 in)
KV = 1400.0                     # rpm/V
KV_RAD = KV * 2 * math.pi / 60  # rad/s per V
KT = 1.0 / KV_RAD               # N*m/A
RM = 0.07                       # ohm, winding
I0 = 0.8                        # A, no-load current
I_MAX = 30.0                    # A, ESC/motor limit
V_OC = 11.4                     # V, 3S at ~50 % charge (3.8 V/cell)
R_PACK = 0.045                  # ohm, 3 x ~15 mOhm cells
# rotor inertia: 1045 prop ~12 g as a slender rod (m D^2 / 12) + motor bell
J_ROTOR = 0.012 * D ** 2 / 12 + 1.0e-5   # kg m^2

# APC SF 10x4.7 (UIUC): J, CT, CP. J=0 from the static test at its top RPM,
# J>0 from the 6512 rpm wind-tunnel run; extrapolated linearly to CT = 0.
_TAB = [(0.000, 0.1299, 0.0531), (0.089, 0.1201, 0.0523), (0.134, 0.1129, 0.0512),
        (0.176, 0.1059, 0.0500), (0.225, 0.0974, 0.0483), (0.266, 0.0895, 0.0465),
        (0.308, 0.0833, 0.0454), (0.357, 0.0743, 0.0434), (0.395, 0.0669, 0.0414),
        (0.420, 0.0616, 0.0398), (0.445, 0.0562, 0.0381)]
_SLOPE_CT = (0.0562 - 0.0669) / (0.445 - 0.395)
_SLOPE_CP = (0.0381 - 0.0414) / (0.445 - 0.395)


def coeffs(j):
    """CT, CP at advance ratio j (j < 0 -> static values)."""
    if j <= 0.0:
        return _TAB[0][1], _TAB[0][2]
    for (j0, t0, p0), (j1, t1, p1) in zip(_TAB, _TAB[1:]):
        if j <= j1:
            f = (j - j0) / (j1 - j0)
            return t0 + f * (t1 - t0), p0 + f * (p1 - p0)
    jl, tl, pl = _TAB[-1]
    return tl + _SLOPE_CT * (j - jl), max(0.0, pl + _SLOPE_CP * (j - jl))


class Rotor:
    def __init__(self):
        self.w = 0.0            # rad/s
        self.current = 0.0
        self.thrust = 0.0
        self.torque = 0.0       # motor reaction torque on the airframe, N m

    def step(self, throttle, v_axial, v_bus, dt):
        n = self.w / (2 * math.pi)
        j = v_axial / (n * D) if n > 1.0 else 0.0
        ct, cp = coeffs(j)
        # windmilling (CT < 0) at very high J: allow drag, not reverse spin
        self.thrust = ct * RHO * n * n * D ** 4
        q_prop = cp / (2 * math.pi) * RHO * n * n * D ** 5
        i = (throttle * v_bus - self.w / KV_RAD) / RM
        i = max(-I_MAX, min(I_MAX, i))
        if throttle <= 0.0 and i < 0.0:
            i = 0.0             # ESC off: freewheel (no regen braking)
        q_motor = KT * (i - (I0 if self.w > 1.0 else 0.0))
        self.current = max(0.0, i)
        self.w = max(0.0, self.w + (q_motor - q_prop) / J_ROTOR * dt)
        self.torque = q_motor
        return self.thrust


class Pack:
    """Shared 3S pack: bus voltage sags with the total current."""

    def __init__(self):
        self.v_bus = V_OC
        self.used_mah = 0.0

    def solve(self, rotors, throttles):
        """Bus voltage consistent with this step's motor currents. Solved, not
        lagged: with 4 motors the one-step-lagged loop (gain R_pack*sum(thr)/Rm
        > 1) oscillated between 11.4 V and 6 V.
          V = V_oc - R_pack * sum((thr_k V - e_k) / Rm),  e_k = w_k / Kv"""
        a = sum(t for t in throttles if t > 0)
        e = sum(r.w / KV_RAD for r, t in zip(rotors, throttles) if t > 0)
        self.v_bus = max(0.0, (V_OC + R_PACK * e / RM) / (1 + R_PACK * a / RM))
        return self.v_bus

    def update(self, rotors, dt):
        total = sum(r.current for r in rotors)
        self.used_mah += total * dt / 3.6
        return total


def _settle(throttle, v_axial=0.0, t_end=2.0, dt=1e-4):
    r, p = Rotor(), Pack()
    t = 0.0
    while t < t_end:
        r.step(throttle, v_axial, p.solve([r], [throttle]), dt)
        p.update([r], dt)
        t += dt
    return r, p


def _spool_time(t_from, t_to, dt=1e-4):
    """63 % thrust-step time from throttle t_from to t_to."""
    r0, _ = _settle(t_from)
    r1, _ = _settle(t_to)
    r, p = Rotor(), Pack()
    r.w = r0.w
    target = r0.thrust + 0.632 * (r1.thrust - r0.thrust)
    t = 0.0
    while t < 1.0:
        r.step(t_to, 0.0, p.solve([r], [t_to]), dt)
        p.update([r], dt)
        t += dt
        if (r1.thrust - r0.thrust) * (r.thrust - target) >= 0:
            return t
    return float("nan")


if __name__ == "__main__":
    print("static, single motor on the pack:")
    for thr in (0.3, 0.5, 0.65, 0.8, 1.0):
        r, p = _settle(thr)
        print(f"  thr {thr:4.2f}: {r.w * 60 / (2 * math.pi):6.0f} rpm  T {r.thrust:5.2f} N "
              f"({r.thrust / 9.81 * 1000:4.0f} g)  I {r.current:5.1f} A  "
              f"P {r.current * p.v_bus:5.0f} W  Vbus {p.v_bus:5.2f}")
    r, _ = _settle(1.0, v_axial=15.0)
    print(f"pusher at 15 m/s, full throttle: T {r.thrust:4.2f} N, I {r.current:4.1f} A, "
          f"J {15 / (r.w / 2 / math.pi * D):.2f}")
    print(f"spool 0.4 -> 0.6: tau {_spool_time(0.4, 0.6) * 1000:4.0f} ms ; "
          f"0.6 -> 0.4: {_spool_time(0.6, 0.4) * 1000:4.0f} ms ; "
          f"0 -> 0.6 (start): {_spool_time(0.0, 0.6) * 1000:4.0f} ms")
