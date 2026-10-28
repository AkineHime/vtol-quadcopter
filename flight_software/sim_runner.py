#!/usr/bin/env python3
"""
sim_runner.py -- one unattended, headless Gazebo + ArduPilot SITL scenario.

    python sim_runner.py NAME --strategy fw_sweep [--wind-n 4 --wind-e 2 --gust 1.5]
                         [--param-file faults.param ...] [--events events.json]
                         [--record] [--fps 3]

Plans the mission, writes the world (wind, cameras), starts a headless Gazebo
server and SITL, flies the mission (injecting --events), then collects:

  demo/runs/NAME/flight.BIN      ArduPilot dataflash log
  demo/runs/NAME/result.json     flight outcome (landed, crashed, wall time)
  demo/runs/NAME/analysis.json   imaging / clearance / energy / transition metrics
  demo/runs/NAME/*.mp4           (--record) chase, overview, nose-camera videos
  demo/runs/NAME/*_sheet.png     (--record) frame contact sheets for review

Nothing is displayed; every process is cleaned up on exit.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GZD = HERE / "gazebo"
JSD = HERE / "jsbsim"
RUNS = HERE / "demo" / "runs"
HOME = Path.home()


def env():
    e = dict(os.environ)
    e.update({
        "GZ_VERSION": "harmonic",
        "GZ_SIM_SYSTEM_PLUGIN_PATH": str(HOME / "ardupilot_gazebo" / "build"),
        "GZ_SIM_RESOURCE_PATH": f"{GZD / 'models'}:{GZD / 'worlds'}:{HOME / 'ardupilot_gazebo' / 'models'}",
        "GALLIUM_DRIVER": "d3d12", "MESA_D3D12_DEFAULT_ADAPTER_NAME": "NVIDIA",
        "PATH": f"{HOME / 'ardupilot' / 'Tools' / 'autotest'}:{e['PATH']}",
    })
    return e


def run(cmd, **kw):
    print("[run]", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], env=env(), **kw)


def kill_all(procs):
    for p in procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:  # noqa: BLE001
            pass
    for sig in ("-TERM", "-KILL"):        # a hung gz server ignores SIGTERM
        for pat in ("arduplane", "gz sim", "camera_keepalive", "jsbsim_bridge"):
            subprocess.run(["pkill", sig, "-f", pat], check=False)
        time.sleep(3)


def encode(out_dir: Path, rec: Path):
    made = []
    for cam_dir in sorted(p for p in rec.glob("*") if p.is_dir()):
        frames = sorted(glob.glob(str(cam_dir / "*.png")),           # gz names them cam_<n>.png
                        key=lambda f: int(re.search(r"_(\d+)\.png$", f).group(1)))
        if len(frames) < 5:
            continue
        lst = cam_dir / "frames.txt"
        lst.write_text("".join(f"file '{f}'\n" for f in frames))
        fps = {"chase": 10, "overview": 4, "esp32cam": 2}.get(cam_dir.name, 5)
        mp4 = out_dir / f"{cam_dir.name}.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-r", fps, "-f", "concat", "-safe", "0", "-i", lst,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", mp4])
        step = max(1, len(frames) // 12)
        sheet = out_dir / f"{cam_dir.name}_sheet.png"
        run(["ffmpeg", "-y", "-loglevel", "error", "-r", fps, "-f", "concat", "-safe", "0", "-i", lst,
             "-vf", f"select='not(mod(n\\,{step}))',scale=480:-1,tile=4x3", "-frames:v", "1", sheet])
        made += [mp4.name, sheet.name]
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--strategy", default="fw_sweep")
    ap.add_argument("--hover-s", type=float, default=3.0)
    ap.add_argument("--targets")
    ap.add_argument("--wind-n", type=float, default=0.0)
    ap.add_argument("--wind-e", type=float, default=0.0)
    ap.add_argument("--gust", type=float, default=0.0)
    ap.add_argument("--param-file", action="append", default=[])
    ap.add_argument("--events")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--fps", type=float, default=5.0)   # ESP32-CAM trigger: 5 fps (3 fps left palms under 2 frames in wind)
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--physics", choices=["gazebo", "jsbsim"], default="gazebo")
    ap.add_argument("--test", choices=["hover", "transition"],
                    help="fly gazebo/flight_test.py instead of the plantation mission")
    a = ap.parse_args()
    if a.physics == "jsbsim" and a.record:
        ap.error("--record needs gazebo cameras; JSBSim runs are rendered in Blender instead")

    out = RUNS / a.name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    work = HOME / "simruns" / a.name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    rec = work / "frames"
    py = sys.executable

    tgt = ["--targets", a.targets] if a.targets else []
    tgt += ["--wind-n", a.wind_n, "--wind-e", a.wind_e]   # forecast = actual mean wind
    run([py, HERE / "route_planner.py", "--strategy", a.strategy, "--hover-s", a.hover_s, *tgt], check=True)
    layout = json.loads((HERE / "demo" / "plan.json").read_text())["layout"]   # dock heading set by the planner
    home = f"{layout['home']['lat']},{layout['home']['lon']},300"
    if a.physics == "gazebo":
        run([py, GZD / "gen_sdf.py"], check=True, stdout=subprocess.DEVNULL)
        wargs = ["--wind-n", a.wind_n, "--wind-e", a.wind_e, "--gust", a.gust]
        if a.record:
            for cam in ("chase", "overview", "esp32cam"):     # gz won't create these itself
                (rec / cam).mkdir(parents=True)
            wargs += ["--record", rec]
        run([py, GZD / "gen_world.py", *wargs], check=True)

    procs = []
    try:
        if a.physics == "gazebo":
            phys = ["gz", "sim", "-s", "-r", GZD / "worlds" / "coconut_plantation.sdf"]
            if a.record:
                phys.insert(3, "--headless-rendering")
        else:
            phys = [py, "-u", JSD / "jsbsim_bridge.py", "--root", JSD, "--model", "CoconutQuadplane",
                    "--rate", "1000", "--home", home, "--heading", layout["dock"].get("heading_deg", 0),
                    "--wind-n", a.wind_n, "--wind-e", a.wind_e, "--gust", a.gust]
        procs.append(subprocess.Popen([str(c) for c in phys], env=env(), cwd=work,
                                      stdout=open(work / "physics.log", "w"), stderr=subprocess.STDOUT,
                                      start_new_session=True))
        if a.record:   # cameras only render with a subscriber; <save> writes the PNGs
            procs.append(subprocess.Popen(["/usr/bin/python3", str(GZD / "camera_keepalive.py")],
                                          env=env(), cwd=work, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.STDOUT, start_new_session=True))
        sv = ["sim_vehicle.py", "-v", "ArduPlane", "-f", "quadplane", "--model", "JSON", "--no-rebuild",
              "--no-mavproxy", "-w", f"--custom-location={layout['home']['lat']},{layout['home']['lon']},300,0",
              f"--add-param-file={HERE / 'coconut_quadplane.param'}",
              f"--add-param-file={(GZD / 'coconut_gazebo.param') if a.physics == 'gazebo' else (JSD / 'coconut_jsbsim.param')}"]
        sv += [f"--add-param-file={Path(p).resolve()}" for p in a.param_file]
        procs.append(subprocess.Popen(sv, env=env(), cwd=work, stdout=open(work / "sitl.log", "w"),
                                      stderr=subprocess.STDOUT, start_new_session=True))
        time.sleep(14)
        cmd = [py, "-u", HERE / "route_planner.py", "--strategy", a.strategy, "--hover-s", a.hover_s,
               "--connect", "tcp:127.0.0.1:5760", "--fly", "--result", out / "result.json", *tgt]
        if a.test:
            cmd = [py, "-u", GZD / "flight_test.py", a.test, "--connect", "tcp:127.0.0.1:5760"]
        if a.events:
            cmd += ["--events", Path(a.events).resolve()]
        with open(out / "mission.log", "w") as ml:
            r = run(cmd, stdout=ml, stderr=subprocess.STDOUT, timeout=a.timeout)
        print(f"[runner] mission exit {r.returncode}")
    except subprocess.TimeoutExpired:
        print("[runner] TIMEOUT")
    finally:
        kill_all(procs)

    logs = sorted(glob.glob(str(work / "logs" / "*.BIN")), key=os.path.getmtime)
    summary = {"name": a.name, "physics": a.physics, "test": a.test, "strategy": a.strategy, "targets": a.targets, "wind_ne": [a.wind_n, a.wind_e], "gust": a.gust,
               "param_files": a.param_file, "events": a.events}
    if logs:
        shutil.copy(logs[-1], out / "flight.BIN")
        sys.path.insert(0, str(HERE))
        import analysis
        res = analysis.analyse(out / "flight.BIN", a.fps)
        (out / "analysis.json").write_text(json.dumps(res, indent=1))
        summary.update({k: res.get(k) for k in (
            "flight_s", "distance_m", "energy_wh", "battery_used_pct", "trees_imaged", "trees_imaged_2plus",
            "targets_imaged_2plus", "target_frames_median",
            "frames_per_tree_median", "frames_total", "min_crown_clearance_m", "max_abs_roll", "max_abs_pitch")})
        summary["lift_events"] = len(res.get("lift_on_off_events_in_flight", []))
    plan = json.loads((HERE / "demo" / "plan.json").read_text())
    summary["n_targets"] = sum(1 for it in plan["mission"] if it.get("tree"))
    shutil.copy(HERE / "demo" / "plan.json", out / "plan.json")
    if (out / "result.json").exists():
        summary["flight"] = json.loads((out / "result.json").read_text())
    if a.record and rec.exists():
        summary["media"] = encode(out, rec)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print("[summary]", json.dumps(summary))


if __name__ == "__main__":
    main()
