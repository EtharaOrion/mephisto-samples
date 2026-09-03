#!/usr/bin/env bash
# forge-canary: FORGE-CANARY-CB5DCD73188C60E84FADF07F58F31424
set -euo pipefail
# vliw_kernel_optimization verifier entrypoint. Writes the bound reward path and attributes every zero to a machine readable reason.
HERE="${EDGEBENCH_HARNESS_DIR:-/verifier}"
REWARD_PATH="${REWARD_PATH:-/logs/verifier/reward.json}"
WORKSPACE="${EDGEBENCH_WORKSPACE:-/home/workspace}"
mkdir -p "$(dirname "$REWARD_PATH")"

python3 "$HERE/score.py" --workspace "$WORKSPACE" --reward-path "$REWARD_PATH"

# A failing compiled rubric item is a measurement, not a harness fault, so its status is recorded and never propagated.
set +e
REWARD_PATH="$REWARD_PATH" python3 -m pytest -q "$HERE/test_output.py" \
    --junit-xml "$(dirname "$REWARD_PATH")/compiled_rubric.xml"
RUBRIC_STATUS=$?
set -e
echo "{\"compiled_rubric_exit\": ${RUBRIC_STATUS}}" > "$(dirname "$REWARD_PATH")/compiled_rubric.json"

exit 0
