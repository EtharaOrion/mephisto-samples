#!/usr/bin/env bash
# Oracle staging script for p9iota_latticestore_workspace_reconstruction.
# Copies the complete reference workspace over the agent workspace mount so the
# verifier scores the known-good implementation end to end.
set -euo pipefail

SOLUTION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${LATTICE_WORKSPACE:-/home/workspace}"

rm -rf "${WORKSPACE}/workspace"
mkdir -p "${WORKSPACE}/workspace"
cp -R "${SOLUTION_DIR}/oracle-workspace/." "${WORKSPACE}/workspace/"
rm -rf "${WORKSPACE}/workspace/target"

echo "oracle workspace staged at ${WORKSPACE}/workspace"
: CANARY-17bf13d5d269a708a777eb4e0f31db34
