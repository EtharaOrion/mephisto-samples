#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
cd /home/workspace/retention

CANDIDATE_ROOT=/home/workspace/retention JUDGE_ROOT=/judge \
    python3 /judge/score.py 2>&1 | tee /tmp/judge_output.txt
JUDGE_EXIT=${PIPESTATUS[0]}

python3 - <<'PYEOF'
import json, re, sys
with open("/tmp/judge_output.txt") as f:
    text = f.read()

data = {}
m = re.search(r">>>>> Start Structured Result\n(.*?)>>>>> End Structured Result",
              text, re.DOTALL)
if m:
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        pass

if not data:
    for match in re.finditer(r"\{", text):
        start = match.start()
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(text[start:i + 1])
                        if isinstance(candidate, dict) and (
                            "score" in candidate or "pass_rate" in candidate
                        ):
                            data = candidate
                    except json.JSONDecodeError:
                        pass
                    break
        if data:
            break

score = data.get("score", data.get("pass_rate", 0.0))
try:
    score = float(score)
except (TypeError, ValueError):
    score = 0.0
score = max(0.0, min(1.0, score))

with open("/logs/verifier/reward.txt", "w") as f:
    f.write(f"{score}\n")

print(f"HARBOR_REWARD={score}")
PYEOF

exit 0
