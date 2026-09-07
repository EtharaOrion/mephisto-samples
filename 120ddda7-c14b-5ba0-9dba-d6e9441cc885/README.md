# `120ddda7-c14b-5ba0-9dba-d6e9441cc885`

Two model cohorts on the same task, the same agent and the same twelve-hour budget.

The task is the mutated sibling of `62b54382-a910-5b29-ad0e-1efa993cc615`: rebuild a **deliberately
modified** libpcap 1.10.6 BPF filter compiler in C from observable behaviour alone - no libpcap
source, headers, binary, documentation, or network. The reference is not stock libpcap. Four
deterministic, semantics-preserving mutations, applied by `mut1.patch` (sha256 `f3d5502b...86600`)
inside the private authoring image and never shipped, change its code generation and instruction
layout choices only, so for most expressions it emits different bytes than upstream while accepting
exactly the same packets - measured at 1,889,280 packet evaluations with zero acceptance
divergence. Recalled upstream bytes are wrong wherever the mutations bite; the departures have to
be excavated from the 750-record `environment/public_cases.jsonl`.

```
task                    edgebench/120ddda7-c14b-5ba0-9dba-d6e9441cc885
                        (task_id libpcap_bpf_codegen_fidelity)
budget                  43200 s (12 h) agent window, 300 submissions max, 120 s cooldown,
                        1800 s evaluator-only snapshot interval
harness / stack         openhands · cpp base image · linux/amd64 ·
                        parser structured_json · selection score_first
cohorts                 claude-opus-5[1m] · gpt-5.6-sol
network                 agent: no-network · verifier: no-network, separate container
containers              work 8 cpu / 6144 MB · judge 4 cpu / 3072 MB, both pinned by @sha256
verifier                900 s budget · 12,000 hidden cases across 8 weighted strata ·
                        weights public, stratum contents hidden
```

Budgets and intervals are read from `trajectories/<cohort>/run_config.json`; images, timeouts,
platform, parser, selection and the mutation provenance from `task.toml`.

## The graded corpus

Eight strata. The eight names and the eight weights are public and fixed; which expressions, link
types and flag combinations fall in each stratum is not. The public corpus is re-stratified toward
cases that expose the reference's departures, so its proportions deliberately do not match the
graded ones.

| stratum | weight | hidden cases | public cases | overlapping (see caveats) |
|---|---|---|---|---|
| basic-proto | 0.10 | 1,200 | 93 | 7 |
| boolean-nesting | 0.16 | 1,920 | 110 | 7 |
| byte-slice-arith | 0.16 | 1,920 | 85 | 5 |
| error-paths | 0.10 | 1,200 | 85 | 7 |
| host-net-addr | 0.12 | 1,440 | 92 | 11 |
| link-layer-and-encap | 0.12 | 1,440 | 91 | 15 |
| optimizer-only | 0.12 | 1,440 | 93 | 8 |
| port-portrange | 0.12 | 1,440 | 101 | 5 |
| **total** | **1.00** | **12,000** | **750** | **65** |

Weights and the per-case stratum map come from `tests/hidden_test_data/manifest.json`; hidden
counts are that map applied to `hidden_cases.jsonl`; public counts are the `stratum` field of
`public_cases.jsonl`. A separate 3,000-case `bench_cases.jsonl` drives the timing term and carries
no golden bytes.

The optimizer is not a corner of this task. `solution/TRUTH.md` records the optimize-on/optimize-off
divergence twice and the two records do not agree: its golden-trajectory table (line 30) says the
optimized program differs from the unoptimized one on **61.4%** of the corpus and **94.4%** of the
optimizer-only stratum, while its measured-anchors prose (line 62) says **60.6%** and **96.7%**.
Both figures are quoted here because the shipped source of truth carries both; neither has been
reconciled, and the file is frozen.

## Scoring

```
R = clip(0.88·C + 0.12·P·min(1, C/0.25), 0, 1)
```

`C` is the weighted mean of per-case scores over the eight strata. Per case, from
`tests/scoring/score.py`:

| outcome | per-case score |
|---|---|
| exact cBPF instruction-tuple sequence | 1.00 |
| rejected with the exact reference error string | 1.00 |
| rejected with a **different** error string | 0.20 |
| returned a program where the reference rejects | 0.00 |
| structurally valid program that diverges | 0.60 × floor-corrected similarity |
| invalid, unparseable or missing | 0.00 |

`P = clip(ln(r/0.5) / ln(4.0/0.5), 0, 1)`, the denominator being `ln(8)`. The ratio is normalized
by exactness rather than taken raw: `r = (t_upstream / N_total) / (t_candidate / N_exact)`, where
`N_exact` counts the exact-program and exact-error cases, and `N_exact = 0` yields `r = 0`. Speed
bought by skipping fidelity therefore earns nothing. The judge measures both binaries itself,
alternating in one run, 3 discarded warmups then 5 timed trials each, medians over the 5, pinned
with `taskset -c 0-3`. There is a dead zone: `r` at or below 1.05 scores `P = 0`.

`instruction.md` documents both ends of the scale. The starter measures `R = 0.0198` and is the
floor. A submission that reproduces the reference exactly on every case but runs at parity speed
measures `C = 1.000`, `P = 0.000`, `R = 0.880` - parity sits inside the dead zone - so any score
above 0.880 necessarily carries throughput credit as well as exact-match conformance.

## Session results

Scores are quoted at the six decimal places `run_history.json` records. Elapsed hours are wall
clock from container start (`started_at`) to the round's `submitted_at`, rounded to two places;
this is the same clock `inspector.html` reports as `t+ minutes`.

| | `claude-opus-5[1m]` | `gpt-5.6-sol` |
|---|---|---|
| submissions packaged | **75** (52 agent-initiated + 23 evaluator-only) | **173** (154 agent-initiated + 19 evaluator-only) |
| submissions scored | 69 | 168 |
| never scored | 6 | 5 |
| selection | `score_first` -> **`agent-49`** | `score_first` -> **`agent-88`** |
| best score | **0.971848** | **0.885184** |
| first graded submission | `auto-1`, 0.019830 (the starter floor) | `auto-1`, 0.548295 |
| best first reached | `agent-49`, at 10.49 h of 12 h | `agent-88`, at 7.51 h |
| session wall clock | 43,200.1 s (12.00 h), `timed_out: true` | 43,266.3 s (12.02 h) of agent time, summed across 16 parts |
| continuity | one native session, `resume_count: 0` | 16 merged parts, 14 recorded reseeds (see Provenance) |

`agent-88` is a merged-record round, so its timing admits two accountings and both are given here.
Wall clock from container start is 7.51 h. Under the agent-time-only accounting the merge itself
uses, `agent-88` lies inside part 7; parts 1-6 sum to 25,376.1 s (7.05 h) and part 7 runs 2,853.6 s,
placing it between 7.05 h and 7.84 h. Neither accounting puts it earlier than 7 h.

Score progression, earliest round to cross each threshold:

| Threshold | `claude-opus-5[1m]` | | | `gpt-5.6-sol` | | |
|---|---|---|---|---|---|---|
| | Round | Score | Elapsed | Round | Score | Elapsed |
| >= 0.50 | `auto-2` | 0.554190 | 1.00 h | `auto-1` | 0.548295 | 0.50 h |
| >= 0.80 | `agent-4` | 0.838023 | 1.34 h | `auto-4` | 0.805050 | 2.08 h |
| >= 0.90 | `auto-4` | 0.914410 | 2.00 h | - | - | not reached |
| >= 0.95 | `agent-14` | 0.953843 | 2.92 h | - | - | not reached |
| >= 0.97 | `agent-49` | 0.971848 | 10.49 h | - | - | not reached |

Both curves are excavation records. The Opus run rose almost vertically - 0.50 by the first hour,
0.90 by 2.00 h, 0.95 by 2.92 h - and then spent the remaining nine hours buying the last 0.018,
stratum-by-stratum divergence hunting against the mutated layout decisions. Both cohorts finished
above 0.880, so both earned throughput credit on top of exact-match conformance.

## Calibration

Controls recorded in `solution/TRUTH.md`, measured on AMD Ryzen AI 9 365, x86_64 native, 20 threads,
22 GiB RAM on 2026-08-13 and re-measured against the mutated oracle the same day. These are that
file's recorded measurements, reproduced here; they were not re-run for this bundle.

| Control | Result |
|---|---|
| empty submission | R = 0.000000, reason `empty_submission` |
| shipped starter (`environment/src/`) | R = 0.019830, C = 0.022535, P = 0.0, N_exact = 0 |
| pinned upstream shim | C = 1.000000 |
| hard-kill line for the starter | 0.12 |

Anti-shortcut calibration, normalized 5-gram containment against the pinned upstream sources. The
scan fires at or above 0.15 and excludes string literals, because exact error-text fidelity is a
graded obligation and a scan that counted error strings would fire hardest on correct submissions.

| Calibration point | Containment | Fires |
|---|---|---|
| shipped starter | 0.0600 | no |
| verbatim upstream copy | 0.9481 | yes |
| copy with identifiers renamed | 0.7381 | yes |
| upstream error strings only, no code | 0.0976 | no |

## Provenance

**The two cohorts are comparable on the task but not on continuity.** They ran the same agent
against the same task with the same prompt and driver: `agent_prompt.md`, `_openhands_driver.py`
and `_sforge-submit.sh` are byte-identical across the two directories (`agent_prompt.md` sha256
`2a905841...f16aa7`), and both `run_config.json` files carry the same 43200 s timeout, 1800 s eval
interval, 300 submission cap, 120 s cooldown and `internet: false`. They differ in more than the
model. `opus-5` is one native twelve-hour session in one container. `gpt-5.6-sol` is 16 merged
parts with 14 recorded reseeds and a fresh container, fresh installed state and fresh model context
at each boundary. Read the pair as two runs of one task, not as a controlled single-variable
comparison.

**The `gpt-5.6-sol` trajectory is a merged record, not one continuous session.** Its
`final_result.json` carries `merged: true`, `merged_by: scripts/merge_runs.py`, `merged_at:
2026-09-07T06:33:19` and a `parts` block naming all 16 segments with their individual runtimes and
best scores; `run_history.json` carries `merged_from` on every one of its 173 entries. During the
session the upstream model provider repeatedly returned truncated responses and `response.failed`
errors - `agent_output.txt` records 12 occurrences of `response.failed`. Each exited the agent
cleanly, which is not the abnormal exit the harness auto-resumes on, so a supervisor detected the
stop and relaunched, seeding the fresh container from an earlier submission archive. What the log
actually records is 14 `Seeded 13 file(s) into /home/workspace/bpfc from
.../submissions/<round>/submission.tar.gz` events across 15 relaunch boundaries, so one relaunch
has no recorded seed. The seed is usually the best submission so far - 9 of the 14 name part 7's
`agent-9`, the run's best at 0.885184 - but not always: the reseed at 21:19:00 took part 2's
`auto-4` (0.814729) while that part's best was `agent-10`, merged as `agent-12` (0.815846). The
solver carried across each relaunch; the agent's conversation did not. `runtime_seconds` is the sum
of the parts' agent time and excludes the gaps between them. Read the `parts` block for anything
that depends on continuity.

**The `opus-5` trajectory is native.** One process, one container, `timed_out: true`,
`resume_count: 0`, no seed file. Nothing about it is reconstructed.

**17 of 248 rounds do not carry the four judge-side artifacts** (`submission.tar.gz`,
`test_output.txt`, `run_instance.log`, `allowed_files.txt`): 11 in `opus-5` and 6 in
`gpt-5.6-sol`. Every one of them is a byte-identical resubmission, marked by a `DEDUPLICATED.txt`
sidecar and a `deduplicated_from` field naming the earlier submission in its `report.json`. The
judge returns the cached report without regrading, so no new artifacts are produced. That cached
report carries a score in 13 of the 17 cases; the remaining 4 (`opus-5/auto-18`, `opus-5/auto-19`,
`opus-5/agent-47`, `gpt-5.6-sol/agent-111`) point at source submissions that were themselves never
scored, so they inherit `score: null` - and, because the whole report is copied, the source's
`timed_out: true` and its ~900 s `runtime_seconds` as well. Those four did not run the verifier at
all; counting timeouts from `report.json` alone would double-count them. The other 231 rounds carry
the complete set.

**11 of 248 rounds were never scored** - 6 in `opus-5`, 5 in `gpt-5.6-sol`. Four are the
dedup-inherited nulls above. The other **seven exhausted the 900 s verifier budget**: their
`report.json` carries `timed_out: true` with `runtime_seconds` of 900.1 to 900.2, and their
`test_output.txt` stops mid-run at `bash /tmp/harbor_test.sh` with no verdict line, because the
judge was killed at the wall clock before it could write one. They are `opus-5/agent-44`,
`opus-5/agent-46`, `opus-5/agent-52`, `gpt-5.6-sol/agent-110`, `gpt-5.6-sol/agent-112`,
`gpt-5.6-sol/agent-116` and `gpt-5.6-sol/auto-17`. A never-scored round is an absent measurement,
not a zero.

**Each cohort has exactly one zero, and they have different causes.** `opus-5/auto-15` is a
snapshot that caught the tree mid-refactor: reason `build_failed`, `make exited 2`, with
`src/parse.c:1255: error: 'pstate' has no member named 'depth'` and `make: *** [Makefile:54:
src/parse.o] Error 1`. That is the failure mode the snapshot mechanism produces - it grades whatever
is on disk at the tick - and it indicates nothing about the run's trajectory.
`gpt-5.6-sol/agent-2` is not a snapshot but an agent-initiated submission that built and then
failed on the graded run: reason `malformed_output`, detail `candidate exited 139: timeout: the
monitored command dumped core`, with `Segmentation fault` on the runner line.

**The `auto-*` rounds are snapshots, not attempts.** The host grades the workspace every 1800 s and
withholds the result from the agent. Reading 75 and 173 as independent attempts overstates both
runs; 52 and 154 are the agent-initiated counts.

**`best_pass_rate: 0.0` is an artifact, not a result.** The parser is `structured_json`: the
verifier writes a continuous reward and there are no pytest cases, so pass rates are zero everywhere
and the harness banner is unreliable. The authoritative numbers are the `best_score` fields.

**The public corpus is not disjoint from the graded corpus.** 65 of the 12,000 graded cases in
`tests/hidden_test_data/hidden_cases.jsonl` are exact `(dlt, filter, netmask, optimize, snaplen)`
matches of records in the agent-visible `environment/public_cases.jsonl`, and all 65 of those
published `expected` values are byte-identical to the graded golden answers in `golden.jsonl`.
`instruction.md` states in two places that the two corpora are "generated from disjoint seeds and
share no case" and that a lookup table keyed on a case "is worth zero on the graded corpus"; both
statements are contradicted by the committed bytes, and `tests/rubrics.jsonl` separately penalizes
public-case special-casing under `no_public_case_special_casing`. The overlap spans all eight
strata, per the last column of the corpus table above; the maximum free weighted correctness it can
supply is C = 0.005417, worth 0.004767 of reward under `R = 0.88*C + ...`. This is the same defect
class the predecessor bundle `62b54382` carried at 192 cases, reduced here rather than removed.
`instruction.md`, `environment/` and `tests/` are deliberately left unedited: they are the frozen
task the two recorded cohorts were graded against, and rewriting them would break correspondence
with the trajectories this bundle ships as evidence.

**Paths in the `gpt-5.6-sol` record are relative to the repository root.** The merge wrote the
authoring host's absolute layout into four files - `run_agent.log`, `run_history.json`,
`final_result.json` and `evolve_state.json` - and the prefix was stripped after the run. Only that
prefix changed; scores, round ids and the `parts` provenance are as the harness produced them.

**`solution/` was reduced after the freeze.** Four authoring-side files - `grounding.yaml`,
`policy.yaml`, `provenance.yaml` and `recompute.py` - were removed from this bundle, so `solution/`
is no longer the directory the authoring pipeline produced. Two of them are still referenced from
files that remain: `solution/TRUTH.md` line 3, `solution/solve.sh` line 3, `solution/rubrics.json`
(`_source_of_truth`) and `tests/test_output.py` line 2 all name `solution/grounding.yaml`, and
`TRUTH.md` additionally names `solution/recompute.py`. Those references are dangling. The four
files are frozen as graded and have not been edited to repair them.

## Files

```
README.md                   this file
inspector.html              single-file visual report over this bundle
plots/
  opus-5.svg                opus-5 alone
  gpt-5.6-sol.svg           gpt-5.6-sol alone
  score_vs_submissions.svg  both cohorts on one axis
instruction.md              the objective handed to the agent
task.toml                   manifest: budgets, images pinned by digest, network mode, container
                            limits, submit paths, selection, and the mutation provenance
                            (mut1.patch sha256, acceptance-equivalence count)
environment/                the agent-visible starting files and the work container image
  Dockerfile                the work image
  Makefile                  builds the starter with -std=c11
  src/                      starter C11 tree: main.c, parse.c, codegen.c, jsonio.c,
                            bpf_defs.h, filter.h, jsonio.h
  include/README.md         placeholder for agent-authored headers
  public_cases.jsonl        the 750-case public corpus, with golden outputs and stratum labels
  score.sh                  local scorer the agent runs against the public corpus
  docs/CONTRACT.md          the byte-level JSON invocation contract
  etc/                      pinned name-resolution tables: ethers, hosts, networks,
                            protocols, services
tests/                      the judge container
  Dockerfile                the judge image
  test.sh                   the verifier, eight numbered steps (STEP 0 assets resolve,
                            1 submission present, 2 containment on the submitted tree,
                            3 rebuild from source, 4 import denylist, 5 graded run
                            unprivileged, 6 judge-measured timing, 7 score as root)
  scoring/                  score.py, similarity.py, validator.py, containment.py
  hidden_test_data/
    hidden_cases.jsonl      12,000 graded inputs
    golden.jsonl            12,000 golden outputs (10,800 programs, 1,200 error strings)
    bench_cases.jsonl       3,000 timing-subset cases, no golden bytes
    manifest.json           per-case stratum map, the 8 weights, seed, oracle image
    upstream_fingerprints.json  31,595 truncated 5-gram digests over 5 upstream files,
                            carrying no upstream text
    REPS                    timing repetition count (20)
  rubrics.jsonl             6 trajectory-level conduct rubrics
  test_output.py            advisory output-shape probe
solution/                   PRIVATE - the oracle
  TRUTH.md                  golden trajectory, rejected routes, measured anchors (canary-tagged)
  rubrics.json              the grading rubrics
  solve.sh                  the reference entry point
trajectories/<cohort>/      one directory per cohort: opus-5, gpt-5.6-sol
  run_config.json           the run as configured: model, timeouts, caps, endpoints
  run_history.json          the round ledger: one entry per submission, in submission order
  final_result.json         the run as it ended: best_score, best_round, counts, runtime,
                            and for gpt-5.6-sol the merge block and 16 parts
  evolve_state.json         host-side selection state
  started_at                container start, ISO timestamp and epoch
  agent_prompt.md           the prompt handed to the agent (identical across cohorts)
  agent_output.txt          the raw session stream
  run_agent.log             host-side driver log, including the reseed events
  auto_eval_ticks.log       one `submitted` line per 1800 s evaluator snapshot: 23 in opus-5,
                            19 in gpt-5.6-sol, whose file also carries the merge part banners
  install_output.txt        work-container setup transcript
  final_archive.tar.gz      the final workspace
  _openhands_driver.py      the driver (identical across cohorts)
  _sforge-submit.sh         the in-container submit tool (identical across cohorts)
  _openhands_stophook.json  stop-hook configuration
  _seed_files.txt           the 13 paths seeded on relaunch (gpt-5.6-sol only)
  submissions/<round>/      report.json, and for non-deduplicated rounds submission.tar.gz,
                            test_output.txt, run_instance.log, allowed_files.txt, eval.sh;
                            deduplicated rounds carry report.json and DEDUPLICATED.txt only
```

`opus-5/submissions/` holds 75 rounds, 52 agent-initiated (`agent-NN`) and 23 evaluator snapshots
(`auto-NN`). `gpt-5.6-sol/submissions/` holds 173, 154 agent-initiated and 19 snapshots. The
directory names and the `round` fields in `run_history.json` are the same set in both cohorts.

Plots are drawn from `trajectories/<cohort>/run_history.json` -> `entries[]` in array order, which
is the true submission order. Filled dots are agent-initiated submissions, hollow dots are
evaluator-only snapshots, enlarged dots mark a new best, and the staircase is best-so-far. Only
scored rounds are plotted: the 11 never-scored rounds carry no point, so `opus-5.svg` draws 48
filled and 21 hollow dots against an axis that runs to 75, and `gpt-5.6-sol.svg` draws 150 filled
and 18 hollow against an axis that runs to 173. A gap in the dots is a missing measurement, not a
drop to zero.

**The oracle ships in this bundle.** `solution/` holds the golden trajectory (`TRUTH.md`,
canary-tagged), the grading rubrics and the reference entry point. Anyone holding this directory
can reproduce a calibrated result directly, so the task cannot be used to evaluate a model that has
had access to it. `instruction.md`, `environment/` and `tests/` are the frozen task exactly as the
two recorded cohorts were graded against it. The authoring-side sources that generated `TRUTH.md`
are retained privately and are not part of this bundle.
