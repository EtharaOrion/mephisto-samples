#!/bin/bash
# Harbor verifier entrypoint for p9iota_latticestore_workspace_reconstruction.
# Materializes the submitted workspace, runs the deterministic scorer, and
# writes the normalized reward to /logs/verifier/reward.txt.
set +e

mkdir -p /logs/verifier
mkdir -p /home/workspace

SUBMISSION_ROOT=""
if [ -d /logs/artifacts/submission/workspace ]; then
    SUBMISSION_ROOT=/logs/artifacts/submission/workspace
elif [ -d /logs/artifacts/submission ]; then
    SUBMISSION_ROOT=/logs/artifacts/submission
fi

rm -rf /home/workspace/workspace
mkdir -p /home/workspace/workspace
if [ -n "$SUBMISSION_ROOT" ]; then
    cp -R "$SUBMISSION_ROOT"/. /home/workspace/workspace/ 2>/dev/null
fi

# Enforce submit_exclude: build artifacts never participate in scoring.
rm -rf /home/workspace/workspace/target

export LATTICE_WORKSPACE=/home/workspace
export LATTICE_REFERENCE_SRC=/opt/reference-src

python3 /opt/verifier/verify.py > /logs/verifier/score_stdout.log 2> /logs/verifier/score_stderr.log
VERIFY_EXIT=$?

SCORE_LINE=$(grep '^TOTAL_SCORE ' /logs/verifier/score_stdout.log | tail -n 1)
if [ -z "$SCORE_LINE" ]; then
    echo "0.0" > /logs/verifier/reward.txt
    echo "REWARD_ATTRIBUTION_REASON verify.py emitted no TOTAL_SCORE line (exit $VERIFY_EXIT)" >&2
    echo "reward: 0.0"
    exit 1
fi

RAW_SCORE=${SCORE_LINE#TOTAL_SCORE }
python3 - "$RAW_SCORE" <<'EOF'
import sys
raw = float(sys.argv[1])
reward = max(0.0, min(1.0, raw / 100.0))
with open("/logs/verifier/reward.txt", "w") as fh:
    fh.write(f"{round(reward, 6)}\n")
EOF

echo "reward: $(cat /logs/verifier/reward.txt)"
grep '^STRUCTURED_RESULT_JSON' /logs/verifier/score_stderr.log | tail -n 1 >&2
exit 0
