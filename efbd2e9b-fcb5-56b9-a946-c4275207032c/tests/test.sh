#!/bin/bash
# Harbor verifier adapter for fdic_community_credit_triage.
# Collects the submitted strategy (from the Harbor artifact tree AND, as a
# fallback, the live workdir - the sforge artifacts-bridge lesson), runs the
# judge-only scorer, and writes the reward contract path with a
# machine-readable reason on every zero path.
set +e
mkdir -p /logs/verifier /home/workspace/strategy

for src in /logs/artifacts /logs/artifacts/strategy; do
  [ -d "$src" ] || continue
  for f in "$src"/policy.py "$src"/book_report.json "$src"/memo.md; do
    [ -f "$f" ] && cp "$f" /home/workspace/strategy/
  done
done

export TRIAGE_WORKSPACE=/home/workspace
python3 /judge/score.py 2>&1 | tee /logs/verifier/scoring_stdout.log

SCORE=$(python3 - <<'PY'
import json, re
txt = open('/logs/verifier/scoring_stdout.log').read()
m = re.search(r'>>>>> Start Structured Result\n(.*?)\n>>>>> End Structured Result',
              txt, re.S)
print(json.loads(m.group(1))['score'] if m else '')
PY
)
if [ -z "$SCORE" ]; then
  echo "ERROR: no structured result emitted (judge crash)" >&2
  echo "reason=judge_no_structured_result" > /logs/verifier/reward_reason.txt
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi
python3 -c "print(round(max(0.0, min(1.0, float('$SCORE')/100.0)), 6))" > /logs/verifier/reward.txt
echo "reason=graded score=$SCORE" > /logs/verifier/reward_reason.txt
chmod 644 /logs/verifier/reward.txt
echo "Harbor reward: raw=$SCORE normalized=$(cat /logs/verifier/reward.txt)"
