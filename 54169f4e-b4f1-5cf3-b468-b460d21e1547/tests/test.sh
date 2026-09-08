#!/bin/bash
set +e
mkdir -p /logs/verifier /home/workspace/forecast
for src in /logs/artifacts /logs/artifacts/forecast; do
  [ -d "$src" ] || continue
  for f in "$src"/predictions.csv "$src"/model.py "$src"/notes.md; do [ -f "$f" ] && cp "$f" /home/workspace/forecast/; done
done
export TRIAGE_WORKSPACE=/home/workspace
python3 /judge/score.py 2>&1 | tee /logs/verifier/scoring_stdout.log
SCORE=$(python3 - <<'PY'
import json,re
t=open('/logs/verifier/scoring_stdout.log').read()
m=re.search(r'>>>>> Start Structured Result\n(.*?)\n>>>>> End Structured Result',t,re.S)
print(json.loads(m.group(1))['score'] if m else '')
PY
)
[ -z "$SCORE" ] && { echo 0 > /logs/verifier/reward.txt; exit 1; }
python3 -c "print(round(max(0.0,min(1.0,float('$SCORE')/100.0)),6))" > /logs/verifier/reward.txt
echo "Harbor reward: raw=$SCORE normalized=$(cat /logs/verifier/reward.txt)"
