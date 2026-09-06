# Zero-One Integer Programming Solver from Scratch (v2)

Task id: `p6zeta_zero_one_ip_solver_from_scratch_v2`

Derived on 2026-09-05 from bundle `f5e2f024-213f-58cf-aa21-594a53624a8b` (v1). v1 is left
untouched; this bundle replaces the hidden set, the judge script and the agent instruction.

## Why v2 exists

Two frontier runs on v1 (Claude Opus 5 on OpenHands, 2026-09-04 and 2026-09-05) showed:

1. Every one of the 90 hidden instances was solved to the proven optimum inside the 60-second
   budget within the first 40 minutes. Lane 2 (30 points) and lane 4 (20 points) saturated
   immediately; the only lane left to climb was lane 3.
2. Lane 5 (15 points) was declared in `score.py`, `p6zeta_lib.py`, the instruction and TRUTH.md,
   but `tests/test.sh` never generated perturbed cohorts nor passed `--perturbations-root`, so
   every submission scored 0 there and the task's ceiling was 85 against a full-reward threshold
   of 95. The instruction told the agent the judge ran the sweep; it did not.
3. TRUTH.md described a lane-3 judge that ranked instances from agent-reported wall times;
   the real judge reads a K=8 `l3_ranking.json` written by the solver.

## What changed

| Area | v1 | v2 |
|---|---|---|
| Hidden instances | small (MDK n 71-97, knapsack n 259-393, ...), all solved to optimum in < 60 s by a from-scratch solver | same seven families, same schema; Chu-Beasley MDK with tight capacities, almost-subset-sum and strongly correlated knapsacks with coefficients to 10^6, dense near-unicost set cover, min-cost type-D GAP (5-8 machines), aggregated-capacity CFL, DSATUR-tight colouring with symmetry-breaking rows, 10-11 city TSP with all subtour rows. Optima certified by HiGHS (`scipy.optimize.milp`, `mip_rel_gap=0`), hardest-certified-first selection per family |
| Lane 5 | never executed | `tests/perturb_v2.py` builds the seven perturbations on a fixed 21-instance subset (first 3 per family), the judge solves them and un-perturbs the outputs before `score.py` |
| Judge parallelism | serial | 16 lanes, each `./solve` pinned to one cpu with `taskset` |
| Agent instruction | claimed single-shot submission and a lane-5 sweep | describes the real `sforge-submit` loop (60 submissions, 900 s cooldown, scalar feedback, identical archives not regraded), the real lane-3 file contract, the real lane-5 subset and formula |
| Develop set | 6 instances, no MDK | 7 instances, one per family, same generator as the hidden set |
| `p6zeta_lib.py` | | `TASK_ID` = v2 id, `L5_SUBSET_PER_FAMILY = 3` |
| Lane 2 curve | 30 at gap 0, 27 at <= 2%, 24 at 5%, 18 at 10%, 10 at 20%, 4 at 35% | 30 at 0, 27 at <= 0.5%, 24 at 1%, 18 at 2%, 10 at 5%, 4 at 10%. Optima are certified, so exactness is rewarded and near-misses are no longer almost free |


## Calibration on the v2 judge (2026-09-05, final images)

| Solver | Total | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|
| Today's v1 frontier artifact (Opus 5 / OpenHands, 75.62 on v1) | 79.67 | 9.78 | 23.69 | 12.50 | 19.29 | 14.42 |
| Yesterday's v1 frontier artifact (Opus 5 / OpenHands, 81.87 on v1) | 72.07 | 10.00 | 24.39 | 3.12 | 19.69 | 14.88 |
| Reference solver (calibration artifact) | 24.23 | 1.11 | 3.33 | 0.00 | 5.50 | 14.29 |
| All-zero control | 4.44 | 4.44 | 0 | 0 | 0 | 0 |

Per-family gap profile of the frontier artifacts under 60 s: facility location 2-10%+, GAP 1-5%,
MDK 0-1%, colouring/TSP/knapsack/set cover at or near the optimum. Lane 2 now spreads instead of
saturating; lane 5 is live and the all-zero control no longer collects it.

## Layout

```
task.toml                    v2 task id; images pinned by digest after build
instruction.md               pointer + full agent instruction
task_instruction.md          agent-facing spec (also copied into the work image)
environment/                 work image: Dockerfile, README, p6zeta_lib.py, data/develop (7), ip_format_spec.md
tests/                       judge image: Dockerfile, score.py, p6zeta_lib.py, perturb_v2.py, test.sh, data/
tests/data/hidden_benchmarks 90 instances   tests/data/hidden_optima.json  HiGHS-certified optima + wall times
solution/                    private oracle tree: TRUTH.md, reference_solver.py, rubrics.json, solve.sh
solution/reference_solver.py        unchanged v1 reference (calibration artifact)
solution/TRUTH.md                   ground-truth record for the v2 route
trajectories/                two recorded runs: opus-5 (42 submissions), gpt-5.6-sol (66, merged)
plots/score_vs_submissions.svg      both runs on one axis
plots/opus-5.svg                    opus-5 alone
plots/gpt-5.6-sol.svg               gpt-5.6-sol alone
```

Plots are drawn from `trajectories/<run>/run_history.json` -> `entries[]` in array order, which is
the true submission order. Filled dots are agent-initiated submissions, hollow dots are
evaluator-only snapshots, and the staircase is best-so-far.

The shipped `tests/data/hidden_optima.json` is the frozen truth for this bundle. The authoring
scripts that produced the hidden set and certified its optima are retained privately and are not
part of the published bundle.
