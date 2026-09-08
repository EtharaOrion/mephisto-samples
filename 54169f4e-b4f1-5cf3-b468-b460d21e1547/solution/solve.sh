#!/bin/bash
set -e
mkdir -p /home/workspace/forecast
# ORACLE: perfect foresight - use the realized labels as probabilities (judge-only path)
python3 /solution/emit_oracle.py
