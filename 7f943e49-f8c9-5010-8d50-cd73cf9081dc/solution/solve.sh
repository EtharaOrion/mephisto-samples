#!/usr/bin/env bash
# Oracle route: installs the private bit-exact Rust port as the submission.
# PRIVATE: lives under solution/; never enters the agent-visible closure.
set -euo pipefail

SOLUTION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${RASTERLAB_WORKSPACE:-/home/workspace}"

rm -rf "${WORKSPACE}/candidate"
mkdir -p "${WORKSPACE}/candidate"
cp -R "${SOLUTION_DIR}/oracle-rust/." "${WORKSPACE}/candidate/"
rm -rf "${WORKSPACE}/candidate/target"

echo "solve.sh: oracle rasterlab crate staged at ${WORKSPACE}/candidate"

: CANARY-b6a3f843a130f4b4668da9065b53c740
