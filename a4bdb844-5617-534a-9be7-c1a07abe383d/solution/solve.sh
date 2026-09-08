#!/bin/bash
set -e
cp /solution/cpi_nowcast_reference.py /home/workspace/cpi_nowcast_book.py
if [ -f /solution/reference_state.json ]; then
  cp /solution/reference_state.json /home/workspace/reference_state.json
fi
if [ -f /solution/requirements.txt ]; then
  cp /solution/requirements.txt /home/workspace/requirements.txt
  pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -10 || true
fi
cd /home/workspace
python3 /home/workspace/cpi_nowcast_book.py \
    --backtest \
    --data /home/workspace/scoring/cpi_test.csv \
    --macro /home/workspace/scoring/macro_test.csv \
    --rates /home/workspace/scoring/rates_test.csv \
    --prints /home/workspace/scoring/test_prints.json \
    --state /home/workspace/reference_state.json \
    --output /home/workspace/nowcast_results.json
echo "Oracle: reference cpi_nowcast_book.py + reference_state.json placed at /home/workspace/"
