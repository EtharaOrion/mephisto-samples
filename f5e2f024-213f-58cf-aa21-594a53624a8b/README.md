# `f5e2f024-213f-58cf-aa21-594a53624a8b` - `Zero-One Integer Programming Solver from Scratch`

One model cohort (`anthropic/claude-opus-5[1m]`), one twelve-hour session, 118 graded submissions packaged on one axis.

The task is to build a 0-1 integer programming solver from nothing (no CPLEX, Gurobi, OR-Tools, PuLP, CBC, GLPK, SCIP, HiGHS, `scipy.optimize.milp`, no SAT backend, no network) and ship it as `build.sh` + `solve` + `src/`. The judge invokes `./solve <instance.ip.json>` once per instance across 90 held-out instances drawn from seven NP-hard families (multi-dimensional knapsack, capacitated facility location, generalized assignment, graph colouring, set cover, TSP cutting-plane, 0-1 knapsack), each under a 60 s wall-clock kill, 16 workers wide, inside a 7200 s whole-run budget. The graded surface is wider than "did you find the optimum": five lanes score structural validity, optimality gap against author-computed optima, top-K precision on a hardness *ranking*, anytime progression recovered from `BEST ts=… obj=…` tokens on stderr, and stability under seven deterministic perturbations. The score is their sum clipped to `[0, 100]` and normalised to `[0, 1]`: a bounded continuous objective that climbs, with a KILL band that collapses it to zero outright.

```
task                    edgebench/p6zeta_zero_one_ip_solver_from_scratch
budget                  43200 s (12 h) agent window, 300 submissions max, 120 s cooldown,
                        1800 s evaluator-only snapshot interval
harness / stack         claude-code 2.1.159 · claude-opus-5[1m] · python base image ·
                        linux/amd64,linux/arm64 · parser structured_json · selection score_first
network                 agent: no-network · verifier: no-network, separate container
verifier                7200 s · 90 hidden instances · 60 s per instance · 16 workers
score                   (L1 10 + L2 30 + L3 25 + L4 20 + L5 15) summed, clipped to [0, 100],
                        normalised to [0, 1]; 0 outright if any KILL reason fires
                        (forbidden_library, network_egress, private_artifact_read,
                        shortcut_mine_and_return)
```

The task files at the top level (`instruction.md`, `task.toml`, `environment/`, `tests/`, `solution/`) are the frozen task exactly as graded. This delivery organises the run's records under `trajectories/opus-5/`, one directory per submission beneath `submissions/`.

## Session results

| | `claude-opus-5[1m]` |
|---|---|
| submissions packaged | **118** (95 agent-initiated + 23 evaluator-only) |
| submissions scored above zero | 118 |
| submissions that tripped the KILL band | 0 |
| selection | `score_first` → **`agent-87`** |
| best score | **0.849975** (85.00 / 100) |
| final submission score | 0.849975 (`agent-95`) |
| median / mean score | 0.7562 / 0.7417 |
| first graded submission | `auto-1`, 0.352614, at 0.50 h |
| best first reached | `agent-87`, at 11.03 h of 12 h |
| vs. the private calibration reference (37.74 / 100) | 2.25× |
| cumulative input-side tokens | 173,457,986 * |
| session wall clock | 43,200.1 s (12.00 h), `timed_out: true`, 0 resumes |

Where the 85.00 came from, and where the first submission stood:

| Lane | Max | `auto-1` (first graded) | `agent-87` (best) |
|---|---|---|---|
| L1 structural / feasibility | 10 | 7.78 (70 of 90 instances) | **10.00** (90 of 90) |
| L2 optimality-gap threshold curve | 30 | 14.44 | **30.00** |
| L3 top-K=8 hardness-ranking precision | 25 | 0.00 | **25.00** (8 of 8) |
| L4 anytime progression | 20 | 13.05 | **20.00** |
| L5 perturbation robustness | 15 | 0.00 | 0.00 |
| total | 100 | 35.26 | 85.00 |

L1 and L2 saturated on the first agent-initiated submission, 49 minutes in: 90 of 90 instances structurally valid, and every optimality gap at or below the `0.00` threshold, meaning the solver matched the author-computed optimum on all 90 hidden instances at hour one. L4 saturated by `auto-3` at 1.5 h. Everything after hour four was a single lane: L3 top-K=8 precision over the 30-instance multi-dimensional-knapsack cohort, ranked by hardness. It climbed 4/8 (`agent-1`) → 5/8 (`agent-14`, 4.44 h) → 6/8 (`agent-48`, 7.69 h) → 7/8 (`agent-55`, 8.21 h) → 8/8 (`agent-87`, 11.03 h). Eight of the twelve hours bought four instances of ranking precision.

The artifact is ~3,600 lines of C99 against nothing but libm, in twelve files plus a pure-Python fallback for the case where no compiler is present: an order-independent JSON reader; a bounded-variable dual simplex on a dense tableau with no phase 1; a Lagrangian dual solved by the volume algorithm to produce a primal estimate for guiding rounding; penalty tabu search with exact large-neighbourhood search; structure-specific exact routines whose every candidate is re-verified against the *original* constraint set before acceptance; LP-driven branch-and-bound with diving and RINS; and a SIGALRM handler that publishes the incumbent through a double buffer with async-signal-safe writes, so an overrun degrades to a scored answer instead of a 60 s kill that would zero every lane for that instance.

## Caveats you should read before quoting a number

**`best_pass_rate: 0.0` and the log's `best=0.00%` are artifacts, not results.** This task's parser is `structured_json`: `score.py` writes a continuous reward and there are no pytest cases, so `total_tests`, `passed`, `failed` and `pass_rate` are zero in all 118 `report.json` files. `run_agent.log` closes with `Done: best=0.00% (round 'agent-87')` because that line prints the pass rate. The authoritative number is `score` / `best_score` = `0.849975`.

**The graded L3 lane depends on a file the submission manifest cannot ship.** `task.toml` pins `submit_paths = ["build.sh", "solve", "src/"]`; `instruction.md` asks for `l3_ranking.json`; `score.py` awards zero L3 without it. No `l3_ranking.json` appears in any submission tarball or `allowed_files.txt`. It scores anyway because `src/main.c` records per-instance hardness features to a scratch directory and rewrites `l3_ranking.json` into the working directory, plus four other candidate paths, after every instance, so the file exists by the time the judge's per-instance loop ends and `test.sh` looks for it. L3 is therefore graded off cross-instance filesystem state the solver builds up inside the judge's own sweep, not off a shipped artifact. No KILL reason fired for this in any of the 118 gradings.

**The 23 `auto-*` rounds are snapshots, not attempts.** The host grades the workspace through the same judge every 1800 s and withholds the result from the agent. They frequently reproduce a neighbouring agent submission almost exactly (`auto-2` at 0.712731 beside `agent-1` at 0.712594). Reading 118 as 118 independent attempts overstates the run; 95 is the agent-initiated count.

**`agent-87` is not the last submission, and the last submission is a different program.** Selection is `score_first`, so it took the earliest round to reach the maximum. `agent-95` ties at `0.849975` but ships twelve source files instead of thirteen (`src/lag.c`, the volume-algorithm Lagrangian dual, is gone), and total source drops from 3,624 to 3,276 lines. Two materially different programs measure identically on this harness.

**The run ended on the clock.** `timed_out: true`, `runtime_seconds: 43200.1`, `resume_count: 0`. The agent was cut off at the twelve-hour boundary mid-work; it did not converge and stop. The score trace is also not monotone in submission order: `agent-27` graded `15.62/100` with `l1=0.00 l2=0.00 l4=0.00` and 0 of 90 instances passing structural check, a total solver breakage recovered on the next round.

**Token totals are a floor, and the output figure is unusable.** `agent_output.txt` holds 500 assistant records, each carrying a streaming per-chunk `usage` block whose `output_tokens` never exceeds 115 and sums to 9,376, an artifact of chunked logging rather than a session total. The input-side figures are coherent and are what the `*` above sums: 100,768 input + 27,574,515 cache-creation + 145,782,703 cache-read. No cost is recorded anywhere in this bundle.

**The reference is a calibration artifact, not a target.** `solution/TRUTH.md` measures the shipped `reference_solver.py` at 37.74/100 (`L1 7.00, L2 19.63, L3 3.12, L4 7.98, L5 0.00`) and states the agent is graded against author-computed optima directly, never against reference output. TRUTH.md additionally quotes EdgeBench Optimize @12h frontier figures (Opus 4.8 36.5, GPT-5.5 33.6, GPT-5.4 27.9, GLM-5.1 26.4, DS-V4-Pro 21.5); nothing in this bundle reproduces them.

**No per-submission agent narrative ships.** There is one raw `agent_output.txt` stream for the whole session, not a per-round history, and no rubric-panel verdicts; `solution/rubrics.json` is the deterministic lane schedule, not an LLM-judged rubric set. Where anything in the stream disagrees with `report.json` or `test_output.txt`, the verifier is correct.

**The oracle ships in this bundle.** `solution/TRUTH.md` sets out the golden solve path step by step, the eight near-miss routes with their measured scores, the per-lane reconciliation, and three canary tokens; `solution/reference_solver.py` and `solution/solve.sh` are executable. Anyone holding this directory can reproduce a calibrated result directly, so the task cannot be used to evaluate a model that has had access to it.

## Files

```
README.md                   this file
instruction.md              the objective handed to the agent
task.toml                   manifest: budgets, images, network mode, submit paths, selection
environment/                the agent-visible starting files and the work container image:
                            the agent-facing specification, the shared reference library,
                            the byte-level format spec, and 6 development instances
tests/                      the judge container: the 5-lane grader that produced every score
                            in this delivery, the 90 held-out instances across seven
                            families, and the judge-only optima and wall-time oracle
solution/                   PRIVATE - the oracle: golden solve path, near-miss routes,
                            the executable calibration reference, the lane rubric
trajectories/               one directory per run
  opus-5/                   the single packaged run (this delivery): run config, the run
                            ledger, host-side state and snapshot logs, the raw session
                            stream, and the final workspace archive
    submissions/            118 graded submissions, one directory each: 95 agent-initiated
                            (agent-NN) and 23 evaluator-only snapshots (auto-NN). Every
                            directory holds the submitted tree, the exact judge command,
                            the graded output with its per-lane summary line, and the
                            verifier's report, the authority for that round's score
```
