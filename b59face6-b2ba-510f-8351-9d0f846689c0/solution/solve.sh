#!/bin/bash
# Oracle: reference solver ships in solution/curve_positioning_reference.py.
# Harbor's OracleAgent uploads the entire solution/ dir to /solution/ inside
# the agent container before invoking this script. Copy the reference to the
# submission path eval_script.py expects, then invoke it in --backtest mode
# across all judge-configured test windows.
#
# Real (non-Oracle) evaluation agents never receive the solution/ upload, so
# curve_positioning_reference.py is not visible to them — no answer leak.
set -e
cp /solution/curve_positioning_reference.py /home/workspace/curve_positioning.py
if [ -f /solution/reference_state.json ]; then
  cp /solution/reference_state.json /home/workspace/reference_state.json
fi
if [ -f /solution/requirements.txt ]; then
  cp /solution/requirements.txt /home/workspace/requirements.txt
  pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -10 || true
fi
cd /home/workspace
python3 /home/workspace/curve_positioning.py --backtest --all-windows > /home/workspace/positioning_results.json
echo "Oracle: reference curve_positioning.py + reference_state.json placed at /home/workspace/"
