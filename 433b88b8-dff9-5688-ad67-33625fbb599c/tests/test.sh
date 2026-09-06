#!/bin/bash
# p6zeta v2 judge. Differences from v1:
#   * 16 parallel workers, each ./solve pinned to ONE cpu (taskset) so a solver
#     cannot buy score with threads and timing lanes are comparable across hosts
#   * lane 5 is real: seven perturbations of a fixed 21-instance subset (3 per
#     family), solver outputs un-perturbed and handed to score.py
#   * every knob is an env var so the same script grades locally and in CI
set -euo pipefail

mkdir -p /logs/verifier /home/workspace/submission
if [ -d /logs/artifacts/submission ]; then
  cp -r /logs/artifacts/submission/. /home/workspace/submission/
fi
cd /home/workspace/submission
if [ -x ./build.sh ]; then
  ./build.sh
fi

S=/home/workspace/scoring
DATA=$S/data/hidden_benchmarks
TL=${P6ZETA_PER_INSTANCE_TIMEOUT:-60}
WORKERS=${P6ZETA_JUDGE_WORKERS:-16}
L5_PER_FAMILY=${P6ZETA_L5_PER_FAMILY:-3}
L5_SALT=${P6ZETA_L5_SALT:-p6zeta-v2-judge-salt-2026-09}
# CPUs this container may actually use (respects a cpuset limit, unlike nproc alone)
mapfile -t CPUS < <(python3 -c "import os; print('\n'.join(map(str, sorted(os.sched_getaffinity(0)))))")
NCPU=${#CPUS[@]}
[ "$WORKERS" -gt "$NCPU" ] && WORKERS=$NCPU
PIN=1; command -v taskset >/dev/null 2>&1 || PIN=0
if [ "$PIN" -eq 1 ] && ! taskset -c "${CPUS[0]}" true >/dev/null 2>&1; then PIN=0; fi

mkdir -p $S/outputs $S/traces $S/perturb $S/perturb_work

# run_batch <list-file> <outdir> <tracedir>: WORKERS parallel lanes, lane w takes
# every WORKERS-th instance and is pinned to cpu (w mod NCPU).
run_batch() {
  local list=$1 outdir=$2 tracedir=$3
  mapfile -t INST < "$list"
  local total=${#INST[@]}
  for ((w=0; w<WORKERS; w++)); do
    (
      for ((k=w; k<total; k+=WORKERS)); do
        inst="${INST[k]}"; id=$(basename "$inst" .ip.json)
        if [ "$PIN" -eq 1 ]; then
          timeout ${TL}s taskset -c "${CPUS[$((w % NCPU))]}" ./solve "$inst" > "$outdir/$id.out.json" 2> "$tracedir/$id.log" || true
        else
          timeout ${TL}s ./solve "$inst" > "$outdir/$id.out.json" 2> "$tracedir/$id.log" || true
        fi
      done
    ) &
  done
  wait
}

# ---- base cohort: all hidden instances -------------------------------------
ls $DATA/*.ip.json > $S/base.list
echo "judge: base cohort $(wc -l < $S/base.list) instances, $WORKERS workers, ${TL}s each, pin=$PIN" >&2
run_batch $S/base.list $S/outputs $S/traces

# ---- lane 5: seven perturbations of a fixed subset --------------------------
python3 $S/perturb_v2.py make --instances $DATA --work $S/perturb_work \
  --salt "$L5_SALT" --per-family "$L5_PER_FAMILY" > $S/l5_subset.txt
echo "judge: lane 5 subset $(wc -l < $S/l5_subset.txt) instances x 7 perturbations" >&2
for name in variable_order_within_constraint constraint_reorder coefficient_common_scale \
            instance_id_salt_rewrite json_whitespace_reformat output_json_field_order \
            output_json_trailing_whitespace; do
  ls $S/perturb_work/$name/in/*.ip.json > $S/perturb_work/$name/list
  mkdir -p $S/perturb_work/$name/trace
  run_batch $S/perturb_work/$name/list $S/perturb_work/$name/raw $S/perturb_work/$name/trace
  python3 $S/perturb_v2.py restore --work $S/perturb_work --perturbation $name --out $S/perturb
done

# ---- lane 3 ranking file, if the solver wrote one ----------------------------
if [ -f /home/workspace/submission/l3_ranking.json ]; then
  L3_ARG="--l3-ranking /home/workspace/submission/l3_ranking.json"
else
  L3_ARG=""
fi

python3 $S/score.py \
  --instances $DATA \
  --optima $S/data/hidden_optima.json \
  --outputs $S/outputs \
  --traces $S/traces \
  --perturbations-root $S/perturb \
  --perturbation-subset $S/l5_subset.txt \
  $L3_ARG \
  --reward-out /logs/verifier/reward.json \
  --print-summary

python3 -c "import json; d=json.load(open('/logs/verifier/reward.json')); open('/logs/verifier/reward.txt','w').write(f\"{d['score']/100.0:.6f}\\n\")"
