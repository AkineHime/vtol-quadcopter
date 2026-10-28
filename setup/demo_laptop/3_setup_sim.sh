#!/usr/bin/env bash
# Coconut VTOL: ArduPilot SITL + JSBSim inside WSL Ubuntu 24.04, the same
# versions the demo flights were flown on. Run through SETUP-3-simulator.cmd,
# or inside Ubuntu:  bash 3_setup_sim.sh /mnt/c/coconut/vtol-quadcopter
# Takes 1-2 h, mostly downloads and compiling; asks for the Ubuntu password once.
# Safe to run again: finished steps are skipped.
set -eo pipefail
REPO="${1:?usage: 3_setup_sim.sh /mnt/c/coconut/vtol-quadcopter}"
AP_URL=https://github.com/ArduPilot/ardupilot.git
AP_COMMIT=8ab6afde107a91df1b5f60ade8f333cb8a61b190      # ArduPilot master of 2026-10-16
AP=~/ardupilot
VENV=~/venv-ardupilot
step() { printf '\n== %s  (%s)\n' "$*" "$(date +%H:%M)"; }
[ -f "$REPO/flight_software/sim_runner.py" ] || { echo "no repo at $REPO: run SETUP-1-dashboard.cmd first"; exit 1; }
t0=$(date +%s)

step "1/5  Ubuntu packages"
sudo apt-get update -qq
sudo apt-get install -y -qq git python3-venv python3-pip

step "2/5  ArduPilot source (pinned commit ${AP_COMMIT:0:7})"
if [ ! -f "$AP/waf" ]; then
  rm -rf "$AP"
  git init -q "$AP"
  git -C "$AP" remote add origin "$AP_URL"
  if ! git -C "$AP" fetch --depth 1 origin "$AP_COMMIT"; then
    echo "  pinned commit not fetchable: using the latest master instead"
    git -C "$AP" fetch --depth 1 origin master
  fi
  git -C "$AP" checkout -q FETCH_HEAD
fi
git -C "$AP" submodule update --init --recursive --depth 1 --jobs 4

step "3/5  ArduPilot build prerequisites (the long download)"
if [ ! -f ~/.coconut_prereqs_done ]; then
  (cd "$AP" && Tools/environment_install/install-prereqs-ubuntu.sh -y)
  touch ~/.coconut_prereqs_done
fi
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
export PATH="$HOME/.local/bin:$AP/Tools/autotest:$PATH"

step "4/5  Build ArduPlane SITL (the long compile)"
cd "$AP"
if [ ! -x build/sitl/bin/arduplane ]; then
  python3 waf configure --board sitl
  python3 waf plane
fi

step "5/5  Simulator Python packages + a 1-minute hover test"
pip install --quiet jsbsim==1.3.3 pymavlink==2.4.50 matplotlib numpy MAVProxy empy==3.3.4 pexpect future lxml dronecan
cd "$REPO/flight_software"
if python sim_runner.py setup_check --physics jsbsim --test hover --timeout 300 > ~/setup_check.log 2>&1; then
  tail -1 ~/setup_check.log | cut -c1-300
  ok=1
else
  ok=0
fi
rm -rf "$REPO/flight_software/demo/runs/setup_check"
git -C "$REPO" checkout -q -- flight_software/demo/plan.json flight_software/demo/mission.waypoints 2>/dev/null || true

mins=$(( ($(date +%s) - t0) / 60 ))
if [ "$ok" = 1 ] && grep -q 'mission exit 0' ~/setup_check.log; then
  printf '\nSimulator ready (%s min). Fly the dashboard plan with RUN-demo-with-sim.cmd\n' "$mins"
else
  printf '\nThe hover test did not finish: see ~/setup_check.log and ~/simruns/setup_check/*.log\n'
  exit 1
fi
