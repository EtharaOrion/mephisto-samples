#!/bin/sh
# GENERATED SECTION. DO NOT HAND-EDIT.
# Source of truth: solution/grounding.yaml
#
# CANARY-BLOCK-BEGIN
# slot-0: 672168dc451ee148
# slot-1: 9b24b041e7affb6a
# slot-2: b602c6f34bd3a044
# CANARY-BLOCK-END
#
# Harbor oracle entry point. Answers the identical invocation contract the
# graded artifact must answer, by delegating to the pinned upstream. This is the
# REFERENCE-FIDELITY reference under invariant 18 and it measures C = 1.000000.
#
# PRIVATE. Harbor mounts solution/ only for the oracle path.
set -eu

BPFC="/usr/local/bin/bpfc-oracle"
if [ ! -x "$BPFC" ]; then
    echo "solve.sh: oracle binary missing at $BPFC" >&2
    exit 2
fi

exec "$BPFC" "$@"
