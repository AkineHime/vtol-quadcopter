"""Open-loop sign check at 15 m/s: higher PWM must give nose-up (SERVO4,
elevator) and roll-right (SERVO1+2, ailerons) -- ArduPilot's convention."""
import math
from jsbsim_bridge import Bridge


def rates(ch, d, ep, er):
    b = Bridge(".", "CoconutQuadplane", 1000.0, elevon_pitch=ep, elevon_roll=er); f = b.f
    f["ic/h-agl-ft"] = 200 / 0.3048; f["ic/u-fps"] = 15 / 0.3048; f.run_ic()
    p = [1500, 1500, 1000, 1500, 1000, 1000, 1000, 1000] + [1500] * 8
    for c in ch:
        p[c] += d
    for _ in range(250):
        b.step(p)
    return math.degrees(f["velocities/q-rad_sec"]), math.degrees(f["velocities/p-rad_sec"])


for ep, er in ((-1, 1), (1, -1), (-1, -1), (1, 1)):
    q, _ = rates([3], +150, ep, er)
    _, pr = rates([0, 1], +150, ep, er)
    print(f"ep {ep:+d} er {er:+d}: SERVO4 +150 -> pitch rate {q:+6.1f}  |  SERVO1/2 +150 -> roll rate {pr:+6.1f}")
