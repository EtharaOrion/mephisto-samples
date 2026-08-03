#!/bin/bash
set -e
cp /solution/leverage_trajectory_reference.py /home/workspace/leverage_trajectory_reference.py
if [ -f /solution/reference_state.json ]; then cp /solution/reference_state.json /home/workspace/reference_state.json; fi
if [ -f /solution/requirements.txt ]; then cp /solution/requirements.txt /home/workspace/requirements.txt; pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -10 || true; fi
cd /home/workspace
python3 /home/workspace/leverage_trajectory_reference.py \
    --input-dir /home/workspace/scoring/dataset \
    --output    /home/workspace/trajectory_results.json
echo "Oracle: reference leverage_trajectory_reference.py placed at /home/workspace/"
