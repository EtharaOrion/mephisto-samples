# `120ddda7-c14b-5ba0-9dba-d6e9441cc885`

Two model cohorts, one twelve-hour session each, on the same agent harness.

The task is the mutated sibling of `62b54382-a910-5b29-ad0e-1efa993cc615`: rebuild a **deliberately modified** libpcap 1.10.6 BPF filter compiler in C from observable behaviour alone - no libpcap source, headers, binary, documentation, or network. The reference is not stock libpcap: four deterministic, semantics-preserving mutations (applied by `mut1.patch`, sha256 `f3d5502b...86600`, inside the private authoring image, never shipped) change its code generation and instruction layout choices only, so for most expressions it emits different bytes than upstream while accepting exactly the same packets - measured at 1,889,280 packet evaluations with zero acceptance divergence. Per the private calibration in `solution/TRUTH.md`, the optimized program differs from the unoptimized one on 61.4% of the corpus and 94.4% of the optimizer-only stratum. Recalled upstream bytes are wrong wherever the mutations bite; the departures must be excavated from the 750-record `public_cases.jsonl`. Graded on exact cBPF instruction-tuple equality and exact error-string equality against 12,000 hidden `(dlt, snaplen, optimize, netmask, filter)` cases across 8 weighted strata, plus a gated judge-timed compile-throughput term.

```
task                    edgebench/120ddda7-c14b-5ba0-9dba-d6e9441cc885
                        (task_id libpcap_bpf_codegen_fidelity)
budget                  43200 s (12 h) agent window, 300 submissions max, 120 s cooldown,
                        1800 s evaluator-only snapshot interval
harness / stack         openhands · cpp base image · linux/amd64 ·
                        parser structured_json · selection score_first
cohorts                 anthropic/claude-opus-5[1m] · openai/gpt-5.6-sol
network                 agent: no-network · verifier: no-network, separate container
verifier                900 s budget · 12,000 hidden cases · 8 public weights, hidden contents ·
                        timing subset, 3 warmups + 5 timed trials, interleaved,
                        judge wall clock only
score                   R = clip(0.88·C + 0.12·P·min(1, C/0.25), 0, 1)
                        C: weighted mean over 8 strata; per case: exact tuple sequence or
                        exact error string = 1.00, structurally valid divergence =
                        0.60 · floor-corrected similarity, invalid or missing = 0.00
                        P: clip(ln(r/0.5)/ln(8), 0, 1) with r = t_upstream/t_candidate,
                        dead zone r <= 1.05 scores 0
```

The task files at the top level (`instruction.md`, `task.toml`, `environment/`, `tests/`, `solution/`) are the frozen task exactly as graded. Each run's records live under `trajectories/<cohort>/`, one directory per submission beneath `submissions/`.

Both cohorts ran the same agent, the same task, and the same settings, so the difference between them is the model and nothing else.

## Session results

| | `claude-opus-5[1m]` | `gpt-5.6-sol` |
|---|---|---|
| submissions packaged | **75** (52 agent-initiated + 23 evaluator-only) | **173** (154 agent-initiated + 19 evaluator-only) |
| submissions scored | 69 | 168 |
| selection | `score_first` -> **`agent-49`** | `score_first` -> **`agent-88`** |
| best score | **0.971848** | **0.885184** |
| first graded submission | `auto-1`, 0.019830 (the starter floor) | `auto-1`, 0.548295 |
| best first reached | `agent-49`, at 10.49 h of 12 h | `agent-88`, at 3.5 h |
| session wall clock | 43,200.1 s (12.00 h), `timed_out: true` | 43,266.3 s (12.02 h), summed across 16 segments |
| continuity | one uninterrupted session, 0 resumes | 16 segments, see Provenance |

Score progression, earliest round to cross each threshold:

| Threshold | `claude-opus-5[1m]` | | | `gpt-5.6-sol` | | |
|---|---|---|---|---|---|---|
| | Round | Score | Elapsed | Round | Score | Elapsed |
| >= 0.50 | `auto-2` | 0.554190 | 1.00 h | `auto-1` | 0.548295 | 0.50 h |
| >= 0.80 | `agent-4` | 0.838023 | 1.34 h | `auto-4` | 0.805050 | 2.08 h |
| >= 0.90 | `auto-4` | 0.914410 | 2.00 h | - | - | not reached |
| >= 0.95 | `agent-14` | 0.953843 | 2.92 h | - | - | not reached |
| >= 0.97 | `agent-49` | 0.971848 | 10.49 h | - | - | not reached |

Both curves are excavation records. The Opus run rose almost vertically - 0.50 by the first hour, 0.90 by 2.00 h, 0.95 by 2.92 h - and then spent the remaining nine hours buying the last 0.018, stratum-by-stratum divergence hunting against the mutated layout decisions. The instruction documents 0.880 as the ceiling for perfect conformance at parity speed; both cohorts crossed it, so both earned throughput credit on top of exact-match conformance.

For reference, the starter tree in `environment/src/` measures 0.0198 on the graded corpus and is the documented floor of this task.

## Provenance

**The `gpt-5.6-sol` trajectory is a merged record, not one continuous session.** Its `final_result.json` carries `merged: true` and a `parts` block naming all 16 segments with their individual runtimes and best scores; `run_history.json` records `merged_from` for every round. During the session the upstream model provider repeatedly returned truncated responses and `response.failed` errors. Each of those exited the agent cleanly, which is not the abnormal exit the harness auto-resumes on, so a supervisor detected the stop and relaunched from the run's best submission via `--seed-archive`. The solver carried across each relaunch; the agent's conversation did not. `runtime_seconds` is the sum of the segments' agent time and excludes the gaps between them. Read the `parts` block for anything that depends on continuity.

**The `opus-5` trajectory is native.** One process, one container, `timed_out: true`, `resume_count: 0`. Nothing about it is reconstructed.

**17 of 248 rounds do not carry the four judge-side artifacts** (`submission.tar.gz`, `test_output.txt`, `run_instance.log`, `allowed_files.txt`): 11 in `opus-5` and 6 in `gpt-5.6-sol`. Every one of them is a byte-identical resubmission, marked by a `DEDUPLICATED.txt` sidecar and a `deduplicated_from` field naming the earlier submission in its `report.json`. The judge returns the cached score without regrading, so no new artifacts are produced. The other 231 rounds carry the complete set.

**The public corpus is not disjoint from the graded corpus.** 65 of the 12,000 graded cases in `tests/hidden_test_data/hidden_cases.jsonl` are exact `(dlt, filter, netmask, optimize, snaplen)` matches of records in the agent-visible `environment/public_cases.jsonl`, and all 65 of those published `expected` values are byte-identical to the graded golden answers in `golden.jsonl`. `instruction.md` states in two places that the two corpora are "generated from disjoint seeds and share no case" and that a lookup table keyed on a case "is worth zero on the graded corpus"; both statements are contradicted by the committed bytes, and `tests/rubrics.jsonl` separately penalizes public-case special-casing under `no_public_case_special_casing`. The overlap spans all eight strata (7 basic-proto, 7 boolean-nesting, 5 byte-slice-arith, 7 error-paths, 11 host-net-addr, 15 link-layer-and-encap, 8 optimizer-only, 5 port-portrange); the maximum free weighted correctness it can supply is C = 0.005417, worth 0.004767 of reward under `R = 0.88*C + ...`. This is the same defect class the predecessor bundle `62b54382` carried at 192 cases, reduced here rather than removed. `instruction.md`, `environment/` and `tests/` are deliberately left unedited: they are the frozen task the two recorded cohorts were graded against, and rewriting them would break correspondence with the trajectories this bundle ships as evidence.

**`best_pass_rate: 0.0` is an artifact, not a result.** The parser is `structured_json`: the verifier writes a continuous reward and there are no pytest cases, so pass rates are zero everywhere and the harness banner is unreliable. The authoritative numbers are the `best_score` fields.

**The `auto-*` rounds are snapshots, not attempts.** The host grades the workspace every 1800 s and withholds the result from the agent. Reading 75 and 173 as independent attempts overstates both runs; 52 and 154 are the agent-initiated counts. A snapshot grades whatever is on disk at the tick, so a round taken mid-edit can score zero without indicating a regression - one such zero appears in each cohort.

**Paths in the `gpt-5.6-sol` record are relative to the repository root.** The merge wrote the authoring host's absolute layout into four files; the prefix was stripped after the run. Only that prefix changed - scores, round ids and the `parts` provenance are as the harness produced them.

**The oracle ships in this bundle.** `solution/` holds the golden trajectory (`TRUTH.md`, canary-tagged), the grading rubrics, and the reference entry point. Anyone holding this directory can reproduce a calibrated result directly, so the task cannot be used to evaluate a model that has had access to it. The authoring-side sources that generated `TRUTH.md` are not shipped.

## Files

```
README.md                   this file
inspector.html              single-file visual report over this bundle
plots/                      score curves per cohort, and score vs submissions
instruction.md              the objective handed to the agent
task.toml                   manifest: budgets, images, network mode, submit paths, selection,
                            mutation provenance (mut1.patch sha256, acceptance-equivalence count)
environment/                the agent-visible starting files and the work container image:
                            starter C11 tree, the 750-case public corpus, local scorer score.sh,
                            docs/CONTRACT.md, pinned name-resolution tables under etc/
tests/                      the judge container: test.sh (the 7-step verifier), scoring/
                            (score.py, similarity.py, validator.py, containment.py),
                            hidden_test_data/ (12,000 cases + golden outputs + fingerprints),
                            rubrics.jsonl (6 trajectory-level conduct rubrics)
solution/                   PRIVATE - the oracle: TRUTH.md golden trajectory
                            (canary-tagged), rubrics.json, solve.sh
trajectories/
  opus-5/                   claude-opus-5[1m], native 12.00 h session: run config, run ledger,
                            host-side state, the raw session stream, final workspace archive
    submissions/            75 graded rounds: 52 agent-initiated (agent-NN) and 23 evaluator
                            snapshots (auto-NN)
  gpt-5.6-sol/              gpt-5.6-sol, 12.02 h across 16 segments (see Provenance)
    submissions/            173 graded rounds: 154 agent-initiated and 19 evaluator snapshots
```
