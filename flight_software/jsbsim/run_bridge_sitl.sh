#!/bin/bash
# Start the JSBSim bridge + ArduPilot SITL (JSON backend) for manual flying.
# Run inside WSL:  bash run_bridge_sitl.sh
# Then connect a GCS (MAVProxy / Mission Planner) to tcp:127.0.0.1:5760.
set -u
H="$(cd "$(dirname "$0")" && pwd)"
AP=~/ardupilot
PARAM="$H/../coconut_quadplane.param"
source ~/venv-ardupilot/bin/activate

pkill -x arduplane 2>/dev/null; sleep 1

echo "[run] JSBSim bridge on UDP 9002 ..."
python -u "$H/jsbsim_bridge.py" --root "$H" --model CoconutQuadplane --rate 400 \
    > "$H/bridge.log" 2>&1 &
BRIDGE=$!
sleep 2

echo "[run] arduplane --model JSON (real JSBSim physics) ..."
cd ~/sitlrun
"$AP/build/sitl/bin/arduplane" --model JSON:127.0.0.1 \
    --defaults "$PARAM" -w \
    --home -35.363261,149.165237,584,0 -I0 \
    > "$H/sitl.log" 2>&1 &
SITL=$!

trap "kill $BRIDGE $SITL 2>/dev/null; pkill -x arduplane 2>/dev/null" EXIT INT TERM
echo "[run] bridge=$BRIDGE sitl=$SITL   MAVLink on tcp:5760   (Ctrl-C to stop)"
echo "[run] tail -f $H/bridge.log   for the physics state"
wait
