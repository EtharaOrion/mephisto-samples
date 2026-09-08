#!/bin/bash
set +e
mkdir -p /logs/verifier /home/workspace/submission
if [ -d /logs/artifacts/submission ]; then
  cp -r /logs/artifacts/submission/* /home/workspace/submission/ 2>/dev/null
fi
python3 /home/workspace/scoring/score.py 2>/tmp/stderr.log >/tmp/stdout.log
score_line=$(grep -E '^TOTAL_SCORE ' /tmp/stdout.log | tail -1)
if [ -z "$score_line" ]; then
  echo "0.000000" > /logs/verifier/reward.txt
  cat /tmp/stderr.log 1>&2
  exit 1
fi
raw=$(echo "$score_line" | awk '{print $2}')
python3 -c "v=float('$raw'); print(f'{max(0.0,min(1.0,v/100.0)):.6f}')" > /logs/verifier/reward.txt
echo "reward $(cat /logs/verifier/reward.txt)"
tail -n 200 /tmp/stderr.log 1>&2
exit 0
