#!/bin/bash
# Harbor eval driver. Runs the judge, greps the structured-result block,
# extracts score (0-100), converts to 0-1 reward, prints HARBOR_REWARD.
set -uo pipefail

mkdir -p /logs/verifier

cd /home/workspace/sec_equity_erosion_watchlist
JUDGE_ROOT=/judge CANDIDATE_ROOT=/home/workspace/sec_equity_erosion_watchlist python3 /judge/score.py > /logs/verifier/score.out 2>&1
RC=$?

if [ $RC -ne 0 ]; then
    echo "score.py exited non-zero: $RC"
    cat /logs/verifier/score.out
    echo "HARBOR_REWARD=0"
    echo "0" > /logs/verifier/reward.txt
    exit 0
fi

python3 - <<'PY' > /logs/verifier/reward.txt
import json
import re
import sys

with open("/logs/verifier/score.out") as fh:
    text = fh.read()

m = re.search(
    r">>>>> Start Structured Result\s*\n(.*?)\n>>>>> End Structured Result",
    text,
    flags=re.S,
)
if not m:
    print(0.0)
    sys.exit(0)

try:
    payload = json.loads(m.group(1))
    score = float(payload.get("score", 0.0))
except Exception:
    print(0.0)
    sys.exit(0)

reward = max(0.0, min(1.0, score / 100.0))
print("%.6f" % reward)
PY

REWARD=$(cat /logs/verifier/reward.txt)
echo "HARBOR_REWARD=$REWARD"
cat /logs/verifier/score.out
