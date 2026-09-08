#!/usr/bin/env bash
# Harbor verifier entry point. It must terminate by writing the reward contract path the
# delivery block binds, and every zero must carry a machine-readable reason rather than an
# unwritten or empty reward file.
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REWARD_PATH="/logs/verifier/reward.txt"
mkdir -p "$(dirname "${REWARD_PATH}")"

python "${TESTS_DIR}/score.py"
status=$?

if [ ! -s "${REWARD_PATH}" ]; then
  # The scorer failed before it could write. Fail closed with a reason rather than leaving
  # the reward file absent, because an absent reward is indistinguishable from a task that
  # never ran.
  echo "0.0" > "${REWARD_PATH}"
  printf '{"reward": 0.0, "reason": "verifier_crashed", "exit_status": %d}\n' "${status}" \
    > "$(dirname "${REWARD_PATH}")/report.json"
fi

# The compiled rubric tests read the report the scorer wrote. They are a second, redundant
# statement of the same relations and they never change the reward.
python -m pytest "${TESTS_DIR}/test_output.py" -q || true

cat "${REWARD_PATH}"
exit 0
