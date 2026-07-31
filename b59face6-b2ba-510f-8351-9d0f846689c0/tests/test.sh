#!/bin/bash
# Harbor verifier adapter for treasury_curve_positioning_book.
# Bridges Harbor's artifact-delivery convention (agent submits land at
# /logs/artifacts/) into the eval_script.py contract (submission expected at
# /home/workspace/), then translates eval output into /logs/verifier/reward.txt.
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
python3 /home/workspace/scoring/eval_script.py 2>&1 | tee /logs/verifier/scoring_stdout.log

SCORE=$(grep -oE "TOTAL_SCORE\s+-?[0-9]+(\.[0-9]+)?" /logs/verifier/scoring_stdout.log | tail -1 | awk '{print $2}')
if [ -z "$SCORE" ]; then
  SCORE=$(grep -oE "Final total score:\s*-?[0-9]+(\.[0-9]+)?" /logs/verifier/scoring_stdout.log | tail -1 | grep -oE "\-?[0-9]+(\.[0-9]+)?$")
fi
if [ -z "$SCORE" ]; then
  echo "ERROR: could not extract score from stdout" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi

SCORE_NORM=$(python3 -c "print(round(float('$SCORE') / 110.0, 6))")
echo "$SCORE_NORM" > /logs/verifier/reward.txt
chmod 644 /logs/verifier/reward.txt
echo "Harbor reward written: raw=$SCORE normalized=$SCORE_NORM"
