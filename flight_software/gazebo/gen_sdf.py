#!/usr/bin/env python3
"""
gen_sdf.py -- write the Gazebo (Harmonic) model of the CoconutQuadplane.

    python gen_sdf.py        ->  models/coconut_quadplane/{model.sdf,model.config}

Body frame is FLU (x forward, y left, z up), origin at the CG.

Where the numbers come from:
  * wing / H-tail / fin lift-drag   aero/coefficients.json (SD7037 + NACA 0009,
                                     NeuralFoil 2D -> finite-span correction)
  * mass, inertia                    jsbsim/aircraft/CoconutQuadplane/CoconutQuadplane.xml
  * rotor / pusher positions         models/freecad/build_assembly.py
                                     (CAD x-aft, y-right -> rotated 180 deg about z)
  * rotor blade aero, motor gains    ardupilot_gazebo's iris (1.5 kg quad, 10" props
                                     -- the closest stock match to our 1.4 kg / 1045)
  * pusher blade aero                ardupilot_gazebo's zephyr

The prop models are the stock Gazebo blade-element approximations, not
measured A2212 + 1045 data (see jsbsim/PROPULSION_NOTES.md).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "models" / "coconut_quadplane"

coef = json.loads((REPO / "aero" / "coefficients.json").read_text())
G = coef["geometry"]
WING = coef["sections_2D"]["SD7037"]["cruise"]
TAIL = coef["sections_2D"]["NACA0009"]["cruise"]

# --- the printed build (airframe/params.py + its mass report) -------------
import sys  # noqa: E402
sys.path.insert(0, str(REPO / "airframe"))
import params as AF  # noqa: E402

_mp = json.loads((REPO / "airframe" / "out" / "mass_properties.json").read_text())["configs"][0]
X_CG, _, Z_CG = _mp["cg_build_mm"]            # build frame, mm


def flu(X, Y, Z):
    """build frame (mm, X aft, Y right, Z up) -> FLU about the CG (m)."""
    return ((X_CG - X) / 1000.0, -Y / 1000.0, (Z - Z_CG) / 1000.0)


MASS = _mp["total_g"] / 1000.0                 # 1.84 kg (LW-PLA build)
IXX, IYY, IZZ = (_mp["inertia_kgm2_flu"][k] for k in ("ixx", "iyy", "izz"))
RHO = 1.13                            # 35 C at ~300 m (Tamil Nadu daytime)
OSWALD = 0.79                         # aero/RESULTS.md (e ~ 0.793)

ROTOR_MASS = 0.025
PROP_R = AF.PROP_D / 2000.0
# Order = ArduPilot quad-X motors 1..4 (FR, RL, FL, RR) on SERVO5..8 ->
# plugin channels 4..7. Spin sign follows iris rotor_0..3. Build frame Y is
# to the RIGHT, so the right boom is +Y.
_zr = AF.Z_BOOM + 30
ROTORS = [
    ("rotor_fr", flu(AF.X_ROTOR_FRONT, AF.BOOM_Y, _zr), +1),
    ("rotor_rl", flu(AF.X_ROTOR_REAR, -AF.BOOM_Y, _zr), +1),
    ("rotor_fl", flu(AF.X_ROTOR_FRONT, -AF.BOOM_Y, _zr), -1),
    ("rotor_rr", flu(AF.X_ROTOR_REAR, AF.BOOM_Y, _zr), -1),
]
# Lift-motor yaw tilt. Rotor drag torque alone could not hold heading
# against the (correctly sized, 340 cm^2) fins weathervaning at 4-10 m/s in
# VTOL flight -- yaw output saturated while the nose swung 50 deg. Common
# quadplane practice: tilt each lift motor a few degrees so its thrust has a
# tangential component in the same sense as its reaction torque. Built into
# the printed motor pods.
MOTOR_YAW_TILT_DEG = AF.MOTOR_YAW_TILT_DEG
PUSHER_POS = flu(AF.X_PUSHER, 0, AF.Z_TAIL)
GROUND_Z = flu(0, 0, AF.GROUND_Z)[2]
FEET = [flu(x, y, 0)[:2] for x in (AF.X_ROTOR_FRONT, AF.X_ROTOR_REAR) for y in (AF.BOOM_Y, -AF.BOOM_Y)]

# aero reference points from the build geometry
MAC = G["MAC_w"]
X_AC_W = flu(AF.X_AC_W, 0, 0)[0]
X_TE_W = flu(AF.X_LE_MAC + AF.MAC, 0, 0)[0]
X_AC_H = flu(AF.X_LE_H + 0.25 * (AF.C_ROOT_H + AF.C_TIP_H) / 2, 0, 0)[0]
Y_FIN = AF.B_H / 2000.0
Z_WING_REL = flu(0, 0, AF.Z_WING)[2]
Z_TAIL_REL = flu(0, 0, AF.Z_STAB)[2]


def lift_slope_3d(a0: float, ar: float, e: float = OSWALD) -> float:
    return a0 / (1.0 + a0 / (math.pi * e * ar))


def liftdrag(link: str, *, a0: float, cla: float, cda: float, alpha_stall: float,
             area: float, cp, forward, upward, control_joint: str | None = None,
             rad_to_cl: float = 0.0, comment: str = "") -> str:
    ctrl = ""
    if control_joint:
        ctrl = (f"\n      <control_joint_name>{control_joint}</control_joint_name>"
                f"\n      <control_joint_rad_to_cl>{rad_to_cl:.3f}</control_joint_rad_to_cl>")
    v = lambda t: " ".join(f"{x:.4f}" for x in t)  # noqa: E731
    return f"""
    <!-- {comment} -->
    <plugin filename="gz-sim-lift-drag-system" name="gz::sim::systems::LiftDrag">
      <a0>{a0:.4f}</a0>
      <cla>{cla:.4f}</cla>
      <cda>{cda:.4f}</cda>
      <cma>0.0</cma>
      <alpha_stall>{alpha_stall:.4f}</alpha_stall>
      <cla_stall>-3.85</cla_stall>
      <cda_stall>-0.9234</cda_stall>
      <cma_stall>0.0</cma_stall>
      <cp>{v(cp)}</cp>
      <area>{area:.4f}</area>
      <air_density>{RHO}</air_density>
      <forward>{v(forward)}</forward>
      <upward>{v(upward)}</upward>
      <link_name>{link}</link_name>{ctrl}
    </plugin>"""


def inertial(mass, ixx, iyy, izz) -> str:
    return f"""<inertial>
        <mass>{mass}</mass>
        <inertia><ixx>{ixx}</ixx><ixy>0</ixy><ixz>0</ixz><iyy>{iyy}</iyy><iyz>0</iyz><izz>{izz}</izz></inertia>
      </inertial>"""


def yaw_tilt_rpy(pos, spin: int) -> tuple[float, float]:
    """roll, pitch that lean a lift rotor's thrust axis tangentially so the
    thrust adds yaw torque in the same sense as the prop's reaction torque
    (spin +1 = CCW from above -> reaction torque -z)."""
    x, y = pos[0], pos[1]
    r = math.hypot(x, y)
    ux, uy = (y / r, -x / r) if spin > 0 else (-y / r, x / r)
    th = math.radians(MOTOR_YAW_TILT_DEG)
    roll = -math.asin(math.sin(th) * uy)
    pitch = math.asin(math.sin(th) * ux / math.cos(roll))
    return roll, pitch


def rotor_link(name, pos, axis, colour, rp=(0.0, 0.0)) -> str:
    x, y, z = pos
    return f"""
    <link name="{name}">
      <pose>{x} {y} {z} {rp[0]:.4f} {rp[1]:.4f} 0</pose>
      {inertial(ROTOR_MASS, 9.75e-06, 0.000166704, 0.000167604)}
      <collision name="collision">
        <pose>0 0 0 {'0 1.5708 0' if axis == 'x' else '0 0 0'}</pose>
        <geometry><cylinder><length>0.005</length><radius>0.05</radius></cylinder></geometry>
      </collision>
      <visual name="disc">
        <pose>0 0 0 {'0 1.5708 0' if axis == 'x' else '0 0 0'}</pose>
        <geometry><cylinder><length>0.004</length><radius>{PROP_R}</radius></cylinder></geometry>
        <material><ambient>{colour} 0.35</ambient><diffuse>{colour} 0.35</diffuse></material>
        <transparency>0.6</transparency>
      </visual>
      <visual name="blade">
        <pose>0 0 0 {'0 1.5708 0' if axis == 'x' else '0 0 0'}</pose>
        <geometry><box><size>{2 * PROP_R} 0.02 0.006</size></box></geometry>
        <material><ambient>0.1 0.1 0.1 1</ambient><diffuse>0.1 0.1 0.1 1</diffuse></material>
      </visual>
    </link>
    <joint name="{name}_joint" type="revolute">
      <child>{name}</child>
      <parent>base_link</parent>
      <axis>
        <xyz>{'1 0 0' if axis == 'x' else '0 0 1'}</xyz>
        <limit><lower>-1e+16</lower><upper>1e+16</upper></limit>
        <dynamics><damping>0.004</damping></dynamics>
      </axis>
    </joint>"""


def elevon_link(side: str, ysign: int) -> str:
    y = ysign * (0.12 + 0.26)
    return f"""
    <link name="elevon_{side}">
      <pose>{X_TE_W + 0.02:.4f} {y:.4f} {Z_WING_REL:.4f} 0 0 0</pose>
      {inertial(0.01, 1e-5, 1e-5, 1e-5)}
      <visual name="visual">
        <pose>-0.025 0 0 0 0 0</pose>
        <geometry><box><size>0.05 0.52 0.006</size></box></geometry>
        <material><ambient>0.9 0.5 0.1 1</ambient><diffuse>0.9 0.5 0.1 1</diffuse></material>
      </visual>
    </link>
    <joint name="elevon_{side}_joint" type="revolute">
      <child>elevon_{side}</child>
      <parent>base_link</parent>
      <axis>
        <xyz>0 1 0</xyz>
        <limit><lower>-0.53</lower><upper>0.53</upper></limit>
        <dynamics><damping>0.01</damping></dynamics>
      </axis>
    </joint>"""


def control(channel, joint, *, multiplier, offset, kind, p_gain, cmd_min, cmd_max,
            comment, slowdown=False) -> str:
    extra = "\n        <controlVelocitySlowdownSim>1</controlVelocitySlowdownSim>" if slowdown else ""
    return f"""
      <!-- {comment} -->
      <control channel="{channel}">
        <jointName>{joint}</jointName>
        <useForce>1</useForce>
        <multiplier>{multiplier}</multiplier>
        <offset>{offset}</offset>
        <servo_min>1000</servo_min>
        <servo_max>2000</servo_max>
        <type>{kind}</type>
        <p_gain>{p_gain}</p_gain>
        <i_gain>0</i_gain>
        <d_gain>0</d_gain>
        <i_max>0</i_max>
        <i_min>0</i_min>
        <cmd_max>{cmd_max}</cmd_max>
        <cmd_min>{cmd_min}</cmd_min>{extra}
      </control>"""


def build() -> str:
    body_mass = MASS - 5 * ROTOR_MASS - 2 * 0.01 - 0.15   # minus rotors, elevons, imu

    # --- wing: two halves, each carrying its elevon -----------------------
    ar_w = G["AR_w"]
    cla_w = lift_slope_3d(WING["a0_per_rad"], ar_w)
    a0_w = math.radians(G["i_w_deg"] - WING["alpha_L0_deg"])     # incidence + camber
    stall_w = math.radians(WING["alpha_clmax_deg"] - WING["alpha_L0_deg"])
    # Gazebo's LiftDrag drag is linear in |alpha|; pick cda so the cruise
    # point (alpha_eff ~ a0 + 1.25 deg trim) reproduces CD ~ 0.035.
    cda_w = 0.035 / (a0_w + math.radians(1.25))
    y_mac = G["y_MAC"]
    # Elevons get their OWN lift elements at the trailing edge (as in the stock
    # zephyr). Gazebo's LiftDrag control term only changes C_L at the element's
    # cp; putting it on the main wing element (AC slightly ahead of the CG)
    # made trailing-edge-up pitch the nose DOWN -- the opposite of a real
    # elevon, whose flap moment acts aft of the CG. The main element moves
    # forward so the combined wing AC stays at X_AC_W.
    s_elev = 0.03                           # per side, ~25% chord x 0.5 m span
    s_main = G["S_w"] / 2 - s_elev
    x_main = (G["S_w"] / 2 * X_AC_W - s_elev * X_TE_W) / s_main
    y_elev = sum(AF.ELEVON_Y) / 2000.0
    rad_to_cl = -0.8 * cla_w   # joint +ve = trailing edge up = less lift (aft) = nose up

    # --- H-tail + twin fins -------------------------------------------------
    ar_h = G["b_h"] ** 2 / G["S_h"]
    cla_h = lift_slope_3d(TAIL["a0_per_rad"], ar_h)
    # -1.79 deg design incidence (aero/RESULTS.md) less ~1.2 deg mean cruise
    # downwash, which LiftDrag does not model: at -1.79 the sim needed full
    # up-elevon in level flight and spiralled in a 40 deg bank (fw_calm, rec).
    a0_h = math.radians(-3.0)
    stall_h = math.radians(TAIL["alpha_clmax_deg"])
    ar_v = 2 * G["b_v"] ** 2 / (2 * G["Sv_each"])   # end-plated by the tail
    cla_v = lift_slope_3d(TAIL["a0_per_rad"], ar_v)
    sv_each = 0.0170                      # recommended 340 cm^2 total (aero/RESULTS.md)

    aero = "".join([
        liftdrag("base_link", a0=a0_w, cla=cla_w, cda=cda_w, alpha_stall=stall_w,
                 area=s_main, cp=(x_main, y_mac, Z_WING_REL), forward=(1, 0, 0),
                 upward=(0, 0, 1), comment="left wing half, SD7037"),
        liftdrag("base_link", a0=a0_w, cla=cla_w, cda=cda_w, alpha_stall=stall_w,
                 area=s_main, cp=(x_main, -y_mac, Z_WING_REL), forward=(1, 0, 0),
                 upward=(0, 0, 1), comment="right wing half, SD7037"),
        liftdrag("base_link", a0=a0_w, cla=cla_w, cda=cda_w, alpha_stall=stall_w,
                 area=s_elev, cp=(X_TE_W, y_elev, Z_WING_REL), forward=(1, 0, 0),
                 upward=(0, 0, 1), control_joint="elevon_left_joint",
                 rad_to_cl=rad_to_cl, comment="left elevon strip (trailing edge)"),
        liftdrag("base_link", a0=a0_w, cla=cla_w, cda=cda_w, alpha_stall=stall_w,
                 area=s_elev, cp=(X_TE_W, -y_elev, Z_WING_REL), forward=(1, 0, 0),
                 upward=(0, 0, 1), control_joint="elevon_right_joint",
                 rad_to_cl=rad_to_cl, comment="right elevon strip (trailing edge)"),
        liftdrag("base_link", a0=a0_h, cla=cla_h, cda=0.05, alpha_stall=stall_h,
                 area=G["S_h"], cp=(X_AC_H, 0, Z_TAIL_REL), forward=(1, 0, 0),
                 upward=(0, 0, 1), comment="horizontal tail, NACA 0009, fixed"),
        liftdrag("base_link", a0=0.0, cla=cla_v, cda=0.05, alpha_stall=stall_h,
                 area=sv_each, cp=(X_AC_H, Y_FIN, Z_TAIL_REL + 0.09), forward=(1, 0, 0),
                 upward=(0, 1, 0), comment="left fin, NACA 0009"),
        liftdrag("base_link", a0=0.0, cla=cla_v, cda=0.05, alpha_stall=stall_h,
                 area=sv_each, cp=(X_AC_H, -Y_FIN, Z_TAIL_REL + 0.09), forward=(1, 0, 0),
                 upward=(0, 1, 0), comment="right fin, NACA 0009"),
    ])

    # --- rotors -------------------------------------------------------------
    links, props, forces, controls = [], [], [], []
    for ch, (name, pos, spin) in enumerate(ROTORS, start=4):
        links.append(rotor_link(name, pos, "z", "0.2 0.4 1.0" if spin > 0 else "0.1 0.8 0.3",
                                rp=yaw_tilt_rpy(pos, spin)))
        for cpx in (0.084, -0.084):
            fwd = (0, spin * (1 if cpx > 0 else -1), 0)
            props.append(liftdrag(name, a0=0.3, cla=4.25, cda=0.10, alpha_stall=1.4,
                                  area=0.002, cp=(cpx, 0, 0), forward=fwd,
                                  upward=(0, 0, 1), comment=f"{name} blade (iris)"))
        forces.append(name + "_joint")
        controls.append(control(ch, name + "_joint", multiplier=838 * spin, offset=0,
                                kind="VELOCITY", p_gain=0.20, cmd_min=-2.5, cmd_max=2.5,
                                comment=f"SERVO{ch + 1} Motor{ch - 3} {name}",
                                slowdown=True))

    links.append(rotor_link("pusher", PUSHER_POS, "x", "0.9 0.9 0.2"))
    for cpz in (0.074, -0.074):
        props.append(liftdrag("pusher", a0=0.3, cla=4.25, cda=0.10, alpha_stall=1.4,
                              area=0.012, cp=(0, 0, cpz),
                              forward=(0, -1 if cpz > 0 else 1, 0), upward=(1, 0, 0),
                              comment="pusher blade (zephyr-derived)"))
    forces.append("pusher_joint")
    # cmd_min < 0 lets the speed controller BRAKE the prop: with cmd_min 0 it
    # could only push, so after cruise the pusher kept coasting/windmilling
    # through every VTOL hover although ArduPilot commanded it off
    controls.append(control(2, "pusher_joint", multiplier=838, offset=0, kind="VELOCITY",
                            p_gain=0.20, cmd_min=-2.5, cmd_max=2.5,
                            comment="SERVO3 Throttle -> pusher"))

    links += [elevon_link("left", +1), elevon_link("right", -1)]
    forces += ["elevon_left_joint", "elevon_right_joint"]
    controls += [
        control(0, "elevon_left_joint", multiplier=1.048, offset=-0.5, kind="POSITION",
                p_gain=10.0, cmd_min=-2.5, cmd_max=2.5, comment="SERVO1 Elevon Left (77)"),
        control(1, "elevon_right_joint", multiplier=1.048, offset=-0.5, kind="POSITION",
                p_gain=10.0, cmd_min=-2.5, cmd_max=2.5, comment="SERVO2 Elevon Right (78)"),
    ]

    feet = "".join(f"""
      <collision name="foot_{i}">
        <pose>{x} {y} {GROUND_Z + 0.01} 0 0 0</pose>
        <geometry><sphere><radius>0.01</radius></sphere></geometry>
        <surface><friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction></surface>
      </collision>""" for i, (x, y) in enumerate(FEET))

    apply_force = "".join(f"""
    <plugin filename="gz-sim-apply-joint-force-system" name="gz::sim::systems::ApplyJointForce">
      <joint_name>{j}</joint_name>
    </plugin>""" for j in forces)

    return f"""<?xml version="1.0"?>
<!-- GENERATED by gen_sdf.py -- edit that, not this file. -->
<sdf version="1.9">
  <model name="coconut_quadplane">
    <pose>0 0 {-GROUND_Z + 0.01:.3f} 0 0 0</pose>
    <link name="base_link">
      {inertial(round(body_mass, 3), IXX, IYY, IZZ)}
      <visual name="airframe">
        <pose>{X_CG / 1000:.4f} 0 {-Z_CG / 1000:.4f} 0 0 3.14159265</pose>
        <geometry><mesh><uri>model://coconut_quadplane/meshes/coconut_quadplane.stl</uri>
          <scale>0.001 0.001 0.001</scale></mesh></geometry>
        <material><ambient>0.85 0.85 0.88 1</ambient><diffuse>0.85 0.85 0.88 1</diffuse>
          <specular>0.3 0.3 0.3 1</specular></material>
      </visual>
      <collision name="body">
        <geometry><box><size>0.5 0.2 0.18</size></box></geometry>
      </collision>{feet}
    </link>

    <link name="imu_link">
      {inertial(0.15, 0.00001, 0.00002, 0.00002)}
      <sensor name="imu_sensor" type="imu">
        <gz_frame_id>imu_link</gz_frame_id>
        <pose degrees="true">0 0 0 180 0 0</pose>
        <always_on>1</always_on>
        <update_rate>1000.0</update_rate>
      </sensor>
    </link>
    <joint name="imu_joint" type="revolute">
      <child>imu_link</child>
      <parent>base_link</parent>
      <axis><xyz>0 0 1</xyz><limit><lower>0</lower><upper>0</upper><effort>0</effort>
        <velocity>0</velocity></limit><dynamics><damping>1.0</damping></dynamics></axis>
    </joint>
{''.join(links)}

    <plugin filename="gz-sim-joint-state-publisher-system"
      name="gz::sim::systems::JointStatePublisher"/>
{aero}
{''.join(props)}
{apply_force}

    <plugin name="ArduPilotPlugin" filename="ArduPilotPlugin">
      <fdm_addr>127.0.0.1</fdm_addr>
      <fdm_port_in>9002</fdm_port_in>
      <connectionTimeoutMaxCount>5</connectionTimeoutMaxCount>
      <lock_step>1</lock_step>
      <no_time_sync>1</no_time_sync>
      <have_32_channels>0</have_32_channels>
      <modelXYZToAirplaneXForwardZDown degrees="true">0 0 0 180 0 0</modelXYZToAirplaneXForwardZDown>
      <gazeboXYZToNED degrees="true">0 0 0 180 0 90</gazeboXYZToNED>
      <imuName>imu_link::imu_sensor</imuName>
{''.join(controls)}
    </plugin>
  </model>
</sdf>
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "model.sdf").write_text(build())
    (OUT / "model.config").write_text("""<?xml version="1.0"?>
<model>
  <name>coconut_quadplane</name>
  <version>1.0</version>
  <sdf version="1.9">model.sdf</sdf>
  <description>CoconutQuadplane VTOL (4 lift + 1 pusher, 2 elevons) for ArduPilot SITL.
  Generated by flight_software/gazebo/gen_sdf.py.</description>
</model>
""")
    print(f"wrote {OUT / 'model.sdf'}")


if __name__ == "__main__":
    main()
