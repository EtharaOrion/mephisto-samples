#!/usr/bin/env bash
# forge-canary: FORGE-CANARY-22582D8CBA73BFC7E63DCE10B60DAC9D
set -euo pipefail
# arc_compiler_runtime verifier entrypoint. Writes the bound reward path and attributes every zero to a machine readable reason.
HERE="${EDGEBENCH_HARNESS_DIR:-/verifier}"
REWARD_PATH="${REWARD_PATH:-/logs/verifier/reward.json}"
WORKSPACE="${EDGEBENCH_WORKSPACE:-/home/workspace}"
mkdir -p "$(dirname "$REWARD_PATH")"

python3 "$HERE/score.py" --workspace "$WORKSPACE" --reward-path "$REWARD_PATH"

# Bridge the structured reward into Harbor's reward.txt contract read by the SForge loader.
python3 - "$REWARD_PATH" > /logs/verifier/reward.txt <<'BRIDGE_PY'
import json, sys
try:
    value = float(json.load(open(sys.argv[1]))["score"])
except Exception:
    value = 0.0
print(round(value, 6))
BRIDGE_PY
chmod 644 /logs/verifier/reward.txt

# A failing compiled rubric item is a measurement, not a harness fault, so its status is recorded and never propagated.
set +e
REWARD_PATH="$REWARD_PATH" python3 -m pytest -q "$HERE/test_output.py" \
    --junit-xml "$(dirname "$REWARD_PATH")/compiled_rubric.xml"
RUBRIC_STATUS=$?
set -e
echo "{\"compiled_rubric_exit\": ${RUBRIC_STATUS}}" > "$(dirname "$REWARD_PATH")/compiled_rubric.json"

exit 0
