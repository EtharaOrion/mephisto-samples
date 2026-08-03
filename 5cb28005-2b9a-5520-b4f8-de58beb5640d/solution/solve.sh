#!/bin/bash
set -e
cp /solution/fundamental_momentum_reference.py /home/workspace/fundamental_momentum_reference.py
if [ -f /solution/reference_state.json ]; then cp /solution/reference_state.json /home/workspace/reference_state.json; fi
if [ -f /solution/requirements.txt ]; then cp /solution/requirements.txt /home/workspace/requirements.txt; pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -10 || true; fi
cd /home/workspace
python3 /home/workspace/fundamental_momentum_reference.py \
    --input-dir /home/workspace/scoring/dataset \
    --output    /home/workspace/momentum_results.json
echo "Oracle: reference fundamental_momentum_reference.py placed at /home/workspace/"
