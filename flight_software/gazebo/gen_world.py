#!/usr/bin/env python3
"""
gen_world.py -- the 1 ha coconut plantation world, from ../demo/plan.json.

    python gen_world.py [--wind-n 0 --wind-e 0] [--gust 0] [--record DIR]

  * 169 palms (heights from trees.csv), crowns with COLLISION spheres so a
    frond strike shows up as a real contact; target palms carry a red ring
    at their inspection height
  * docking pad at (0, 0), field soil patch, the planned route as a line
  * --wind-n/--wind-e: steady wind (m/s, blowing TOWARDS north/east). Gazebo's
    LiftDrag subtracts the world wind at every lifting surface, so the wing
    and rotors feel it as real relative airflow. --gust adds the WindEffects
    system's random horizontal noise (m/s).
  * --record DIR: three cameras that save frames for MP4s: a chase camera on
    the aircraft, a fixed field overview, and the nose ESP32-CAM view
    (60 deg down) -- the images the disease models would actually get.

World frame is ENU (x = east, y = north), as the ArduPilot plugin expects.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE.parent / "demo" / "plan.json"
OUT = HERE / "worlds" / "coconut_plantation.sdf"


def mat(rgba, emissive=False):
    em = f"<emissive>{rgba}</emissive>" if emissive else ""
    # matte PBR: with ogre2's default the ground mirrored the sky at grazing
    # (chase-camera) angles and read as clouds
    return (f"<material><ambient>{rgba}</ambient><diffuse>{rgba}</diffuse><specular>0 0 0 1</specular>{em}"
            "<pbr><metal><metalness>0</metalness><roughness>1</roughness></metal></pbr></material>")


def palm(t, cr, is_target, hover_h):
    seed = int(t["id"][1:])
    h = t["height"]
    yaw0 = (seed * 53 % 360) * math.pi / 180
    cond = t["condition"]
    frond = "0.62 0.52 0.18 1" if "frond" in cond else "0.13 0.45 0.12 1"
    fronds = "".join(f"""
        <visual name="frond_{k}"><pose>{1.6 * math.cos(yaw0 + k * math.pi / 4):.2f} {1.6 * math.sin(yaw0 + k * math.pi / 4):.2f} {h - 0.6:.2f} 0 0.5 {yaw0 + k * math.pi / 4:.3f}</pose>
          <geometry><box><size>3.6 0.5 0.04</size></box></geometry>{mat(frond)}</visual>""" for k in range(8))
    nuts = (f"""
        <visual name="nuts"><pose>0 0 {h - 1.1:.2f} 0 0 0</pose>
          <geometry><sphere><radius>0.6</radius></sphere></geometry>{mat("0.95 0.55 0.05 1")}</visual>"""
            if "ripe" in cond else f"""
        <visual name="nuts"><pose>0 0 {h - 1.1:.2f} 0 0 0</pose>
          <geometry><sphere><radius>0.45</radius></sphere></geometry>{mat("0.25 0.45 0.12 1")}</visual>""")
    ring = (f"""
        <visual name="stop_ring"><pose>0 0 {hover_h:.2f} 0 0 0</pose>
          <geometry><cylinder><radius>2.5</radius><length>0.05</length></cylinder></geometry>
          {mat("1 0.1 0.1 0.45", True)}<transparency>0.5</transparency></visual>""" if is_target else "")
    return f"""
    <model name="palm_{t['id']}"><static>true</static><pose>{t['e']:.2f} {t['n']:.2f} 0 0 0 0</pose>
      <link name="link">
        <collision name="crown"><pose>0 0 {h - 0.6:.2f} 0 0 0</pose>
          <geometry><sphere><radius>{cr:.2f}</radius></sphere></geometry></collision>
        <collision name="trunk"><pose>0 0 {h / 2:.2f} 0 0 0</pose>
          <geometry><cylinder><radius>0.2</radius><length>{h:.2f}</length></cylinder></geometry></collision>
        <visual name="trunk"><pose>0 0 {h / 2:.2f} 0 0 0</pose>
          <geometry><cylinder><radius>0.18</radius><length>{h:.2f}</length></cylinder></geometry>{mat("0.45 0.35 0.25 1")}</visual>{fronds}{nuts}{ring}
      </link>
    </model>"""


def route_line(pts):
    segs = []
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        L = math.sqrt(dx * dx + dy * dy + dz * dz)
        if L < 0.5:
            continue
        segs.append(f"""
        <visual name="seg_{i}"><cast_shadows>false</cast_shadows>
          <pose>{(a[0] + b[0]) / 2:.2f} {(a[1] + b[1]) / 2:.2f} {(a[2] + b[2]) / 2:.2f} 0 {-math.atan2(dz, math.hypot(dx, dy)):.4f} {math.atan2(dy, dx):.4f}</pose>
          <geometry><box><size>{L:.2f} 0.15 0.15</size></box></geometry>{mat("1 0.85 0.1 0.7", True)}</visual>""")
    return f'<model name="planned_route"><static>true</static><link name="link">{"".join(segs)}</link></model>'


def camera(name, rate, w, h, hfov, save_dir):
    return f"""
        <sensor name="{name}" type="camera">
          <update_rate>{rate}</update_rate><always_on>1</always_on>
          <camera><horizontal_fov>{hfov}</horizontal_fov>
            <image><width>{w}</width><height>{h}</height><format>R8G8B8</format></image>
            <clip><near>0.2</near><far>400</far></clip>
            <save enabled="true"><path>{save_dir}/{name}</path></save></camera>
        </sensor>"""


def build(plan, wind_n, wind_e, gust, record):
    lay, home = plan["layout"], plan["home"]
    cr = lay["crown_radius_m"]
    targets = {it["tree"] for it in plan["mission"] if it["tree"]}
    hover_h = {it["tree"]: it["alt"] for it in plan["mission"] if it["tree"]}
    pts = [(0.0, 0.0, 0.3)] + [(it["e"], it["n"], max(it["alt"], 0.3)) for it in plan["mission"] if it["n"] is not None]
    trees = "".join(palm(t, cr, t["id"] in targets, hover_h.get(t["id"], 0)) for t in plan["trees"])
    fx = lay["field_e0"] + lay["field_m"] / 2
    fy = lay["field_n0"] + lay["field_m"] / 2
    # Gazebo world is ENU (x east): compass heading -> yaw about +z
    dock_yaw = math.radians(90.0 - lay["dock"].get("heading_deg", 90.0))
    sensors_sys = ""
    cams = ""
    model_cams = ""
    if record:
        sensors_sys = '<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>'
        cams = f"""
    <model name="overview_cam"><static>true</static><pose>{fx + 95:.1f} {fy - 115:.1f} 70 0 0.42 2.27</pose>
      <link name="link">{camera("overview", 5, 960, 540, 1.1, record)}</link></model>"""
        model_cams = f"""
    <model name="coconut_quadplane"><pose>0 0 0.11 0 0 {dock_yaw:.4f}</pose>  <!-- on top of the 0.1 m dock pad -->
      <include merge="true"><uri>model://coconut_quadplane</uri></include>
      <!-- 10 mg: a fixed-joint link is lumped into base_link, and at 7.6 m a
           1 g "massless" camera added 0.06 kg m^2 -- doubling pitch/yaw inertia
           in recorded runs only -->
      <link name="chase_link"><pose>-7 0 3.0 0 0.38 0</pose>
        <inertial><mass>0.00001</mass><inertia><ixx>1e-9</ixx><iyy>1e-9</iyy><izz>1e-9</izz></inertia></inertial>
        {camera("chase", 10, 960, 540, 1.3, record)}</link>
      <joint name="chase_joint" type="fixed"><parent>base_link</parent><child>chase_link</child></joint>
      <link name="nosecam_link"><pose>0.30 0 -0.03 0 {math.radians(60):.4f} 0</pose>
        <inertial><mass>0.001</mass><inertia><ixx>1e-6</ixx><iyy>1e-6</iyy><izz>1e-6</izz></inertia></inertial>
        {camera("esp32cam", 2, 800, 600, 1.047, record)}</link>
      <joint name="nosecam_joint" type="fixed"><parent>base_link</parent><child>nosecam_link</child></joint>
    </model>"""
    vehicle = model_cams if record else f"""
    <include><uri>model://coconut_quadplane</uri><pose>0 0 0.345 0 0 {dock_yaw:.4f}</pose></include>"""
    vehicle = vehicle.replace("<include merge", '<include merge') if record else vehicle
    wind = f"""
    <wind><linear_velocity>{wind_e:.2f} {wind_n:.2f} 0</linear_velocity></wind>"""
    wind_sys = ""
    if gust > 0:
        wind_sys = f"""
    <plugin filename="gz-sim-wind-effects-system" name="gz::sim::systems::WindEffects">
      <force_approximation_scaling_factor>0.0</force_approximation_scaling_factor>
      <horizontal><magnitude><time_for_rise>3</time_for_rise>
        <sin><amplitude_percent>0.25</amplitude_percent><period>9</period></sin>
        <noise type="gaussian"><mean>0</mean><stddev>{gust:.2f}</stddev></noise></magnitude>
        <direction><time_for_rise>20</time_for_rise>
        <sin><amplitude>15</amplitude><period>40</period></sin>
        <noise type="gaussian"><mean>0</mean><stddev>4</stddev></noise></direction></horizontal>
      <vertical><noise type="gaussian"><mean>0</mean><stddev>{gust * 0.3:.2f}</stddev></noise></vertical>
    </plugin>"""
    return f"""<?xml version="1.0"?>
<!-- GENERATED by gen_world.py from demo/plan.json -- regenerate, don't edit. -->
<sdf version="1.9">
  <world name="coconut_plantation">
    <physics name="1ms" type="ignore"><max_step_size>0.001</max_step_size><real_time_factor>-1.0</real_time_factor></physics>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>
    <plugin filename="gz-sim-navsat-system" name="gz::sim::systems::NavSat"/>
    <plugin filename="gz-sim-contact-system" name="gz::sim::systems::Contact"/>
    <plugin filename="gz-sim-apply-link-wrench-system" name="gz::sim::systems::ApplyLinkWrench"/>
    {sensors_sys}{wind_sys}{wind}
    <scene><ambient>0.9 0.9 0.9</ambient><background>0.62 0.78 0.95</background><sky></sky><shadows>true</shadows></scene>
    <spherical_coordinates><latitude_deg>{home['lat']}</latitude_deg><longitude_deg>{home['lon']}</longitude_deg>
      <elevation>300</elevation><heading_deg>0</heading_deg><surface_model>EARTH_WGS84</surface_model></spherical_coordinates>
    <light type="directional" name="sun"><cast_shadows>true</cast_shadows><pose>0 0 100 0 0 0</pose>
      <diffuse>0.9 0.9 0.85 1</diffuse><specular>0.3 0.3 0.3 1</specular><direction>-0.4 0.3 -0.85</direction></light>
    <model name="ground"><static>true</static><link name="link">
      <collision name="c"><geometry><plane><normal>0 0 1</normal><size>2000 2000</size></plane></geometry>
        <surface><friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction></surface></collision>
      <visual name="grass"><geometry><plane><normal>0 0 1</normal><size>2000 2000</size></plane></geometry>{mat("0.42 0.55 0.25 1")}</visual>
      <visual name="field"><pose>{fx:.1f} {fy:.1f} 0.01 0 0 0</pose><geometry><box><size>{lay['field_m']} {lay['field_m']} 0.01</size></box></geometry>{mat("0.50 0.42 0.28 1")}</visual>
      <sensor name="navsat_sensor" type="navsat"><always_on>1</always_on><update_rate>1</update_rate></sensor>
    </link></model>
    <model name="dock"><static>true</static><link name="link">
      <collision name="c"><pose>0 0 0.05 0 0 0</pose><geometry><box><size>1.6 1.6 0.1</size></box></geometry></collision>
      <visual name="pad"><pose>0 0 0.05 0 0 0</pose><geometry><box><size>1.6 1.6 0.1</size></box></geometry>{mat("0.25 0.25 0.28 1")}</visual>
      <visual name="h"><pose>0 0 0.11 0 0 0</pose><geometry><box><size>0.15 0.9 0.01</size></box></geometry>{mat("1 1 1 1")}</visual>
    </link></model>
    {route_line(pts)}
    {trees}
    {cams}
    {vehicle}
  </world>
</sdf>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wind-n", type=float, default=0.0)
    ap.add_argument("--wind-e", type=float, default=0.0)
    ap.add_argument("--gust", type=float, default=0.0)
    ap.add_argument("--record", default="")
    a = ap.parse_args()
    plan = json.loads(PLAN.read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(plan, a.wind_n, a.wind_e, a.gust, a.record))
    print(f"wrote {OUT} ({len(plan['trees'])} palms, wind n/e {a.wind_n}/{a.wind_e}, gust {a.gust}, "
          f"record {'on' if a.record else 'off'})")


if __name__ == "__main__":
    main()
