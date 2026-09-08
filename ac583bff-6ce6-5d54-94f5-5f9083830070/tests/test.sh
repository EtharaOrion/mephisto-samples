#!/bin/bash
# Harbor verifier adapter for EdgeBench FORGE bundle: cryoem_single_particle_reconstruction.
# Runs the bundle's judge, translates output to Harbor's /logs/verifier/reward.txt.
set +e
mkdir -p /logs/verifier /home/workspace/cryoem_reconstruction

for f in /logs/artifacts/*; do
  [ -f "$f" ] || [ -d "$f" ] || continue
  cp -r "$f" "/home/workspace/cryoem_reconstruction/$(basename "$f")"
done

cd /home/workspace/cryoem_reconstruction
python /opt/cryoem_scoring/evaluate.py --submission_dir /home/workspace/cryoem_reconstruction --case_dir /home/workspace/cryoem_reconstruction --scoring_dir /opt/cryoem_scoring --output /home/workspace/cryoem_reconstruction/score.json 2>&1 | tee /logs/verifier/scoring_stdout.log

SCORE=$(grep -oE "TOTAL_SCORE\s+[-0-9.]+" /logs/verifier/scoring_stdout.log | tail -1 | awk '{print $2}')
[ -z "$SCORE" ] && SCORE=$(grep -oE "Final total score:\s*-?[0-9]+(\.[0-9]+)?" /logs/verifier/scoring_stdout.log | tail -1 | grep -oE "\-?[0-9]+(\.[0-9]+)?$")
[ -z "$SCORE" ] && SCORE=$(grep -oE '"score":\s*[-0-9.]+' /logs/verifier/scoring_stdout.log | tail -1 | grep -oE "[-0-9.]+$")
[ -z "$SCORE" ] && SCORE=0

SCORE_NORM=$(python3 -c "print(round(max(0.0, min(1.0, float('$SCORE') / 100.0)), 6))")
echo "$SCORE_NORM" > /logs/verifier/reward.txt
echo "Harbor reward: raw=$SCORE normalized=$SCORE_NORM"
