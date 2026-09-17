#!/usr/bin/env python3
"""Render the architecture, data-flow and use-case diagrams with Graphviz
(clean automatic layout). Gantt stays in make_figures.py. Output -> figs/."""
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "figs"
OUT.mkdir(exist_ok=True)

FONT = "Helvetica"
COMMON = f'''
  graph [fontname="{FONT}", fontsize=13];
  node  [fontname="{FONT}", fontsize=13];
  edge  [fontname="{FONT}", fontsize=11];
'''

# --------------------------------------------------------- Fig 2 architecture
ARCH = f'''digraph arch {{
  rankdir=TB;
  bgcolor="white";
  nodesep=0.35; ranksep=0.55;
  {COMMON}
  node [shape=box, style="rounded,filled", margin="0.14,0.09"];

  subgraph cluster_air {{
    label="AERIAL LAYER  —  autonomous quadplane";
    labeljust="l"; fontsize=12; color="#9fb8e0"; style="filled"; fillcolor="#eef3fc";
    node [fillcolor="#dbe7fb"];
    tof      [label="VL53L1X ToF sensor\\naltitude / obstacle ranging"];
    fc       [label="ArduPilot QuadPlane firmware\\nBrahma F4 MK-III flight controller\\nflies uploaded MAVLink missions"];
    cam      [label="RGB camera\\n(ESP32-CAM class)"];
    airframe [label="Quadplane airframe\\n1.3 m wing · 4 lift + 1 forward\\nmotor · 2 elevons"];
    sd       [label="Onboard storage\\nimagery + telemetry log"];
    {{ rank=same; airframe; fc; cam; tof; }}
    fc -> airframe [label="servo PWM", dir=both];
    tof -> fc [label="range"];
    fc -> cam [label="capture", style=dashed];
    cam -> sd [style=dashed];
    fc -> sd [label="telemetry", style=dashed];
  }}

  subgraph cluster_gnd {{
    label="GROUND LAYER  —  laptop (processing after landing)";
    labeljust="l"; fontsize=12; color="#e6c88a"; style="filled"; fillcolor="#fff6e6";
    node [fillcolor="#ffe9c2"];
    ingest [label="Image + telemetry\\ningest"];
    yolo   [label="YOLO detection\\ndisease & pest symptoms\\n(+ frond-health model)"];
    db     [label="Per-tree data store\\nSQLite — status, confidence,\\nlast visit, active / cleared", shape=cylinder];
    planner[label="Route planner\\nvisiting order + dynamic\\npruning → MAVLink mission"];
    gcs    [label="Ground-station link\\npymavlink / MAVLink"];
    dash   [label="Dashboard\\nLeaflet map · battery ·\\nmission time · detections"];
    ingest -> yolo -> db;
    db -> planner -> gcs;
    db -> dash [constraint=false];
    {{ rank=same; ingest; yolo; db; }}
    {{ rank=same; planner; gcs; dash; }}
  }}

  sd  -> ingest [label="  offload after landing", penwidth=1.5, minlen=2];
  gcs -> fc     [label="  upload next mission", penwidth=1.5, color="#1f6feb", fontcolor="#1f6feb", constraint=false];
}}
'''

# --------------------------------------------------------------- Fig 3 DFD L1
DFD = f'''digraph dfd {{
  rankdir=LR;
  bgcolor="white";
  nodesep=0.45; ranksep=0.85;
  {COMMON}
  node [shape=box, style=filled, fillcolor="#eef1f4", fontsize=15];
  op   [label="Operator"];
  env  [label="Coconut\\nplantation"];
  fc   [label="ArduPilot\\nflight\\ncontroller"];

  node [shape=circle, style=filled, fillcolor="#dbe7fb", width=1.45, fixedsize=true, fontsize=14];
  p1 [label="1.0\\nPlan /\\nprune route"];
  p2 [label="2.0\\nCapture\\nimagery"];
  p3 [label="3.0\\nDetect\\ndisease /\\npest symptoms"];
  p4 [label="4.0\\nUpdate\\ntree status"];
  p5 [label="5.0\\nRender\\ndashboard"];

  node [shape=box, style=filled, fillcolor="#ffe9c2", fixedsize=false, fontsize=14];
  d1 [label="D1  Per-tree status (SQLite)"];
  d2 [label="D2  Flight imagery store"];

  {{ rank=same; p1; p2; }}
  {{ rank=same; d1; d2; }}
  {{ rank=same; p3; p4; }}

  op  -> p1 [label="survey area"];
  d1  -> p1 [label="active\\nwaypoints"];
  p1  -> fc [label="waypoint\\nmission"];
  fc  -> p2 [label="position /\\ntrigger"];
  env -> p2 [label="palm\\nimagery"];
  p2  -> d2 [label="raw frames"];
  d2  -> p3 [label="images"];
  p3  -> p4 [label="detections"];
  p4  -> d1 [label="confidence,\\ncleared flag"];
  d1  -> p5 [label="tree status"];
  fc  -> p5 [label="telemetry", style=dashed];
  p5  -> op [label="map / KPIs"];
}}
'''

# ------------------------------------------------------------- Fig 4 use case
UC = f'''digraph uc {{
  rankdir=LR;
  bgcolor="white";
  ranksep=0.9; nodesep=0.35; margin="0.3";
  {COMMON}
  node [shape=box, style=filled, fillcolor="#eef1f4", width=1.3];
  operator [label="Operator"];
  fcx      [label="ArduPilot\\nflight controller"];

  subgraph cluster_sys {{
    label="Coconut-plantation surveillance quadplane";
    labeljust="c"; fontsize=12; style="rounded,filled"; fillcolor="#fbfcfd"; color="#9aa4ad";
    margin=16;
    node [shape=ellipse, style=filled, fillcolor="#dbe7fb", width=2.9,
          fixedsize=false, height=0.9, margin="0.22,0.11"];
    u1 [label="Define survey area"];
    u2 [label="Generate /\\nprune route"];
    u3 [label="Upload mission"];
    u4 [label="Execute\\nautonomous flight"];
    u5 [label="Capture\\npalm imagery"];
    u6 [label="Detect disease\\n& pest symptoms"];
    u7 [label="Review dashboard & tree status"];
    u2 -> u3 [label="«include»", style=dashed, arrowhead=onormal];
    u4 -> u5 [label="«include»", style=dashed, arrowhead=onormal];
    u5 -> u6 [label="«include»", style=dashed, arrowhead=onormal];
  }}

  edge [dir=none];
  operator -> u1; operator -> u2; operator -> u3; operator -> u7;
  fcx -> u4; fcx -> u5;
}}
'''

for name, src in [("architecture", ARCH), ("dfd", DFD), ("usecase", UC)]:
    dot = OUT / f"{name}.dot"
    png = OUT / f"{name}.png"
    dot.write_text(src)
    subprocess.run(["dot", "-Tpng", "-Gdpi=200", str(dot), "-o", str(png)],
                   check=True)
    print(png.name)
print("done")
