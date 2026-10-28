#!/usr/bin/env python3
"""
jsbsim_bridge.py — ArduPilot SITL  <->  JSBSim physics bridge.

ArduPilot runs with the generic external-physics backend (`-f JSON`) and sends
a servo/PWM packet each frame; this bridge drives the CoconutQuadplane JSBSim
model with it and returns the vehicle state. That puts the REAL SD7037 /
NACA 0009 aerodynamics under ArduPilot instead of its built-in generic model.

Control mapping
---------------
  SERVO1,2  (ailerons, fn 4)        ->  fcs/aileron-cmd-norm   (average of the two)
  SERVO3    (throttle, fn 70)       ->  forward pusher thrust  (external_reactions/fwdMotor)
  SERVO4    (tail elevator, fn 19)  ->  fcs/elevator-cmd-norm
  SERVO5-8  (motors 1-4, fn 33-36)  ->  4 lift rotors  (external_reactions/liftM1..4)
                                        + a yaw-reaction couple from motor torque

Thrust and torque come from rotor_model.py: A2212 1400KV motors on measured
APC 10x4.7 prop data, with motor/rotor dynamics (spool lag) and a sagging 3S
pack. The lift thrust lines carry the airframe's 5 deg yaw tilt (XML).

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

import rotor_model as rm

FT2M = 0.3048
M2FT = 1.0 / FT2M
LBF2N = 4.4482216
G = 9.80665

LIFT_SPIN = (+1, +1, -1, -1)   # quad-X M1 FR, M2 RL CCW (+yaw reaction); M3 FL, M4 RR CW
YAW_ARM = 0.80                 # m, matches the XML yaw-couple force positions


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
    def __init__(self, root, model, rate_hz, elevon_pitch=-1.0, elevon_roll=1.0,
                 home=(10.6609, 77.0048, 300.0), heading_deg=180.0, wind_ne=(0.0, 0.0), gust=0.0):
        # elevon_pitch / elevon_roll: signs from PWM to JSBSim surface; set by
        # control_sign_check.py (open loop) so that higher PWM = nose up / roll right.
        self.f = jsbsim.FGFDMExec(root, None)
        self.f.set_debug_level(0)
        if not self.f.load_model(model):
            raise SystemExit(f"could not load model {model}")
        self.dt = 1.0 / rate_hz
        self.f.set_dt(self.dt)
        self.ep, self.er = elevon_pitch, elevon_roll
        self.home = home
        self.heading = heading_deg
        self.wind_ne, self.gust = wind_ne, gust
        self.rotors = [rm.Rotor() for _ in range(5)]     # 4 lift + pusher
        self.pack = rm.Pack()
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
        f["ic/h-agl-ft"] = 0.74          # feet 0.22 m below the CG, resting on the pad
        f["ic/psi-true-deg"] = self.heading
        f["ic/phi-deg"] = 0.0
        f["ic/theta-deg"] = 0.0
        for k in ("u", "v", "w", "p", "q", "r"):
            f[f"ic/{k}-fps" if k in "uvw" else f"ic/{k}-rad_sec"] = 0.0
        f.run_ic()
        # mean wind (air moving TOWARD north/east, m/s) + MIL-spec turbulence;
        # gust ~ rms gust m/s: <=1.5 light (severity 1), <=3 moderate (3), else 4
        f["atmosphere/wind-north-fps"] = self.wind_ne[0] * M2FT
        f["atmosphere/wind-east-fps"] = self.wind_ne[1] * M2FT
        if self.gust > 0:
            f["atmosphere/turb-type"] = 3
            f["atmosphere/turbulence/milspec/windspeed_at_20ft_AGL-fps"] =                 max(1.0, math.hypot(*self.wind_ne)) * M2FT
            f["atmosphere/turbulence/milspec/severity"] = 1 if self.gust <= 1.5 else 3 if self.gust <= 3 else 4
        # never start the piston/brushless engine — all thrust is external
        try:
            f["propulsion/engine[0]/set-running"] = 0
        except Exception:
            pass
        for name in ("liftM1", "liftM2", "liftM3", "liftM4", "fwdMotor",
                     "yawTorqueF", "yawTorqueA"):
            f[f"external_reactions/{name}/magnitude"] = 0.0
        self.rotors = [rm.Rotor() for _ in range(5)]
        self.pack = rm.Pack()
        self.sim_t = 0.0
        self.started = True

    # ---- one physics frame -------------------------------------------------
    def step(self, pwm):
        f = self.f

        # ArduPilot: higher PWM = roll right (fn 4) / nose up (fn 19)
        roll = self.er * 0.5 * (pwm_norm(pwm[0]) + pwm_norm(pwm[1]))
        pitch = self.ep * pwm_norm(pwm[3])
        f["fcs/elevator-cmd-norm"] = clamp(pitch, -1, 1)
        f["fcs/aileron-cmd-norm"] = clamp(roll, -1, 1)
        f["fcs/rudder-cmd-norm"] = 0.0

        u = f["velocities/u-aero-fps"] * FT2M       # body, +forward
        w = f["velocities/w-aero-fps"] * FT2M       # body, +down
        thr = [pwm_throttle(pwm[4 + i]) for i in range(4)] + [pwm_throttle(pwm[2])]
        vb = self.pack.solve(self.rotors, thr)
        Tf = self.rotors[4].step(thr[4], u, vb, self.dt)
        f["external_reactions/fwdMotor/magnitude"] = Tf / LBF2N
        Mz = 0.0
        for i in range(4):
            T = self.rotors[i].step(thr[i], -w, vb, self.dt)
            f[f"external_reactions/liftM{i + 1}/magnitude"] = T / LBF2N
            Mz += LIFT_SPIN[i] * self.rotors[i].torque   # reaction on the airframe
        self.i_total = self.pack.update(self.rotors, thr, self.dt)   # A drawn from the pack, all five motors
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
            # the pack model (rotor_model.Pack): ArduPilot's battery monitor integrates
            # this current, so battery % drains as the motors draw power
            "battery": {"voltage": self.pack.v_bus, "current": getattr(self, "i_total", 0.0)},
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
    ap.add_argument("--elevon-roll", type=float, default=1.0)
    ap.add_argument("--home", default="10.6609,77.0048,300", help="lat,lon,alt_m of the pad")
    ap.add_argument("--heading", type=float, default=180.0, help="initial heading, deg")
    ap.add_argument("--wind-n", type=float, default=0.0)
    ap.add_argument("--wind-e", type=float, default=0.0)
    ap.add_argument("--gust", type=float, default=0.0)
    args = ap.parse_args()

    b = Bridge(args.root, args.model, args.rate,
               elevon_pitch=args.elevon_pitch, elevon_roll=args.elevon_roll,
               home=tuple(float(x) for x in args.home.split(",")), heading_deg=args.heading,
               wind_ne=(args.wind_n, args.wind_e), gust=args.gust)
    serve(b, args.port, not args.no_lockstep)


if __name__ == "__main__":
    main()
