#!/usr/bin/env python3
"""
test_physics.py -- open-loop checks of the JSBSim model + rotor model, no
ArduPilot. Run before flying the bridge:  python test_physics.py

  1. rest   : 0 throttle for 5 s on the pad -> stays upright, settles
  2. hover  : equal lift throttle sweep -> throttle where climb accel ~ 0
  3. yaw    : CCW pair up / CW pair down -> positive yaw rate (nose right)
  4. glide  : released at 15 m/s, 60 m, controls neutral -> stable glide
"""
import math
import sys

from jsbsim_bridge import Bridge

ROOT = "."
ok = True


def check(name, cond, detail):
    global ok
    ok &= bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}: {detail}")


def pwm(lift=0.0, fwd=0.0, elev=1500, lift4=None):
    p = [1500, 1500, int(1000 + 1000 * fwd), 1500, 0, 0, 0, 0] + [1500] * 8
    for i, t in enumerate(lift4 or [lift] * 4):
        p[4 + i] = int(1000 + 1000 * t)
    p[0] = p[1] = elev
    return p


def run(b, cmd, secs):
    for _ in range(int(secs / b.dt)):
        b.step(cmd)


def att(b):
    f = b.f
    return (math.degrees(f["attitude/phi-rad"]), math.degrees(f["attitude/theta-rad"]),
            f["position/h-agl-ft"] * 0.3048)


# 1 rest
b = Bridge(ROOT, "CoconutQuadplane", 400.0)
run(b, pwm(), 5.0)
r, p, h = att(b)
check("rest on pad", abs(r) < 2 and abs(p) < 3 and 0.1 < h < 0.4, f"roll {r:.1f} pitch {p:.1f} CG agl {h:.2f} m")

# 2 hover throttle: lowest equal lift throttle that climbs above 0.5 m in 2.5 s
hov = None
for k in range(30, 81):
    t = k / 100
    b = Bridge(ROOT, "CoconutQuadplane", 400.0)
    run(b, pwm(), 0.5)
    run(b, pwm(lift=t), 2.5)
    if b.f["position/h-agl-ft"] * 0.3048 > 0.5:
        hov = t
        break
check("hover throttle", hov is not None and 0.40 < hov < 0.65,
      f"lift-off at throttle {hov:.2f}, bus {b.pack.v_bus:.1f} V" if hov else "never lifted")

# 3 yaw: hover, then CCW pair (M1,M2) +0.05, CW pair (M3,M4) -0.05
t0 = hov or 0.45
b = Bridge(ROOT, "CoconutQuadplane", 400.0)
run(b, pwm(lift=t0 + 0.05), 2.0)
run(b, pwm(lift4=[t0 + 0.08, t0 + 0.08, t0 - 0.02, t0 - 0.02]), 0.6)
rr = math.degrees(b.f["velocities/r-rad_sec"])
check("yaw sign", rr > 5, f"yaw rate {rr:+.1f} deg/s (expect +, nose right)")

# 4 glide from 150 m at 15 m/s, all off, elevons neutral: L/D over 20-40 s
b = Bridge(ROOT, "CoconutQuadplane", 400.0)
f = b.f
f["ic/h-agl-ft"] = 150 / 0.3048
f["ic/u-fps"] = 15 / 0.3048
f.run_ic()
for i in range(int(40 / b.dt)):
    b.step(pwm())
    if abs((i + 1) * b.dt - 20) < b.dt / 2:
        h0, x0 = f["position/h-agl-ft"] * 0.3048, f["position/distance-from-start-mag-mt"]
h1, x1 = f["position/h-agl-ft"] * 0.3048, f["position/distance-from-start-mag-mt"]
ld, v = (x1 - x0) / (h0 - h1), f["velocities/vt-fps"] * 0.3048
check("hands-off glide", 8 < ld < 18 and 12 < v < 21,
      f"L/D {ld:.1f}, sink {(h0 - h1) / 20:.2f} m/s, airspeed {v:.1f} m/s (stable, no divergence)")

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
