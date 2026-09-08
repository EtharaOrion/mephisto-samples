Read the complete task instructions in `/home/workspace/task_instruction.md`, and complete the task according to those requirements. The final deliverables must be written to the file paths specified in `task_instruction.md`.

---

# RasterLab: Bit-Exact Cross-Language Rewrite

Reimplement the legacy `rasterlab` raster-processing tool in Rust as a drop-in
replacement for the reference binary.

## What you have

- `/reference/rasterlab-src/` - the complete, readable C99 source of the
  reference implementation (`rasterlab.h`, `rasterlab.c`, `main.c`,
  `Makefile`). Read it, understand it, rewrite it.
- `/reference/rasterlab` - a prebuilt reference binary for local
  experimentation. It will NOT exist at scoring time.
- `/home/workspace/rasterlab.1` - the man page. It documents commands,
  formats, kernels and exit codes only. For exact numeric behaviour, consult
  the source.
- `/home/workspace/public_probes/` - a small public workload set with the
  reference outputs recorded under `public_probes/expected/`.
- `/home/workspace/verify_local.py` - a local checker that runs your candidate
  binary over the public probes and diffs it against the recorded outputs.

## What you must build

A from-scratch Rust crate at `/home/workspace/candidate/` such that:

    cd /home/workspace/candidate && cargo build --release

produces `target/release/rasterlab`, a drop-in replacement for the reference
binary. Byte-identical stdout, byte-identical stderr, identical exit codes,
and byte-identical output `.rlr` container files, on every input.

The crate must build offline with no dependencies outside the Rust standard
library.

## Scoring (0-100)

- **L1 (10)** - candidate builds and matches the public probes.
- **L2 (45)** - bit-exact equivalence on a hidden pixel-workload set
  (conversions, resizes, chains across all formats, kernels and sizes,
  including odd dimensions). ANY mismatch on ANY hidden workload zeroes
  L2, L3 and L4.
- **L3 (15)** - behavioural equivalence on hidden CLI transcripts, including
  malformed inputs and corrupt containers: byte-identical stdout and stderr,
  identical exit codes.
- **L4 (25)** - performance, evaluated only if L2 and L3 are perfect. Score is
  a geometric-mean runtime ratio r = reference_time / candidate_time over
  timed workloads, both binaries built and timed on the scoring host. Each
  timed repetition consumes a fresh input variant and its output is verified
  bit-exact against the reference; a mismatch during timing is scored as a
  hidden bit mismatch. r <= 0.6
  scores 0; the score rises linearly to the full 25 at r >= 1.5. Beating the
  C baseline requires real optimization; portable SIMD via `std::simd` or
  `std::arch` intrinsics is allowed.
- **L5 (5)** - integrity: clean provenance, no forbidden constructs.

Hidden workloads are regenerated fresh from sealed seeds at scoring time.
There is nothing to memorize: outputs you have never seen are recomputed from
the reference source, which is then deleted before your binary runs.

## Hard rules

- Do NOT compile, link, wrap, or invoke the reference implementation or any
  part of its C source from your submission. Your binary is rebuilt from Rust
  source in a clean environment and scanned; violations score 0.
- No inline assembly (`asm!`, `global_asm!`).
- No third-party crates. `cargo build --release --offline` must succeed with
  the standard library only.
- No network access exists in the environment.
- Do not embed recorded outputs or probe answers; hidden workloads differ
  from the public probes.

## Practical notes

- Exact numeric behaviour matters everywhere: fixed-point coefficient tables,
  rounding, clamping, chroma phase offsets, CRC initialization, error-message
  bytes, argument-parsing quirks. Approximations that look correct will fail
  the bit-exact gate.
- `verify_local.py` gives you a fast local signal, but the hidden set is much
  larger and broader than the public probes. Passing the probes is necessary,
  not sufficient.
- Submission is the `candidate/` directory (excluding `target/`).
