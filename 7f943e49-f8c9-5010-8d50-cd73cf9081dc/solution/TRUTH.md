GENERATED SECTION. DO NOT HAND-EDIT.

Source of truth: solution/grounding.yaml via solution/recompute.py.

# TRUTH - p8theta_rasterlab_bitexact_rewrite

## Scoring lanes

| Lane | Max | Rule |
| --- | --- | --- |
| L1_build_surface_conformance | 10 | 4.0 points for a clean `cargo build --release --offline` producing candidate/target/release/rasterlab; plus 6.0 * (matched / total) over the fresh public split transcript comparison. |
| L2_bitexact_hidden_workloads | 45 | 45.0 iff every hidden pixel-family workload (convert, resize_up, resize_down, chain, perf) matches the reference transcript on all compared fields; any mismatch fires kill_band_bit_mismatch and zeroes L2, L3 and L4. |
| L3_cli_behavioral_equivalence | 15 | 15.0 iff every hidden CLI-family workload (metadata, errors) matches on exit code, stdout bytes and normalized stderr; shares the L2 kill band. |
| L4_performance_ratio | 25 | Evaluated only when L2 and L3 are both full. r = geometric mean of (reference_median / candidate_median) over the hidden perf specs, 3 timed repeats each, median per side. Each repeat consumes a fresh rep-seeded input variant (same format, dims, pattern; key '{seed}|perfrep|{rep}') so cross-rep output caching is useless, and every timed candidate output is compared field-for-field against the reference output for the same variant; any timed-rep mismatch fires kill_band_bit_mismatch. Score = 0 for r <= 0.6, linear 25 * (r - 0.6) / 0.9 on (0.6, 1.5), capped at 25. |
| L5_integrity | 5 | 5.0 iff the integrity scan is clean: no canary tokens, no forbidden patterns (asm!, global_asm!, /reference, rasterlab-src), no symlinks, no third-party or build dependencies, no build.rs, no .cargo config, total source under 32 MiB. |

## Kill bands

| Id | Condition | Effect |
| --- | --- | --- |
| kill_band_bit_mismatch | any hidden-workload field mismatch | L2 = L3 = L4 = 0; structural score cap = L1 + L5 <= 15 |
| kill_band_canary | canary token found in submission bytes | total score 0; BLOCK:INVALID_TASK escalation |
| kill_band_wrap | forbidden pattern (inline asm or reference wrap/invoke) | total score 0 |

## Environment gate

Verifier aborts before scoring with zero_score_reason INVALID_ENVIRONMENT when the host is not native x86_64 or shows ARM /proc/cpuinfo markers, unless RASTERLAB_ALLOW_EMULATION=1. A confounded performance score is never emitted.

## Golden trajectory

- **T1_read_reference_source**: study /reference/rasterlab-src (rasterlab.h, rasterlab.c, main.c) for exact integer semantics
  - yields: RL-92 matrices, kernel weight formulas, rounding, CRC init, error-message bytes
- **T2_container_codec**: implement .rlr reader/writer with exact error precedence and CRC
  - yields: info/checksum commands pass public metadata probes
- **T3_colorspace_hub**: implement RGB24 hub conversion with alpha-drop quirk and chroma box filters
  - yields: convert family bit-exact
- **T4_resample_kernels**: implement map_pos + point/tent/cubic4 with centre-tap renormalisation and phase offsets
  - yields: resize and chain families bit-exact
- **T5_cli_surface**: mirror argument parsing, message bytes and exit codes from main.c
  - yields: errors/metadata families byte-identical
- **T6_hidden_validation**: run verify_local.py until 34/34, then stress with self-generated random workloads vs dev binary
  - yields: confidence against fresh hidden regeneration
- **T7_simd_optimization**: vectorize hot paths (resample inner loops, colorspace) with std::simd/std::arch, preserving exact integer results
  - yields: L4 performance ratio above scalar parity

## Rejected routes

- hardcode recorded public-probe outputs -> named control `probe_memorizing_stub`
- wrap or invoke the reference binary -> named control `wrapper_submission`
- submit the unmodified stub -> named control `empty_submission`

## Controls

- negative `empty_submission`: unmodified candidate stub (exits 2 unconditionally); expected build succeeds, every probe mismatches, hidden kill band fires, total <= 15, effectively ~9
- negative `wrapper_submission`: candidate that shells out to /reference/rasterlab; expected integrity scan finds '/reference' pattern, kill_band_wrap, total 0
- negative `probe_memorizing_stub`: candidate hardcoding recorded public-probe outputs; expected public probes pass, hidden workloads mismatch, kill band caps total at L1 + L5 <= 15
- positive `oracle_port`: solution/oracle-rust submitted via solve.sh; expected all lanes full except L4 depends on host; target band [95, 100]

## Oracle

Bit-exact against the reference C implementation on 286/286 workloads across dev (64), public (34) and hidden (188) splits: every compared field identical (exit, stdout_sha256, stdout_len, normalized stderr, out_sha256, out_len). Zero mismatches.

Self-score target band: [95, 100].
