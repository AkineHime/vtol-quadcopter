#!/usr/bin/env bash
# One-command visual demo: Gazebo plantation world + ArduPilot QuadPlane SITL
# + route planner flying the inspection mission. Default: the recommended
# operation -- fixed-wing scout sweep of the 1 ha block, then VTOL confirm
# stops at 4 flagged palms, land on the dock. Override with PLAN_ARGS, e.g.
#   PLAN_ARGS="--strategy fw_sweep" bash run_demo.sh
#
#   bash run_demo.sh              # live, Gazebo GUI with chase camera
#   bash run_demo.sh --record     # also write a Gazebo state log to ../demo/gz_log
#                                 # (WARNING: ~1 GB per run -- for a review-day
#                                 # backup prefer a screen recording, Win+Alt+R)
#   bash run_demo.sh --no-fly     # bring everything up, don't auto-fly
#
# QGroundControl on Windows: add a TCP link to 127.0.0.1:5762 to watch the
# route and live position on a map while this runs.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FS="$(dirname "$HERE")"
RECORD=0
FLY=1
for a in "$@"; do
    case "$a" in
        --record) RECORD=1 ;;
        --no-fly) FLY=0 ;;
    esac
done

export GZ_VERSION=harmonic
export GZ_SIM_SYSTEM_PLUGIN_PATH="$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_RESOURCE_PATH="$HERE/models:$HERE/worlds:$HOME/ardupilot_gazebo/models:${GZ_SIM_RESOURCE_PATH:-}"
# WSLg: without GALLIUM_DRIVER Mesa falls back to llvmpipe (software) rendering
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
# shellcheck disable=SC1090
source ~/venv-ardupilot/bin/activate

LOGDIR="$FS/demo/logs"
mkdir -p "$LOGDIR"
PIDS=()
cleanup() {
    echo "[demo] shutting down"
    for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
    pkill -f "gz sim" 2>/dev/null
    pkill -f arduplane 2>/dev/null
}
trap cleanup EXIT INT TERM

if [ ! -f "$HERE/models/coconut_quadplane/meshes/coconut_quadplane.stl" ]; then
    echo "[demo] building visual mesh from the CAD STEP (one-time)"
    python "$HERE/mesh_from_step.py" >/dev/null || exit 1
fi
python "$HERE/gen_sdf.py" >/dev/null || exit 1

echo "[demo] planning route + generating world"
PLAN_ARGS=${PLAN_ARGS:---strategy hybrid --targets P0005,P0302,P0612,P0911}
python "$FS/route_planner.py" $PLAN_ARGS >/dev/null || exit 1
python "$HERE/gen_world.py" || exit 1
HOME_LL=$(python -c "import json;h=json.load(open('$FS/demo/plan.json'))['home'];print(f\"{h['lat']},{h['lon']}\")")

GZ_ARGS=(-r "$HERE/worlds/coconut_plantation.sdf")
if [ "$RECORD" = 1 ]; then
    rm -rf "$FS/demo/gz_log"
    GZ_ARGS+=(--record --record-path "$FS/demo/gz_log")
fi
echo "[demo] starting Gazebo"
gz sim "${GZ_ARGS[@]}" >"$LOGDIR/gazebo.log" 2>&1 &
PIDS+=($!)

echo "[demo] starting ArduPilot SITL at $HOME_LL"
cd "$LOGDIR" || exit 1
sim_vehicle.py -v ArduPlane -f quadplane --model JSON --no-rebuild --no-mavproxy -w \
    --custom-location="$HOME_LL,300,0" \
    --add-param-file="$FS/coconut_quadplane.param" \
    --add-param-file="$HERE/coconut_gazebo.param" \
    >"$LOGDIR/sitl.log" 2>&1 &
PIDS+=($!)

# chase camera once the GUI is up
(
    for _ in $(seq 60); do
        gz service -l 2>/dev/null | grep -q /gui/follow && break
        sleep 1
    done
    gz service -s /gui/follow --reqtype gz.msgs.StringMsg --reptype gz.msgs.Boolean \
        --timeout 2000 --req 'data: "coconut_quadplane"' >/dev/null 2>&1
    gz service -s /gui/follow/offset --reqtype gz.msgs.Vector3d --reptype gz.msgs.Boolean \
        --timeout 2000 --req 'x: -12, y: 0, z: 6' >/dev/null 2>&1
) &

if [ "$FLY" = 1 ]; then
    sleep 10
    python "$FS/route_planner.py" $PLAN_ARGS --connect tcp:127.0.0.1:5760 --fly \
        2>&1 | tee "$LOGDIR/mission.log"
    echo "[demo] mission finished -- close the Gazebo window or Ctrl+C to exit"
fi
wait
