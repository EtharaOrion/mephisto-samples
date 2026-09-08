#!/bin/bash
set -e
mkdir -p /home/workspace/submission
cp /solution/oracle_opmargin_change_ranks.csv /home/workspace/submission/opmargin_change_ranks.csv
echo "solve.sh: byte-copied oracle_opmargin_change_ranks.csv to submission/"
