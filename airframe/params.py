"""
params.py -- single source of truth for the print-ready CoconutQuadplane.

Read by build_airframe.py (CAD + mass/CG report) and by
flight_software/gazebo/gen_sdf.py (simulation model), so the airframe you
print and the airframe you simulate are the same numbers.

Build frame (mm): X aft from the wing-root leading edge, Y to the RIGHT,
Z up. Body-frame FLU for simulation: x = X_cg - X, y = -Y, z = Z - Z_cg.

Aerodynamic geometry comes from aero/coefficients.json (the analysed
design), not from the older KCL-traced FreeCAD model in models/freecad/
(that one is 1.5 m span; the aero, trim and fin sizing were all done at
1.30 m).
"""
from __future__ import annotations

import math

# --------------------------------------------------------------------------
# Print constraints
# --------------------------------------------------------------------------
BED = (220.0, 220.0, 250.0)       # mm, Ender-3 / A1-mini class; every part fits
WALL = 0.8                        # mm, 2 perimeters at 0.4 nozzle (shells)
SKIN = 0.45                       # mm, single-wall wing / tail skin (printed "spiral-like")
CLEAR = 0.25                      # mm, sliding fit clearance (tube in printed bore)

# Material densities, g/cm^3
RHO = {
    "PLA": 1.24,
    "LW-PLA": 0.60,               # foamed (~0.5-0.7 depending on temperature)
    "PETG": 1.27,
    "CF": 1.55,                   # pultruded/rolled carbon tube
}

# --------------------------------------------------------------------------
# Wing (aero/coefficients.json geometry)
# --------------------------------------------------------------------------
SPAN = 1300.0
C_ROOT = 288.5
C_TIP = 173.1
SWEEP_LE_DEG = 2.0
I_WING_DEG = 1.0
AIRFOIL_WING = "SD7037"
MAC = 235.6
X_LE_MAC = 10.4
CG_FRAC_MAC = 0.33
X_CG_TARGET = X_LE_MAC + CG_FRAC_MAC * MAC          # 88.1 mm aft of root LE
X_CG_LIMITS = (X_LE_MAC + 0.25 * MAC, X_LE_MAC + 0.40 * MAC)   # 69..105 mm, SM 35%..20%

Z_WING = 62.0           # wing chord-line height at root (high wing on the pod)
SPAR_OD, SPAR_ID = 12.0, 10.0       # main spar tube, one piece 1250 mm
SPAR_X_FRAC = 0.26                  # spar at 26% chord (thickest-section region)
SPAR_LEN = 1250.0
PIN_OD = 4.0                        # anti-rotation rod through the inboard segments + node
PIN_X_ROOT_FRAC = 0.55              # fixed X = 55% of root chord (straight rod)
PIN_HALF = 302.0                    # each side runs Y 0..302 (stops short of the elevon bay)
PIN_LEN = 2 * PIN_HALF
ELEVON_CHORD_FRAC = 0.25
ELEVON_Y = (312.0, 645.0)           # per side, outboard of the boom node
ELEVON_SPLIT = 478.0                # two printed pieces per side (bed length), joined by a 2 mm rod

# The wing is two detachable halves meeting on the centreline above the pod;
# the one-piece spar and the pins pass through both. Segments per side (Y
# ranges, each < bed); the printed boom node sits at 290-310 on the spar.
WING_SEGMENTS = [(0.0, 145.0), (145.0, 290.0), (302.0, 478.0), (478.0, 650.0)]
NODE_Y = (290.0, 302.0)
WING_BOLTS = [(40.0, 22.0), (225.0, 22.0)]   # (X, |Y|) M4 nylon wing bolts into the pod saddle
# Segments whose chord exceeds the bed are split chordwise between the spar
# and the pin (each half keeps one rod for alignment), then glued.
CHORD_SPLIT_X = 118.0
CHORD_SPLIT_ABOVE = 215.0           # split when the segment's root chord exceeds this

# --------------------------------------------------------------------------
# Fuselage pod (printed in 3 sections + hatch)
# --------------------------------------------------------------------------
POD_X = (-200.0, 262.0)             # nose .. tail cone end
POD_W, POD_H = 124.0, 108.0         # max width / height (ellipse), mm -- sized to the
                                    # 138x46x30 battery + 36x36 FC stack, not bigger
# (X, width, height) ellipse stations, width >= height
POD_STATIONS = [
    (-200.0, 26.0, 22.0), (-192.0, 66.0, 58.0), (-175.0, 98.0, 85.0),
    (-140.0, 116.0, 101.0), (-90.0, POD_W, POD_H), (110.0, POD_W, POD_H),
    (175.0, 110.0, 95.0), (220.0, 78.0, 68.0), (262.0, 30.0, 26.0)]
# per-section material in the light config (mid carries the wing bolts)
POD_MATERIAL_LIGHT = {"pod_nose": "LW-PLA", "pod_mid": "PLA", "pod_tail": "LW-PLA", "hatch": "LW-PLA"}
POD_ZC = 0.0
POD_SECTIONS = [(-200.0, -20.0), (-20.0, 175.0), (175.0, 262.0)]
HATCH_X = (-165.0, 0.0)             # top hatch, ahead of the wing saddle
JOINT_LIP = 10.0                    # internal sleeve overlap at section joints

# --------------------------------------------------------------------------
# Tail (H-stab + twin fins on a carbon tail boom)
# --------------------------------------------------------------------------
TAILBOOM_OD, TAILBOOM_ID = 10.0, 8.0
S_H, B_H, TAPER_H = 63000.0, 500.0, 0.7          # mm^2, mm
C_ROOT_H = 2 * S_H / (B_H * (1 + TAPER_H))         # 148 mm
C_TIP_H = C_ROOT_H * TAPER_H
X_AC_W = X_LE_MAC + 0.25 * MAC
X_LE_H = X_AC_W + 500.0 - 0.25 * (C_ROOT_H + C_TIP_H) / 2   # tail arm 0.5 m (aero)
I_TAIL_DEG = -1.79                                   # relative to fuselage (aero/RESULTS.md)
Z_TAIL = 0.0                                         # tail boom on the pod axis
Z_STAB = Z_TAIL + 11.0                               # stab chord line sits on a keel over the boom
STAB_SPAR_OD = 4.0                                   # rod through the stab, 30% chord
# Tail elevator (2026-10-27): the wing elevons could not control pitch (a
# nose-up command mostly dumped wing lift -- documents/sim_results.md), so the
# stab gets an elevator and the wing surfaces become ailerons. Straight hinge
# line placed so the elevator is 30% of the stab area (straight LE):
# S/2 - x*B/2 = 0.3 S/2  ->  x = 0.7 S/B.
ELEV_HINGE_X = X_LE_H + 0.7 * S_H / B_H              # 88 mm aft of the stab LE
ELEV_GAP = 1.0                                       # mm, hinge gap (CA/tape hinge)
ELEV_BOOM_SLOT = 7.0                                 # mm half-width: elevator halves clear the boom
ELEV_JOINER_OD = 2.0                                 # carbon rod joining the 4 elevator pieces
ELEV_SERVO_X = 180.0     # elevator servo in the pod aft bay; a tail-mounted servo put the CG at 34.6% MAC
S_V_EACH, B_V, TAPER_V = 17000.0, 180.0, 0.62      # 340 cm^2 total (aero fin sizing)
C_ROOT_V = 2 * S_V_EACH / (B_V * (1 + TAPER_V))
C_TIP_V = C_ROOT_V * TAPER_V
AIRFOIL_TAIL = "NACA0009"
TAIL_SEGMENTS = [(-100.0, 100.0), (100.0, 250.0)]  # centre piece + one tip piece per side

# --------------------------------------------------------------------------
# VTOL booms, rotors, pusher, landing gear
# --------------------------------------------------------------------------
BOOM_Y = 300.0
BOOM_OD, BOOM_ID = 16.0, 14.0
PROP_D = 254.0                      # 10x4.5 (1045)
# front/rear rotors symmetric about the CG target so hover needs no trim
X_ROTOR_FRONT = X_CG_TARGET - 312.0
X_ROTOR_REAR = X_CG_TARGET + 312.0
BOOM_X = (X_ROTOR_FRONT - 25.0, X_ROTOR_REAR + 25.0)
Z_BOOM = Z_WING - 32.0              # boom centre below the wing spar
MOTOR_YAW_TILT_DEG = 5.0            # tangential tilt -- see flight_software/gazebo/README.md
LEG_LEN = 230.0                     # 6 mm carbon rod, boom to ground
LEG_OD = 6.0
GROUND_Z = Z_BOOM - LEG_LEN

X_TE_H = X_LE_H + C_ROOT_H
X_PUSHER = X_TE_H + 18.0
TAILBOOM_X = (POD_X[1] - 40.0, X_PUSHER - 8.0)

# --------------------------------------------------------------------------
# Off-the-shelf parts (mass g, position mm). Positions are where they go in
# the build; the battery slides to set the CG.
# --------------------------------------------------------------------------
COTS = {
    # name: (mass_g, X, Y, Z)
    "motor_lift_FR": (50.0, X_ROTOR_FRONT, BOOM_Y, Z_BOOM + 30),
    "motor_lift_FL": (50.0, X_ROTOR_FRONT, -BOOM_Y, Z_BOOM + 30),
    "motor_lift_RR": (50.0, X_ROTOR_REAR, BOOM_Y, Z_BOOM + 30),
    "motor_lift_RL": (50.0, X_ROTOR_REAR, -BOOM_Y, Z_BOOM + 30),
    "motor_pusher": (50.0, X_PUSHER - 15, 0, Z_TAIL),
    "props_x5": (50.0, (2 * X_ROTOR_FRONT + 2 * X_ROTOR_REAR + X_PUSHER) / 5, 0, Z_BOOM + 40),
    "esc_lift_x4": (100.0, (X_ROTOR_FRONT + X_ROTOR_REAR) / 2, 0, Z_BOOM),   # on the booms
    "esc_pusher": (25.0, 200.0, 0, 0),
    "servo_aileron_x2": (27.0, 120.0, 0, Z_WING),   # the former elevon servos
    "servo_elevator": (9.0, ELEV_SERVO_X, 0, 0.0),        # 9 g micro in the pod, near the CG
    "elevator_horn_clevis": (3.0, ELEV_HINGE_X, 0, Z_STAB - 8),
    "flight_controller": (10.0, X_CG_TARGET - 60, 0, -10),
    "gps_compass": (25.0, -95.0, 0, POD_H / 2 + 6),      # on the hatch, clear of the wing
    "esp32_cam": (12.0, -185.0, 0, -30),
    "tof_vl53l1x": (3.0, -150.0, 0, -60),
    "rx_telemetry": (12.0, 60.0, 0, -20),
    "wiring_pdb_xt60": (70.0, 0.0, 0, -20),
    "magnets_screws_inserts": (30.0, -60.0, 0, 0),
    "battery_3s_4000": (320.0, None, 0, -35),    # X solved for CG
}
BATTERY_X_RANGE = (-150.0, 60.0)     # tray slot range (battery centre)
BATTERY_DIMS = (138.0, 46.0, 30.0)   # 3S 4000 mAh class, mm

# Carbon parts: (od, id_or_0_for_rod, length, centre X, Y, Z, count)
CARBON = {
    "main_spar": (SPAR_OD, SPAR_ID, SPAR_LEN, X_LE_MAC + SPAR_X_FRAC * MAC, 0, Z_WING, 1),
    "booms": (BOOM_OD, BOOM_ID, BOOM_X[1] - BOOM_X[0], sum(BOOM_X) / 2, 0, Z_BOOM, 2),
    "tailboom": (TAILBOOM_OD, TAILBOOM_ID, TAILBOOM_X[1] - TAILBOOM_X[0], sum(TAILBOOM_X) / 2, 0, Z_TAIL, 1),
    "legs": (LEG_OD, 0, LEG_LEN, (X_ROTOR_FRONT + X_ROTOR_REAR) / 2, 0, Z_BOOM - LEG_LEN / 2, 4),
    "wing_pins": (PIN_OD, 0, PIN_LEN, PIN_X_ROOT_FRAC * C_ROOT, 0, Z_WING, 1),
    "stab_spar": (STAB_SPAR_OD, 0, B_H, X_LE_H + 0.3 * C_ROOT_H, 0, Z_STAB, 1),
    "elevator_joiner": (ELEV_JOINER_OD, 0, 300.0, ELEV_HINGE_X + 4.0, 0, Z_STAB, 1),
    "elevator_pushrod": (1.5, 0, ELEV_HINGE_X - ELEV_SERVO_X, (ELEV_HINGE_X + ELEV_SERVO_X) / 2, 0, Z_TAIL + 8, 1),
}


def carbon_mass_g(od, idd, length, count=1):
    area = math.pi / 4 * (od ** 2 - idd ** 2)      # mm^2
    return area * length / 1000.0 * RHO["CF"] * count
