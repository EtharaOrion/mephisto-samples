#!/bin/bash
set +e
mkdir -p /logs/verifier /home/workspace

for f in /logs/artifacts/*; do
  [ -f "$f" ] || continue
  cp "$f" "/home/workspace/$(basename "$f")"
done

if [ -f /home/workspace/requirements.txt ]; then
  pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -20 || true
fi

cd /home/workspace

python3 /home/workspace/scoring/judge.py \
  --submission-dir /home/workspace \
  --truth-csv /home/workspace/scoring/dataset/cot_graded_truth.csv \
  --calendar-csv /home/workspace/scoring/dataset/macro_calendar.csv \
  --output /logs/verifier/reward.json \
  2>&1 | tee /logs/verifier/scoring_stdout.log

if [ -f /logs/verifier/reward.json ]; then
  SCORE_NORM=$(python3 -c "import json; d=json.load(open('/logs/verifier/reward.json')); print(round(d['score']/100.0, 6))")
  echo "$SCORE_NORM" > /logs/verifier/reward.txt
  chmod 644 /logs/verifier/reward.txt
  echo "Harbor reward written: normalized=$SCORE_NORM"
else
  echo 0 > /logs/verifier/reward.txt
  echo "ERROR: judge produced no reward.json" >&2
  exit 1
fi
