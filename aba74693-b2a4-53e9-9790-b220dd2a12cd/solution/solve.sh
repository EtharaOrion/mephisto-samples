#!/bin/bash
set -e
cp /solution/auction_bidding_reference.py /home/workspace/auction_bidding.py
if [ -f /solution/reference_state.json ]; then
  cp /solution/reference_state.json /home/workspace/reference_state.json
fi
if [ -f /solution/requirements.txt ]; then
  cp /solution/requirements.txt /home/workspace/requirements.txt
  pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -10 || true
fi
cd /home/workspace
python3 /home/workspace/auction_bidding.py \
    --backtest \
    --data /home/workspace/scoring/auction_history_test.csv \
    --macro /home/workspace/scoring/macro_indicators_test.csv \
    --auctions /home/workspace/scoring/test_auctions.json \
    --state /home/workspace/reference_state.json \
    --output /home/workspace/bidding_results.json
echo "Oracle: reference auction_bidding.py + reference_state.json placed at /home/workspace/"
