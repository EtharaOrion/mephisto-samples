# `120ddda7-c14b-5ba0-9dba-d6e9441cc885` - `libpcap BPF Codegen Fidelity (mutated reference, mut1)`

One model cohort (`anthropic/claude-opus-5[1m]`), one twelve-hour session, 126 graded submissions packaged on one axis.

The task is the mutated sibling of `62b54382-a910-5b29-ad0e-1efa993cc615`: rebuild a **deliberately modified** libpcap 1.10.6 BPF filter compiler in C from observable behaviour alone - no libpcap source, headers, binary, documentation, or network. The reference is not stock libpcap: four deterministic, semantics-preserving mutations (applied by `mut1.patch`, sha256 `f3d5502b...86600`, inside the private authoring image, never shipped) change its code generation and instruction layout choices only, so for most expressions it emits different bytes than upstream while accepting exactly the same packets - measured at 1,889,280 packet evaluations with zero acceptance divergence. Per the private calibration in `solution/TRUTH.md`, the optimized program differs from the unoptimized one on 61.4% of the corpus and 94.4% of the optimizer-only stratum. Recalled upstream bytes are wrong wherever the mutations bite; the departures must be excavated from the 685-record `public_cases.jsonl` (the instruction text calls it the 750 case corpus; the shipped file carries 685 records). Graded on exact cBPF instruction-tuple equality and exact error-string equality against 12,000 hidden `(dlt, snaplen, optimize, netmask, filter)` cases across 8 weighted strata, plus a gated judge-timed compile-throughput term.

```
task                    edgebench/libpcap_bpf_codegen_fidelity_mut1
budget                  43200 s (12 h) agent window, 300 submissions max, 120 s cooldown,
                        1800 s evaluator-only snapshot interval
harness / stack         claude-code · claude-opus-5[1m] · cpp base image · linux/amd64 ·
                        parser structured_json · selection score_first
network                 agent: no-network · verifier: no-network, separate container
verifier                900 s budget · 12,000 hidden cases · 8 public weights, hidden contents ·
                        3,000-case timing subset, 3 warmups + 5 timed trials, interleaved,
                        judge wall clock only
score                   R = clip(0.88·C + 0.12·P·min(1, C/0.25), 0, 1)
                        C: weighted mean over 8 strata; per case: exact tuple sequence or
                        exact error string = 1.00, structurally valid divergence =
                        0.60 · floor-corrected similarity, invalid or missing = 0.00
                        P: clip(ln(r/0.5)/ln(8), 0, 1) with r = (t_up/N_total)/(t_cand/N_exact),
                        byte-exact cases only; dead zone r <= 1.05 scores 0
```

The task files at the top level (`instruction.md`, `task.toml`, `environment/`, `tests/`, `solution/`) are the frozen task exactly as graded. The run's records live under `trajectories/opus-5/`, one directory per submission beneath `submissions/`.

## Session results

| | `claude-opus-5[1m]` |
|---|---|
| submissions packaged | **126** (103 agent-initiated + 23 evaluator-only) |
| submissions scored above zero | 123 |
| selection | `score_first` -> **`agent-102`** |
| best score | **0.953180** |
| final submission score | 0.940774 (`agent-103`) |
| median / mean score | 0.9399 / 0.8946 |
| first graded submission | `auto-1`, 0.019830, at 0.50 h |
| best first reached | `agent-102`, at 11.48 h of 12 h |
| cumulative input-side tokens | 2,029,611,221 * |
| session wall clock | 43,199.8 s (12.00 h), `timed_out: true`, 1 resume |

Score progression, earliest round to cross each threshold:

| Threshold | Round | Score | Elapsed |
|---|---|---|---|
| >= 0.50 | `agent-3` | 0.548849 | 1.00 h |
| >= 0.80 | `agent-6` | 0.801605 | 1.30 h |
| >= 0.90 | `agent-9` | 0.909806 | 1.48 h |
| >= 0.94 | `agent-45` | 0.941083 | 3.60 h |
| >= 0.95 | `agent-102` | 0.953180 | 11.48 h |

The curve is an excavation record. The first nonzero grading is the 0.50 h evaluator snapshot (`auto-1`, 0.019830). Conformance then rose almost vertically: 0.50 by `agent-3` (1.00 h), 0.80 by `agent-6` (1.30 h), 0.90 by `agent-9` (1.48 h), 0.94 by `agent-45` (3.60 h, 0.941083). From there the run is one long tail: the remaining 7.9 hours bought the last 0.012097 of score - stratum-by-stratum divergence hunting against the mutated layout decisions - closing at 0.953180 on `agent-102` about 31 minutes before the clock. Three rounds graded zero: the first two agent submissions (`agent-1` at 0.88 h, `agent-2` at 0.95 h) and one evaluator snapshot (`auto-7` at 3.50 h, sitting between `agent-43` at 0.937520 and `agent-44` at 0.938812 - the snapshot grades whatever is on disk at the tick). The per-round verifier transcripts that would attribute those zeros did not survive the loss of the run directory, so the cause of each zero is not recoverable from this salvage. The session ended on the boundary mid-work (`timed_out: true`), with 1 mid-session resume.

## Provenance: this trajectory was salvaged. Read before quoting anything.

**The original run directory was lost to an infrastructure fault, and this bundle is the rescue.** What survived intact: the complete raw session stream (`agent_output.txt`, 12 MB, 3,680 assistant records), the harness agent log, and the start marker. Everything else at run level was reconstructed 2026-08/2026-09 from rescued harness logs (supervisor score table, judge access log, captured submit responses) and carries an explicit `_recovered` provenance key or header where the format allows. Scores are authoritative: every per-round score was captured from the judge's own responses at run time.

**Four per-round judge artifacts are absent from every submission directory**: the submitted tarball (`submission.tar.gz`), the verifier transcript (`test_output.txt`), the judge container log (`run_instance.log`), and the extracted-file list (`allowed_files.txt`). They were lost with the directory and are not reconstructable from any surviving log. Each round ships `report.json` (recovered score record) and `eval.sh` (invariant judge entry point). A re-run under the renamed task id is scheduled; its bundle will carry the full six-file layout.

**Round timestamps are approximate.** `evolve_state.json` derives each round's `at` from its first appearance in the supervisor's minute-resolution score table, offset from `started_at`. Any time axis built from this bundle inherits that granularity.

**`final_archive.tar.gz` is a replay reconstruction.** The final workspace was rebuilt by replaying the session stream's file operations (Write/Edit tool calls, shell heredocs, python string-replace edits) over the starter tree: 20 files, 199,536 bytes of source vs the 53,923-byte original. Twenty-five `sed -i` commands and 252 opaque python write-blocks could not be replayed, so file contents are approximate; runtime artifacts (`.gcda`) are absent.

**`best_pass_rate: 0.0` is an artifact, not a result.** The parser is `structured_json`: the verifier writes a continuous reward and there are no pytest cases, so pass rates are zero everywhere and the harness banner (`harness_reported_best_pct: 0.0`) is unreliable. The authoritative number is `best_score = 0.953180`.

**The 23 `auto-*` rounds are snapshots, not attempts.** The host grades the workspace every 1800 s and withholds the result from the agent. Reading 126 as independent attempts overstates the run; 103 is the agent-initiated count.

**Token totals are a floor, and the output figure is unusable.** The input-side sum above (364,745 input + 11,361,923 cache-creation + 2,017,884,553 cache-read across 3,680 assistant records) is coherent; the streamed `output_tokens` sum (20,873) is a chunked-logging artifact. No cost is recorded in this bundle.

**The instruction and the shipped public corpus disagree on one count.** `instruction.md` calls it "the 750 case public corpus"; the shipped `environment/public_cases.jsonl` carries 685 records. The graded surface (12,000 hidden cases) is unaffected.

**The task was renamed after this run.** `task.toml` here freezes `name`/`task_id` as `libpcap_bpf_codegen_fidelity_mut1` to keep the mutant and `62b54382` distinct in any registry; the run's internal records predate the rename and carry the original id. The re-run will use the new id end to end.

**The oracle ships in this bundle.** `solution/` holds the generated golden trajectory (`TRUTH.md`, canary-tagged), the checker grounding, and executable recompute tooling. Anyone holding this directory can reproduce a calibrated result directly, so the task cannot be used to evaluate a model that has had access to it.

## Files

```
README.md                   this file
inspect.html                single-file visual report over this bundle
instruction.md              the objective handed to the agent
task.toml                   manifest: budgets, images, network mode, submit paths, selection,
                            mutation provenance (mut1.patch sha256, acceptance-equivalence count)
environment/                the agent-visible starting files and the work container image:
                            starter C11 tree, the public corpus, local scorer score.sh,
                            docs/CONTRACT.md, pinned name-resolution tables under etc/
tests/                      the judge container: test.sh (the 7-step verifier), scoring/
                            (score.py, similarity.py, validator.py, containment.py),
                            hidden_test_data/ (12,000 cases + golden outputs + fingerprints),
                            rubrics.jsonl (6 trajectory-level conduct rubrics)
solution/                   PRIVATE - the oracle: TRUTH.md golden trajectory (generated,
                            canary-tagged), grounding/policy/provenance YAMLs, recompute.py,
                            solve.sh, rubrics.json
trajectories/
  opus-5/                   the single packaged run: run config, run ledger, host-side state,
                            the raw session stream, and the replay-reconstructed final
                            workspace archive (see Provenance)
    submissions/            126 graded rounds, one directory each: 103 agent-initiated
                            (agent-NN) and 23 evaluator-only snapshots (auto-NN). Every
                            directory holds report.json (the recovered score record, the
                            authority for that round) and eval.sh; the four judge-side
                            artifacts are absent pending the re-run (see Provenance)
```
