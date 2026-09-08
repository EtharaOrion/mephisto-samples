# 00ed522b-32e1-51f6-a187-dfbd2fe900a8

Build and progressively optimise a two-dimensional irregular nesting engine that packs polygonal
parts into a bounded sheet. The objective is to minimise the mean material waste the verifier
recomputes across a pinned family of nesting instances, subject to exact geometric feasibility on
every placement. Reward is a single float in [0, 1]; up to 50 attempts inside a 15-hour wall-clock
envelope on one H100, with the best-scoring attempt kept.

## Problem

Instances are mounted read-only at `/mnt/instances`; the public practice sweep is readable, while
grading runs on a larger hidden family drawn from the same generator. Part geometry arrives through
two independent carriers — the vector outline carrier `outlines.geom` (exact integer-vertex
polygons, sheet dimensions, defect exclusion rectangles, per-part rotation allowance, multiplicity,
margin) and the tabular carrier `parts.csv`. Exactly one carrier is authoritative for each field on
which they disagree, and the live registry at `/mnt/authority/authority.json` is the sole statement
of which carrier binds which field. Both the registry and the instance manifest can change during
the run and must be polled.

A placement is a part identifier, a rotation from the quantised set {0, 90, 180, 270} degrees, and
an integer translation. The verifier replays every placement from scratch with exact integer
arithmetic, so feasibility never depends on floating point or on the host.

## Scoring

Waste for one instance is the usable sheet area (sheet area minus defect rectangles) less the exact
polygon area of every placed part, divided by that usable area. The score is a clipped linear map
of mean waste across the graded family — lower waste, higher score. Every reported figure is
independently recomputed. Solve time is charged by a published deterministic cost model: an
interpreter line-event tracer counts line events as cost units at a fixed 25 ns each, against
per-instance and whole-sweep budgets named in the live manifest.

## Submission loop

Every attempt is recorded through `/opt/edgebench/harness/submit.py`, which settles the mounts,
builds and runs the engine over the practice sweep, and appends the authoritative run record.
Local tools `preview.py` and `geometry.py` provide exact integer-predicate checks for single
placement files. Three deliverables land in `/home/workspace` under one shared UUID prefix:

- `<uuid>_D1_nester_src.tar` — source tree rooted at a `nester` package, `nester/main.py`
  exposing `main(argv)` with the `--instance / --output / --budget-seconds` contract
- `<uuid>_D2_placement_bundle.jsonl` — one selected placement set per practice instance
- `<uuid>_D3_reward_log.jsonl` — one record per attempt with `attempt_index`, `approach`,
  `measured_reward`

A deliberately simple starter engine ships at `/home/workspace/starter`: it builds, runs, and its
placements survive recomputation, leaving ample headroom for rotation-aware, true-polygon packing.

## Layout

```
task.toml        task contract (harbor 1.4): 50 attempts, 15 h envelope, best-of selection,
                 one H100, setup-only egress, separate verifier image pinned by digest
instruction.md   agent-facing specification
environment/     work image: Dockerfile, harness, starter engine, private assets
solution/        private oracle tree
tests/           judge image and scorer
```
