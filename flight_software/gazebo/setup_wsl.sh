#!/usr/bin/env bash
# One-shot environment setup for the Gazebo + ArduPilot demo, inside WSL2
# Ubuntu 24.04. Safe to re-run: every step skips what is already done.
#
#   bash flight_software/gazebo/setup_wsl.sh      (from the repo, inside WSL)
#
# Installs: build tools, Gazebo Harmonic, ArduPilot (SITL build of ArduPlane)
# at ~/ardupilot, the ardupilot_gazebo plugin at ~/ardupilot_gazebo, and the
# Python venv ~/venv-ardupilot (pymavlink, matplotlib, numpy, gmsh, cadquery),
# plus ffmpeg for the recorded-run videos.
set -euo pipefail
REPO_GZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"     # this folder, found before any cd

log() { printf '\n=== %s ===\n' "$*"; }

log "base packages"
sudo apt-get update
sudo apt-get install -y git curl lsb-release gnupg cmake build-essential \
    python3-venv python3-pip mesa-utils rapidjson-dev libopencv-dev \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl ffmpeg

log "Gazebo Harmonic"
if ! command -v gz >/dev/null; then
    sudo curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
        -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
        | sudo tee /etc/apt/sources.list.d/gazebo-stable.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y gz-harmonic
fi
sudo apt-get install -y libgz-sim8-dev

log "ArduPilot"
if [ ! -d ~/ardupilot ]; then
    git clone --depth 1 --recurse-submodules --shallow-submodules \
        https://github.com/ArduPilot/ardupilot.git ~/ardupilot
fi
cd ~/ardupilot
# marker file, not the venv: the venv appears early in install-prereqs, so an
# interrupted run would otherwise be mistaken for a finished one
if [ ! -f ~/.ardupilot-prereqs-done ]; then
    USER="${USER:-$(whoami)}" Tools/environment_install/install-prereqs-ubuntu.sh -y
    touch ~/.ardupilot-prereqs-done
fi
# shellcheck disable=SC1090
source ~/venv-ardupilot/bin/activate
pip install --upgrade pymavlink matplotlib numpy gmsh "cadquery==2.8.0"  # cadquery: airframe/build_airframe.py
if [ ! -x build/sitl/bin/arduplane ]; then
    python3 waf configure --board sitl
    python3 waf plane
fi

log "ardupilot_gazebo plugin"
if [ ! -d ~/ardupilot_gazebo ]; then
    git clone https://github.com/ArduPilot/ardupilot_gazebo ~/ardupilot_gazebo
fi
cd ~/ardupilot_gazebo
mkdir -p build && cd build
GZ_VERSION=harmonic cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j"$(nproc)"

log "shell environment"
if ! grep -q "coconut-gazebo-env" ~/.bashrc; then
    cat >> ~/.bashrc <<EOF

# >>> coconut-gazebo-env >>>
export GZ_VERSION=harmonic
export GZ_SIM_SYSTEM_PLUGIN_PATH=\$HOME/ardupilot_gazebo/build:\${GZ_SIM_SYSTEM_PLUGIN_PATH:-}
export GZ_SIM_RESOURCE_PATH=$REPO_GZ/models:$REPO_GZ/worlds:\$HOME/ardupilot_gazebo/models:\$HOME/ardupilot_gazebo/worlds:\${GZ_SIM_RESOURCE_PATH:-}
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
export PATH=\$HOME/ardupilot/Tools/autotest:\$PATH
# <<< coconut-gazebo-env <<<
EOF
fi

log "done"
gz sim --versions || true
ls -l ~/ardupilot/build/sitl/bin/arduplane
ls ~/ardupilot_gazebo/build/*.so
