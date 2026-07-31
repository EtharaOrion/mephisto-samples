#!/bin/bash
set -e
cp /solution/bank_capital_projection_reference.py /home/workspace/bank_capital_projection.py
if [ -f /solution/reference_state.json ]; then
  cp /solution/reference_state.json /home/workspace/reference_state.json
fi
if [ -f /solution/requirements.txt ]; then
  cp /solution/requirements.txt /home/workspace/requirements.txt
  pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -10 || true
fi
cd /home/workspace
python3 /home/workspace/bank_capital_projection.py \
    --backtest \
    --data /home/workspace/scoring/financials_test.csv \
    --macro /home/workspace/scoring/macro_indicators_test.csv \
    --institutions /home/workspace/scoring/test_institutions.json \
    --state /home/workspace/reference_state.json \
    --output /home/workspace/projection_results.json
echo "Oracle: reference bank_capital_projection.py + reference_state.json placed at /home/workspace/"
