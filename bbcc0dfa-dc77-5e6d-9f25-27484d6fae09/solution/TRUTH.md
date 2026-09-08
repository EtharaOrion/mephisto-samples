<!-- GENERATED SECTION. DO NOT HAND-EDIT. -->
<!-- Source of truth: solution/grounding.yaml via solution/recompute.py -->
# TRUTH - p9iota_latticestore_workspace_reconstruction

## Scoring lanes

| Lane | Max | Rule |
| --- | --- | --- |
| L1_build_surface_conformance | 10 | 4.0 points when `cargo build --release --offline` succeeds for the submitted workspace and produces target/release/lattice, plus 6.0 times the fraction of the 30 public workloads whose full record (every step transcript plus the final store_state digest) is byte-identical to the freshly built reference run inside the judge container. |
| L2_hidden_layered_equivalence | 45 | Hidden workloads are regenerated fresh from sealed seeds at verify time and run against reference and candidate binaries. Points are awarded all-or-nothing per layer only when every hidden workload in the layer matches the reference on the full record including the store_state digest: layer_core (basic plus boundary families) 18 points, layer_dedupe_multi (dedupe plus multi) 9 points, layer_corrupt 9 points, layer_recovery 9 points. |
| L3_cli_transcript_equivalence | 15 | 15 points all-or-nothing when every hidden workload's binary-step transcript fields (op, exit, stdout_sha256, stdout_len, normalized stderr, out_sha256, out_len) are byte-identical to the reference for the identical workload id set. |
| L4_performance_ratio | 25 | Gated on perfect L2 (45) and L3 (15). Three perf specs (perf_put_stream, perf_put_dedupe, perf_get, 16 MiB corpora) are timed for 3 repetitions each with fresh per-repetition inputs keyed '{spec_id}|rep{n}'. r = geometric mean over specs of reference_median_seconds / candidate_median_seconds. Score 0 at r <= 0.6, then 25 * (r - 0.6) / 0.9 linearly, capped at 25 at r >= 1.5. Timed-repetition transcripts are also compared to the reference; any divergence triggers kill_band_bit_mismatch. |
| L5_integrity | 5 | 5 points when the submission contains no canary tokens, no forbidden patterns (asm!, global_asm!, /reference, reference-src, reference-bin), no symlinks, no third-party dependencies in any workspace Cargo.toml, no build.rs, no .cargo config, and total source under 32 MiB. |

## Kill bands

| Id | Condition | Effect |
| --- | --- | --- |
| kill_band_bit_mismatch | During the gated performance lane, after full L2 and L3 equivalence has already been established, a candidate timed-repetition transcript diverges from the reference. This is an anti timing-cache guard that catches a binary returning fast wrong output only while being timed. | L2 and L3 are zeroed and L4 is not awarded, so the total falls back to L1 + L5 (at most 15). Ordinary hidden divergence outside the timed perf lane does not trip this band; it forfeits only the affected per-layer L2 points and, if any hidden transcript differs, all of L3. |
| kill_band_canary | Any canary token from tests/canary_tokens.json appears in the submitted workspace bytes. | Total score 0 and CANARY_TOKEN_IN_SUBMISSION escalation. |
| kill_band_wrap | Submitted code invokes, wraps, links, or reads the frozen reference binary or its artifacts at runtime, or embeds forbidden patterns (asm!, global_asm!, /reference, reference-src, reference-bin). | Total score 0. |

## Environment gate

tests/verify.py aborts with INVALID_ENVIRONMENT unless running on native x86_64; the judge image sets LATTICE_ALLOW_EMULATION=1 so development scoring on ARM hosts remains possible, in which case L4 timing is not valid pilot evidence. Signed pilots run on native Intel x86_64 hosts per seed/pilot.yaml where the override is a no-op.

## Golden trajectory

- T1: Read SPEC.md, the doc comments across all seven crates, and the C chunker reference; build the stripped workspace to enumerate todo!() stubs. Yields: complete inventory of the 50 production functions to reconstruct.
- T2: Recover the gear chunker boundary rule by probing the /reference/lattice binary and reproduce it bit-exact using wrapping u64 arithmetic and validate spans against the latchunk binary on generated corpora. Yields: lattice-chunk green including public tests.
- T3: Implement lattice-codec (canonical LEB128, zigzag, delta, CRC32 IEEE) against the documented check values. Yields: codec primitives every upper crate depends on.
- T4: Implement lattice-index and lattice-log byte formats exactly as documented including CRC trailers and durable-prefix replay. Yields: deterministic on-disk index and journal.
- T5: Implement lattice-store put/get/verify/stats plus recovery with the committed-set manifest sweep, pack truncation, and no index rebuild. Yields: byte-identical store state on all workload families.
- T6: Implement lattice-cli argument handling and exact output literals and exit codes; validate with verify_local.py against the 30 public probes. Yields: 30/30 public probes matching.
- T7: Profile put and get paths and optimize (buffer reuse, single-pass hashing) to hold the perf ratio at or above the reference. Yields: full L4 after perfect L2 and L3.

## Rejected routes

- wrap or invoke the frozen /reference/lattice binary at runtime. Control: wrapper_submission
- hardcode recorded public probe outputs and replay them. Control: probe_memorizing_stub
- submit an empty or non-building workspace for partial credit. Control: empty_submission

## Controls

- negative empty_submission: no workspace directory is submitted. Expected: INTEGRITY_VIOLATION with total score exactly 0.
- negative wrapper_submission: a workspace whose lattice-cli main simply executes /reference/lattice and forwards argv. Expected: kill_band_wrap fires with total score 0.
- negative probe_memorizing_stub: a workspace that hardcodes replies for the public probes and panics on anything else. Expected: no hidden layer pays out and L3 is forfeit because the freshly regenerated hidden workloads diverge, so the total is bounded by L1 + L5 (at most 15) through the lane structure alone with no kill band raised. The verbatim stripped workspace, which panics on every probe, scores L1 4.0 plus L5 5.0 equal to 9.0 with empty kill_bands.
- positive oracle_workspace: solution/solve.sh stages the complete reference workspace. Expected: total score inside self_score_target_band [80, 95].

## Oracle

35 unit tests plus the public test subset all pass; the Rust chunker was cross-checked bit-exact against the C reference on 10 keyed corpora; the public split was run twice through the oracle binary with byte-identical outputs. Self-score target band: [80, 95].

Canary: CANARY-17bf13d5d269a708a777eb4e0f31db34
