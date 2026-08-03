#!/bin/bash
set -e
cp /solution/fed_funds_positioning_reference.py /home/workspace/fed_funds_positioning.py
if [ -f /solution/reference_state.json ]; then
  cp /solution/reference_state.json /home/workspace/reference_state.json
fi
if [ -f /solution/requirements.txt ]; then
  cp /solution/requirements.txt /home/workspace/requirements.txt
  pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -10 || true
fi
mkdir -p /home/workspace/input
cp /home/workspace/scoring/fed_funds_test.csv                 /home/workspace/input/
cp /home/workspace/scoring/rates_test.csv                     /home/workspace/input/
cp /home/workspace/scoring/macro_test.csv                     /home/workspace/input/
cp /home/workspace/scoring/fomc_meetings_test_2025_2026.csv   /home/workspace/input/
cp /home/workspace/scoring/test_windows_schedule.json         /home/workspace/input/
cd /home/workspace
python3 /home/workspace/fed_funds_positioning.py \
    --backtest \
    /home/workspace/input \
    /home/workspace/reference_state.json \
    /home/workspace/positioning_results.json
echo "Oracle: reference fed_funds_positioning.py + reference_state.json placed at /home/workspace/"
