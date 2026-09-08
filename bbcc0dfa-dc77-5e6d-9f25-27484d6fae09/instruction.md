
---

# LatticeStore: Spec-Contract Reconstruction of a Content-Addressed Multi-Crate Rust Workspace

Reconstruct every missing implementation in the LatticeStore Rust workspace so that the rebuilt `lattice` CLI is behaviorally indistinguishable, byte for byte, from the frozen reference implementation on hidden workloads, then optionally beat its performance. The exact on-disk encodings are deliberately withheld from the written specification: you recover them by probing a stripped reference binary and inspecting the bytes it writes.

## What you have

- `/home/workspace/workspace/` is a seven-crate Cargo workspace (`lattice-types`, `lattice-chunk`, `lattice-codec`, `lattice-index`, `lattice-log`, `lattice-store`, `lattice-cli`) in which production function bodies have been replaced with `todo!()`. Type signatures, trait bounds, and public item declarations are preserved and are normative. Every crate must be implemented, including `lattice-types` (hashing, hex, error formatting). Some constants in the sources are deliberate placeholders (for example zeroed integers or empty byte arrays) that you must replace with the real values you recover from the reference.
- `/home/workspace/SPEC.md` specifies required behavior, operations, invariants, and the command-line contract. It intentionally withholds exact byte layouts, magic markers, numeric constants, checksum polynomials, and chunker parameters. You recover those by experiment.
- `/reference/lattice` is a stripped, prebuilt reference CLI binary and is your executable ground truth. Run it on inputs you construct and inspect the store files it writes to recover every exact encoding, magic marker, field order, checksum placement, chunker boundary rule, dedup formatting, CLI literal, and exit code. It will NOT exist in the scoring environment, and submitted code that invokes, wraps, links, or reads it scores zero.
- `/home/workspace/public_probes/` holds 30 public workloads whose expected final store-state digests are recorded under `expected/_transcript.json`, and `/home/workspace/verify_local.py` replays your build's store state against them. This is a coarse check: it compares only the final store state, not command stdout, stderr, or exit codes, and it is a non-covering subset. Passing it is necessary but far from sufficient.

## What you must build

- Complete every `todo!()` body across all seven crates, and fill in every placeholder constant, so that `cargo build --release --offline` succeeds from `/home/workspace/workspace/` and the resulting `workspace/target/release/lattice` binary satisfies the full behavioral and byte contract.
- The store your binary produces must be byte-identical to the reference store for any workload: same metadata, pack bytes, manifests, index, journal, recovery behavior after crashes, and corruption diagnostics with exact error literals and exit codes.
- Use only the Rust standard library. No third-party crates anywhere in the workspace, no `build.rs`, no `.cargo` config, no inline assembly.

## Scoring (0-100)

- L1 Build and surface conformance (10): 4.0 for a clean `cargo build --release --offline`, plus 6.0 times the fraction of public workloads whose final store state matches the reference.
- L2 Hidden layered equivalence (45, all or nothing per layer): hidden workloads are grouped into layer_core (18), layer_dedupe_multi (9), layer_corrupt (9), and layer_recovery (9). A layer pays out only if every hidden workload in it matches the reference exactly, including the final store-state digest.
- L3 Hidden CLI transcript equality (15, all or nothing): every hidden workload step must match the reference on exit code, stdout hash and length, normalized stderr, and output-file hash.
- L4 Performance ratio (25): only graded when L2 and L3 are both perfect. r is the geometric mean over perf specs of reference median time divided by candidate median time across 3 timed repeats on fresh per-repeat inputs. r at or below 0.6 scores 0, rising linearly to the full 25 at r of 1.5 or above.
- L5 Integrity (5): no canary tokens, no forbidden patterns, no symlinks, no third-party dependencies, no `build.rs` or `.cargo`, and a source tree under 32 MiB.
- L2 is per-layer all or nothing, so a submission that clears no hidden layer earns zero on L2, forfeits L3, and cannot reach the gated L4, leaving at most L1 plus L5 equal to 15 even if every public probe matched; partial reconstruction earns the layers it clears (18, 27, or 36). Wrapping or invoking the reference binary from submitted code, or embedding recorded outputs, zeroes the entire score.
- Hidden workloads are regenerated fresh from sealed seeds at scoring time. There is nothing to memorize.

## Hard rules

- Do not compile, link, wrap, invoke, or read `/reference/lattice` or any reference artifact from submitted code. It is a development aid only and is absent at scoring.
- Do not use inline assembly, third-party crates, `build.rs`, or `.cargo` configuration anywhere in the workspace.
- Do not embed recorded workload outputs or transcript fragments; hidden workloads are regenerated from sealed seeds, so memorization scores zero and trips integrity scans.
- No network access at any point.

## Practical notes

- Exact byte behavior matters everywhere: gear-table derivation and boundary arithmetic in the chunker, integer encoding canonicality, checksum choice and placement, chunk-record offsets in the pack, manifest ordering, index sorting and refcounting, journal framing and record tags, recovery sweep order, integer-math dedup-ratio formatting, and every CLI literal and exit code. None of these values are written down; construct inputs, run `/reference/lattice`, and hexdump the store it produces to recover them.
- `python3 verify_local.py` replays the 30 public probes against your build and reports how many final store states match. It checks store state only and is a coarse, non-covering aid; the hidden set is five times larger and exercises corruption and crash-recovery paths more aggressively.
- Your submission is the `workspace/` directory excluding `workspace/target/`.
