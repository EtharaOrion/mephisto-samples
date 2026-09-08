# d6cb9bed-077f-5ff0-949d-f9dd0c16a872

Build and progressively optimise a two-dimensional irregular nesting engine that packs polygonal
parts into a bounded sheet, minimising the mean material waste the verifier recomputes across a
pinned family of nesting instances while keeping every placement exactly geometrically feasible.
Reward is a single float in [0, 1]; up to 50 attempts inside a 15-hour wall-clock envelope on one
H100, with the best-scoring attempt kept.

## Problem

Instances are mounted read-only at `/mnt/instances`. The public practice sweep is directly
readable; grading runs on a larger hidden family drawn from the same generator. Each instance
delivers part geometry through two independent carriers — `outlines.geom` (exact integer-vertex
polygon boundaries, sheet dimensions, defect exclusion rectangles, rotation allowance,
multiplicity, margin) and `parts.csv` (tabular parameters). Exactly one carrier is authoritative
per disputed field, and the live registry at `/mnt/authority/authority.json` is the sole statement
of which carrier binds which field. The registry and the instance manifest are live objects that
can change mid-run; both must be polled.

A placement is a part identifier, a rotation drawn from {0, 90, 180, 270} degrees, and an integer
translation. The verifier replays every placement with exact integer arithmetic, so feasibility is
bit-reproducible and host-independent: containment in the sheet, clearance of defect rectangles,
pairwise separation, rotation allowance and multiplicity are all recomputed from scratch.

## Scoring

Per-instance waste is the usable sheet area (sheet minus defect rectangles) less the exact polygon
area of the placed parts, divided by the usable area; the score is a clipped linear map of mean
waste across the graded family. Every figure the engine reports is independently recomputed. Solve
time is charged deterministically — an interpreter line-event tracer counts events at a fixed
25 ns per unit against per-instance and whole-sweep budgets named in the live manifest — so cost
is exactly reproducible.

## Submission loop

Attempts are recorded through `/opt/edgebench/harness/submit.py`, which settles the mounts, runs
the engine over the practice sweep, and appends the authoritative run record. The local tools
`preview.py` and `geometry.py` recompute containment, defect exclusion and overlap for individual
placement files. Three deliverables in `/home/workspace`, all under one UUID prefix:

- `<uuid>_D1_nester_src.tar` — `nester` package with `nester/main.py` exposing `main(argv)` and
  the `--instance / --output / --budget-seconds` command-line contract
- `<uuid>_D2_placement_bundle.jsonl` — exactly one selected placement set per practice instance
- `<uuid>_D3_reward_log.jsonl` — `attempt_index`, `approach`, `measured_reward` per attempt

A starter engine at `/home/workspace/starter` builds, runs, and survives recomputation using
axis-aligned bounding boxes on a coarse lattice — a working floor with clear room for true-polygon,
rotation-aware improvement.

## Layout

```
task.toml        task contract (harbor 1.4): 50 attempts, 15 h envelope, best-of selection,
                 one H100, setup-only egress, separate verifier image pinned by digest
instruction.md   agent-facing specification
environment/     work image: Dockerfile, harness, starter engine, private assets
solution/        private oracle tree
tests/           judge image and scorer
```
