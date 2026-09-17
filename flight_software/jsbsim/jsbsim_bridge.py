#!/usr/bin/env python3
"""
jsbsim_bridge.py — ArduPilot SITL  <->  JSBSim physics bridge.

ArduPilot runs with the generic external-physics backend (`-f JSON`) and sends
a servo/PWM packet each frame; this bridge drives the CoconutQuadplane JSBSim
model with it and returns the vehicle state. That puts the REAL SD7037 /
NACA 0009 aerodynamics under ArduPilot instead of its built-in generic model.

Control mapping
---------------
  SERVO1,2  (elevon L/R, fn 77/78)  ->  fcs/elevator-cmd-norm + fcs/aileron-cmd-norm
  SERVO3    (throttle, fn 70)       ->  forward pusher thrust  (external_reactions/fwdMotor)
  SERVO5-8  (motors 1-4, fn 33-36)  ->  4 lift rotors  (external_reactions/liftM1..4)
                                        + a yaw-reaction couple from motor torque

Thrust is a SIMPLE calibrated model (see PROPULSION_NOTES.md) — the fixed-wing
aero is the real deliverable; hover/transition thrust is indicative only.

Usage
-----
  # 1. start this first
  python jsbsim_bridge.py --root . --model CoconutQuadplane
  # 2. then, in WSL:
  sim_vehicle.py -v ArduPlane -f JSON --no-mavproxy -w \
      --add-param-file="/mnt/e/.../coconut_quadplane.param"
"""
from __future__ import annotations

import argparse
import json
import math
import socket
import struct
import time

import jsbsim

FT2M = 0.3048
M2FT = 1.0 / FT2M
LBF2N = 4.4482216
G = 9.80665

# ---- simple thrust model (calibrated, not measured — PROPULSION_NOTES.md) ----
LIFT_TMAX_N = 11.0       # per lift rotor, static (A2212 2200KV + 1045, ~1.1 kgf);
                        #   4x11 vs 13.7 N weight -> hover ~0.56, decel margin
LIFT_EXP = 1.6          # T ~ throttle**exp  (prop + ESC nonlinearity)
FWD_TMAX_N = 8.0        # forward pusher, static (helps hold cruise speed)
FWD_VMAX = 45.0        # m/s where forward thrust -> ~0 at full throttle
K_REACT = 0.020          # lift-motor yaw reaction torque / thrust  [N·m / N]
YAW_ARM = 0.80           # m, matches the XML yaw-couple force positions


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def pwm_norm(pwm):          # -1..1 for a control surface
    return clamp((pwm - 1500.0) / 500.0, -1.0, 1.0)


def pwm_throttle(pwm):      # 0..1
    if pwm < 1000:
        return 0.0
    return clamp((pwm - 1000.0) / 1000.0, 0.0, 1.0)


def euler_to_quat(phi, theta, psi):
    cy, sy = math.cos(psi * 0.5), math.sin(psi * 0.5)
    cp, sp = math.cos(theta * 0.5), math.sin(theta * 0.5)
    cr, sr = math.cos(phi * 0.5), math.sin(phi * 0.5)
    return [cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy]


class Bridge:
    def __init__(self, root, model, rate_hz, elevon_pitch=-1.0, elevon_roll=-1.0,
                 home=(-35.363261, 149.165230, 584.0)):
        # elevon_pitch/-roll default -1: verified against ArduPilot's SERVO
        # function 77/78 output in the SITL bridge — with +1 the vehicle PIO'd
        # and departed (positive feedback); -1 gives correct roll/pitch response.
        self.f = jsbsim.FGFDMExec(root, None)
        self.f.set_debug_level(0)
        if not self.f.load_model(model):
            raise SystemExit(f"could not load model {model}")
        self.dt = 1.0 / rate_hz
        self.f.set_dt(self.dt)
        self.ep, self.er = elevon_pitch, elevon_roll
        self.home = home
        self.sim_t = 0.0
        self.started = False
        self.reset()

    def reset(self):
        self._reset_ic()

    def _reset_ic(self):
        f = self.f
        lat, lon, elev_m = self.home
        f["ic/lat-geod-deg"] = lat
        f["ic/long-gc-deg"] = lon
        f["ic/terrain-elevation-ft"] = elev_m * M2FT
        f["ic/h-agl-ft"] = 0.43          # legs (13 cm below CG) resting on ground
        f["ic/psi-true-deg"] = 0.0
        f["ic/phi-deg"] = 0.0
        f["ic/theta-deg"] = 0.0
        for k in ("u", "v", "w", "p", "q", "r"):
            f[f"ic/{k}-fps" if k in "uvw" else f"ic/{k}-rad_sec"] = 0.0
        f.run_ic()
        # never start the piston/brushless engine — all thrust is external
        try:
            f["propulsion/engine[0]/set-running"] = 0
        except Exception:
            pass
        for name in ("liftM1", "liftM2", "liftM3", "liftM4", "fwdMotor",
                     "yawTorqueF", "yawTorqueA"):
            f[f"external_reactions/{name}/magnitude"] = 0.0
        self.sim_t = 0.0
        self.started = True

    # ---- one physics frame -------------------------------------------------
    def step(self, pwm):
        f = self.f

        nl, nr = pwm_norm(pwm[0]), pwm_norm(pwm[1])
        pitch = self.ep * 0.5 * (nl + nr)
        roll = self.er * 0.5 * (nl - nr)
        f["fcs/elevator-cmd-norm"] = clamp(pitch, -1, 1)
        f["fcs/aileron-cmd-norm"] = clamp(roll, -1, 1)
        f["fcs/rudder-cmd-norm"] = 0.0

        V = f["velocities/vt-fps"] * FT2M
        thr_f = pwm_throttle(pwm[2])
        Tf = FWD_TMAX_N * thr_f ** 2 * clamp(1.0 - V / FWD_VMAX, 0.10, 1.0)
        f["external_reactions/fwdMotor/magnitude"] = Tf / LBF2N

        thr = [pwm_throttle(pwm[4 + i]) for i in range(4)]
        T = [LIFT_TMAX_N * t ** LIFT_EXP for t in thr]
        for i in range(4):
            f[f"external_reactions/liftM{i + 1}/magnitude"] = T[i] / LBF2N
        # M1,M2 CCW ; M3,M4 CW  -> net reaction M_z
        Mz = K_REACT * (T[0] + T[1] - T[2] - T[3])           # N·m
        mag_lbf = (Mz / (2.0 * YAW_ARM)) / LBF2N
        f["external_reactions/yawTorqueF/magnitude"] = mag_lbf
        f["external_reactions/yawTorqueA/magnitude"] = mag_lbf

        f.run()
        self.sim_t += self.dt

    # ---- state packet for ArduPilot -------------------------------------
    def state(self):
        f = self.f
        gyro = [f["velocities/p-rad_sec"],
                f["velocities/q-rad_sec"],
                f["velocities/r-rad_sec"]]
        acc = [f["accelerations/a-pilot-x-ft_sec2"] * FT2M,
               f["accelerations/a-pilot-y-ft_sec2"] * FT2M,
               f["accelerations/a-pilot-z-ft_sec2"] * FT2M]
        q = euler_to_quat(f["attitude/phi-rad"],
                          f["attitude/theta-rad"],
                          f["attitude/psi-rad"])
        vel = [f["velocities/v-north-fps"] * FT2M,
               f["velocities/v-east-fps"] * FT2M,
               f["velocities/v-down-fps"] * FT2M]
        return {
            "timestamp": self.sim_t,
            "imu": {"gyro": gyro, "accel_body": acc},
            "latitude": f["position/lat-geod-deg"],
            "longitude": f["position/long-gc-deg"],
            "altitude": f["position/h-sl-ft"] * FT2M,
            "quaternion": q,
            "velocity": vel,
            "airspeed": max(0.0, f["velocities/vt-fps"] * FT2M),
        }


def serve(bridge, port, lockstep):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    print(f"[bridge] listening on 127.0.0.1:{port}  dt={bridge.dt*1e3:.2f} ms  "
          f"lockstep={lockstep}")
    peer = None
    last_report = time.time()
    frames = 0
    magic16, magic32 = 18458, 29569

    while True:
        data, peer = sock.recvfrom(4096)
        if len(data) < 8:
            continue
        magic, rate, count = struct.unpack_from("<HHI", data, 0)
        if magic == magic16:
            n = 16
        elif magic == magic32:
            n = 32
        else:
            continue
        pwm = struct.unpack_from("<%dH" % n, data, 8)

        bridge.step(pwm)
        msg = ("\n" + json.dumps(bridge.state()) + "\n").encode()
        sock.sendto(msg, peer)

        frames += 1
        now = time.time()
        if now - last_report >= 2.0:
            s = bridge.state()
            print(f"[bridge] t={bridge.sim_t:7.1f}s  {frames/(now-last_report):5.0f} fps  "
                  f"alt={s['altitude']:6.1f}  V={s['airspeed']:4.1f}  "
                  f"att=({math.degrees(bridge.f['attitude/phi-rad']):+5.1f},"
                  f"{math.degrees(bridge.f['attitude/theta-rad']):+5.1f},"
                  f"{math.degrees(bridge.f['attitude/psi-rad']):+6.1f})")
            last_report, frames = now, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--model", default="CoconutQuadplane")
    ap.add_argument("--port", type=int, default=9002)
    ap.add_argument("--rate", type=float, default=400.0)
    ap.add_argument("--no-lockstep", action="store_true")
    ap.add_argument("--elevon-pitch", type=float, default=-1.0)
    ap.add_argument("--elevon-roll", type=float, default=-1.0)
    args = ap.parse_args()

    b = Bridge(args.root, args.model, args.rate,
               elevon_pitch=args.elevon_pitch, elevon_roll=args.elevon_roll)
    serve(b, args.port, not args.no_lockstep)


if __name__ == "__main__":
    main()
