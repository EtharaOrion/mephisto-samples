#!/bin/bash
set -euo pipefail

mkdir -p /logs/verifier /home/workspace/submission

if [ -d /logs/artifacts/submission ]; then
  cp -r /logs/artifacts/submission/. /home/workspace/submission/
fi

cd /home/workspace/submission

if [ -x ./build.sh ]; then
  ./build.sh
fi

mkdir -p /home/workspace/scoring/outputs
mkdir -p /home/workspace/scoring/traces

for inst in /home/workspace/scoring/data/hidden_benchmarks/*.ip.json; do
  id=$(basename "$inst" .ip.json)
  timeout 60s ./solve "$inst" \
    > "/home/workspace/scoring/outputs/${id}.out.json" \
    2> "/home/workspace/scoring/traces/${id}.log" || true
done

if [ -f /home/workspace/submission/l3_ranking.json ]; then
  L3_ARG="--l3-ranking /home/workspace/submission/l3_ranking.json"
else
  L3_ARG=""
fi

python3 /home/workspace/scoring/score.py \
  --instances /home/workspace/scoring/data/hidden_benchmarks \
  --optima /home/workspace/scoring/data/hidden_optima.json \
  --outputs /home/workspace/scoring/outputs \
  --traces /home/workspace/scoring/traces \
  $L3_ARG \
  --reward-out /logs/verifier/reward.json \
  --print-summary

python3 -c "import json; d=json.load(open('/logs/verifier/reward.json')); open('/logs/verifier/reward.txt','w').write(f\"{d['score']/100.0:.6f}\\n\")"
