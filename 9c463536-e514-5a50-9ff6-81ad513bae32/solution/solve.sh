#!/bin/bash
set -e
cp /solution/treasury_liquidity_reference.py /home/workspace/treasury_liquidity.py
if [ -f /solution/reference_state.json ]; then
  cp /solution/reference_state.json /home/workspace/reference_state.json
fi
if [ -f /solution/requirements.txt ]; then
  cp /solution/requirements.txt /home/workspace/requirements.txt
  pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -10 || true
fi
mkdir -p /home/workspace/input
cp /home/workspace/scoring/dataset/*.csv /home/workspace/input/ 2>/dev/null || true
cp /home/workspace/scoring/dataset/test_ladder_dates.json /home/workspace/input/
cd /home/workspace
if [ ! -f /home/workspace/reference_state.json ]; then
  python3 /home/workspace/treasury_liquidity.py --train /home/workspace/input /home/workspace/reference_state.json
fi
python3 /home/workspace/treasury_liquidity.py \
    --backtest \
    /home/workspace/input \
    /home/workspace/reference_state.json \
    /home/workspace/positioning_results.json
echo "Oracle: reference treasury_liquidity.py + reference_state.json placed at /home/workspace/"
