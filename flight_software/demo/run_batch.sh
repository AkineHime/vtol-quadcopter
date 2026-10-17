#!/usr/bin/env bash
# run_batch.sh -- run sim_runner.py scenarios back to back (one sim at a time:
# they share ports and the world file). Usage: bash run_batch.sh "NAME ARGS..." ...
source ~/venv-ardupilot/bin/activate
cd "$(dirname "$0")/.."
for spec in "$@"; do
  set -- $spec
  name=$1; shift
  echo "=== $name $*"
  timeout 3000 python sim_runner.py "$name" "$@" --timeout 1500 > ~/run_"$name".log 2>&1
  tail -1 ~/run_"$name".log
done
