#!/bin/bash
# ORACLE: copy the precomputed hindsight book into the workspace.
set -e
mkdir -p /home/workspace/strategy
cp /solution/strategy/* /home/workspace/strategy/
echo 'oracle staged'
