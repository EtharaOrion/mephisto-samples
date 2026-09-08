# 7f943e49-f8c9-5010-8d50-cd73cf9081dc

Reimplement the legacy `rasterlab` fixed-point raster-processing tool in Rust as a drop-in
replacement for the C99 reference binary: byte-identical stdout, stderr and exit codes, and
bit-exact `.rlr` container outputs on hidden workloads, with a performance lane timed against
the C reference rebuilt on the scoring host.

## The task

The agent receives the complete, readable C99 source of the reference implementation
(`rasterlab.h`, `rasterlab.c`, `main.c`, `Makefile`), a prebuilt reference binary for local
experimentation (absent at scoring time), the man page, a public probe set with recorded
reference outputs, and a local checker (`verify_local.py`). From these it must produce a
from-scratch Rust crate at `/home/workspace/candidate/` that builds offline with
`cargo build --release` using only the Rust standard library.

Exactness is the core difficulty: the pipeline is fixed-point, so every rounding decision,
kernel evaluation, resize path and container byte must be reproduced exactly across all
formats, kernels and sizes — including odd dimensions and malformed or corrupt inputs.

## Scoring (0-100)

| Lane | Points | Measures |
|---|---|---|
| L1 | 10 | candidate builds and matches the public probes |
| L2 | 45 | bit-exact equivalence on a hidden pixel-workload set (conversions, resizes, chains) |
| L3 | 15 | behavioural equivalence on hidden CLI transcripts, including malformed inputs and corrupt containers |
| L4 | 25 | performance — geometric-mean runtime ratio vs the C reference, both built and timed on the scoring host |

L2 is unforgiving by design: any mismatch on any hidden workload zeroes L2, L3 and L4.
L4 is evaluated only once L2 and L3 are perfect, so speed pays out only after correctness
is fully established.

## Submission loop

The agent submits `candidate/` (excluding `candidate/target/`) via sforge; the judge grades
in a separate pinned container with no network access. The work and judge images are pinned
by digest in `task.toml`, and hidden workloads plus canary tokens live under `tests/`.

## Layout

```
task.toml            task contract; work and judge images pinned by digest
instruction.md       agent-facing specification
environment/         work image: Dockerfile, C reference source, man page,
                     public probes, local verifier
tests/               judge image: Dockerfile, reference source tree,
                     run_workloads.py, canary_tokens.json
solution/            private oracle tree
```

The task is fully synthetic original work with no upstream lift.
