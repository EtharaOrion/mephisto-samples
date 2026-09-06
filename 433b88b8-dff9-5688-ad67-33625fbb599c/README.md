# Zero-One Integer Programming Solver from Scratch

Build a 0-1 integer programming solver from scratch, in C or C++, with no external optimization
libraries. The judge runs the submitted `./solve` against 90 hidden instances drawn from seven
NP-hard families, under a 60 second per-instance timeout and no network access.

## Hidden set

Seven families, one JSON schema, dense coefficient rows, binary variables, constraints in
`<=`, `>=` or `==`:

- **multi-dimensional knapsack** — Chu-Beasley correlated profits with tight capacities (30 instances)
- **zero-one knapsack** — almost-subset-sum and strongly/inversely correlated, coefficients to 10^6, which defeats dynamic programming
- **set cover** — dense random cover with near-unicost costs, so the LP relaxation is fractional
- **generalized assignment** — Martello-Toth type D min-cost, 5-8 machines against 40-60 jobs
- **capacitated facility location** — aggregated capacity only, giving a weak LP bound
- **graph colouring** — dense graphs, DSATUR-tight colour budget, symmetry-breaking rows
- **TSP cutting plane** — 10-11 cities with every subtour row enumerated

Hardness comes from structure rather than size. Optima are certified by HiGHS
(`scipy.optimize.milp`, `mip_rel_gap=0`); only instances proved optimal were admitted, selected
hardest-certified-first within each family. The develop set under `environment/data/develop`
carries one instance per family, generated the same way.

## Scoring

100 points across five lanes, with a full-reward threshold of 0.95:

| Lane | Points | Measures |
|---|---|---|
| L1 | 10 | status agreement (feasible / infeasible / unknown) per instance |
| L2 | 30 | optimality gap against the certified optimum |
| L3 | 25 | top-K=8 precision of a solver-written `l3_ranking.json` against the HiGHS wall-time ranking of the 30-instance multi-dimensional-knapsack cohort |
| L4 | 20 | solution validity and reporting discipline |
| L5 | 15 | invariance under seven deterministic perturbations |

The L2 curve awards 30 at gap 0, 27 at <= 0.5%, 24 at 1%, 18 at 2%, 10 at 5% and 4 at 10%. Because
the optima are certified, exactness is rewarded and near-misses are not close to free.

L5 rebuilds a fixed 21-instance subset (the first 3 of each family) under seven perturbations —
variable order within a constraint, constraint reorder, common coefficient scaling, instance-id
salt rewrite, JSON whitespace reformat, output field order, and output trailing whitespace. The
judge solves the perturbed cohorts, un-perturbs the outputs, and grades them alongside the base
cohort.

A KILL band clips the total to 0 for a forbidden optimization library, network egress, reading a
private artifact, or mining and returning the answer key.

The judge runs 16 lanes in parallel with each `./solve` pinned to a single cpu via `taskset`, so a
solver cannot buy score with threads and the timing lanes stay comparable across hosts.

## Submission loop

The agent submits with `sforge-submit`, which packages `build.sh`, `solve` and `src/`, grades them
in a separate container, and returns a single scalar in [0, 1]. Submissions are capped with a
cooldown between them, a byte-identical resubmission returns the previous score without regrading,
and no per-lane or per-instance breakdown is returned — local measurement against the develop set
is the only fine-grained feedback available.

## Calibration

Measured on the shipped judge, 2026-09-05:

| Solver | Total | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|---|
| Frontier artifact A (Opus 5 / OpenHands) | 79.67 | 9.78 | 23.69 | 12.50 | 19.29 | 14.42 |
| Frontier artifact B (Opus 5 / OpenHands) | 72.07 | 10.00 | 24.39 | 3.12 | 19.69 | 14.88 |
| Reference solver (calibration artifact) | 24.23 | 1.11 | 3.33 | 0.00 | 5.50 | 14.29 |
| All-zero control | 4.44 | 4.44 | 0 | 0 | 0 | 0 |

Per-family gap profile of the frontier artifacts under 60 s: facility location 2-10%+, generalized
assignment 1-5%, multi-dimensional knapsack 0-1%, and colouring, TSP, knapsack and set cover at or
near the optimum. Lane 2 spreads rather than saturating, and the all-zero control does not collect
lane 5.

## Layout

```
task.toml                    task contract; images pinned by digest
instruction.md               pointer to the agent-facing specification
environment/                 work image: Dockerfile, README, solver library, agent spec,
                             7 develop instances, byte-level format spec
tests/                       judge image: Dockerfile, score.py, solver library,
                             perturbation builder, test.sh, data/
tests/data/hidden_benchmarks 90 hidden instances
tests/data/hidden_optima.json  HiGHS-certified optima plus solver wall times
solution/                    private oracle tree: TRUTH.md, reference_solver.py,
                             rubrics.json, solve.sh
trajectories/                two recorded runs: opus-5 (42 submissions),
                             gpt-5.6-sol (66, merged from two parts)
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
