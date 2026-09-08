# bbcc0dfa-dc77-5e6d-9f25-27484d6fae09

Reconstruct every stripped implementation in LatticeStore, a seven-crate content-addressed
storage workspace in Rust, so the rebuilt `lattice` CLI is byte-identical to a frozen reference
binary on hidden regenerated workloads — then optionally beat its performance. The exact on-disk
encodings are deliberately withheld from the written specification: the agent recovers them by
probing a stripped reference binary and hexdumping the bytes it writes.

## The workspace

`/home/workspace/workspace/` is a seven-crate Cargo workspace — `lattice-types`, `lattice-chunk`,
`lattice-codec`, `lattice-index`, `lattice-log`, `lattice-store`, `lattice-cli` — in which every
production function body has been replaced with `todo!()`. Type signatures, trait bounds and
public item declarations are preserved and normative. Some constants are deliberate placeholders
(zeroed integers, empty byte arrays) whose real values must be recovered from the reference.

- `SPEC.md` specifies behavior, operations, invariants and the CLI contract, but intentionally
  withholds byte layouts, magic markers, checksum polynomials and chunker parameters.
- `/reference/lattice` is a stripped, prebuilt reference CLI — the executable ground truth.
  It is absent in the scoring environment; submitted code that invokes, wraps, links or reads it
  scores zero.
- 30 public workloads under `public_probes/` with recorded final store-state digests, replayed
  by `verify_local.py` — a coarse, non-covering check of store state only.

Only the Rust standard library is allowed: no third-party crates, no `build.rs`, no `.cargo`
config, no inline assembly.

## Scoring

100 points across five lanes:

| Lane | Points | Measures |
|---|---|---|
| L1 | 10 | clean `cargo build --release --offline` (4.0) + fraction of public workloads matching (6.0) |
| L2 | 45 | hidden layered equivalence — all-or-nothing per layer: core (18), dedupe/multi (9), corrupt (9), recovery (9) |
| L3 | 15 | hidden CLI transcript equality — exit codes, stdout hash/length, normalized stderr, output-file hashes (all-or-nothing) |
| L4 | 25 | performance ratio vs the reference, gated on perfect L2 and L3; geometric mean over perf specs, full marks at r >= 1.5 |
| L5 | 5 | integrity — no canaries, forbidden patterns, symlinks, third-party deps, `build.rs`, `.cargo`; source tree under 32 MiB |

Hidden workloads are regenerated fresh from sealed seeds at scoring time, so there is nothing to
memorize — embedding recorded outputs zeroes the score. Exact byte behavior matters everywhere:
gear-table derivation, integer encoding canonicality, checksum choice and placement, pack-record
offsets, manifest ordering, index sorting and refcounting, journal framing, recovery sweep order,
dedup-ratio formatting, and every CLI literal and exit code.

## Submission loop

The submission is the `workspace/` directory (excluding `workspace/target/`), packaged by
`sforge-submit` and graded in a separate judge container with a 2-hour verifier budget. The agent
works under a 12-hour envelope with no network access; the score is a single scalar in [0, 1],
maximized, first-score selection.

## Layout

```
task.toml                    task contract; work and judge images pinned by digest
instruction.md               agent-facing specification
environment/                 work image: Dockerfile, stripped workspace, SPEC.md,
                             reference binary, public probes, local verifier
tests/                       judge image: Dockerfile, verify.py, run_workloads.py,
                             workload_generator.py, reference-src, canary_tokens.json, test.sh
solution/                    private oracle tree: TRUTH.md, oracle-workspace,
                             grounding.yaml, policy.yaml, provenance.yaml,
                             recompute.py, rubrics.json, solve.sh
```

The task is fully synthetic original work with no upstream lift.
