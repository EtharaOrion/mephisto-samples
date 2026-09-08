#!/bin/bash
set -euo pipefail
cd /home/workspace
python3 /solution/reference_solver.py --train ./attachments /tmp/state.json
python3 /solution/reference_solver.py --backtest ./attachments /tmp/state.json ./positioning_results.json
cp /solution/reference_solver.py ./cftc_positioning.py
cp /home/workspace/attachments/requirements.txt ./requirements.txt 2>/dev/null || echo 'numpy\npandas' > ./requirements.txt
