#!/usr/bin/env bash
# Harbor verifier entrypoint for p8theta_rasterlab_bitexact_rewrite.
# Terminates by writing /logs/verifier/reward.txt (normalized [0,1]) per the
# reward contract in seed/contract.yaml (delivery.reward_contract_path is the
# structured JSON echoed on stderr; Harbor consumes reward.txt).
set +e

mkdir -p /logs/verifier
mkdir -p /home/workspace/candidate

# Materialize the submitted candidate tree into the workspace.
if [ -d /logs/artifacts/submission/candidate ]; then
    cp -R /logs/artifacts/submission/candidate/. /home/workspace/candidate/
elif [ -d /logs/artifacts/submission ]; then
    cp -R /logs/artifacts/submission/. /home/workspace/candidate/
fi

# Enforce submit_exclude: never score a shipped target/ tree.
rm -rf /home/workspace/candidate/target

export RASTERLAB_WORKSPACE=/home/workspace
export RASTERLAB_REFERENCE_SRC=/opt/reference-src

python3 /opt/verifier/verify.py \
    > /logs/verifier/score_stdout.log \
    2> /logs/verifier/score_stderr.log
verifier_rc=$?

score_line=$(grep '^TOTAL_SCORE ' /logs/verifier/score_stdout.log | tail -1 | awk '{print $2}')

if [ -z "${score_line}" ]; then
    echo "0.0" > /logs/verifier/reward.txt
    echo "REWARD_ATTRIBUTION_REASON no_total_score_line rc=${verifier_rc}" >&2
    exit 1
fi

normalized=$(python3 - "${score_line}" <<'PY'
import sys
raw = float(sys.argv[1])
print(round(max(0.0, min(1.0, raw / 100.0)), 6))
PY
)

echo "${normalized}" > /logs/verifier/reward.txt
echo "Harbor reward: raw=${score_line} normalized=${normalized}"

grep '^STRUCTURED_RESULT_JSON' /logs/verifier/score_stderr.log | tail -1 >&2

exit 0
