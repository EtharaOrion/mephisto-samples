#!/usr/bin/env bash
# GENERATED SECTION. DO NOT HAND-EDIT. Source: solution/grounding.yaml
set -euo pipefail

target="/home/workspace/submission/codec.py"
mkdir -p "$(dirname "${target}")"
cp /solution/reference/codec.py "${target}"
echo "oracle installed reference codec at ${target}"
