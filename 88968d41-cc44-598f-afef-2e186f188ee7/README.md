# 88968d41-cc44-598f-afef-2e186f188ee7

Build the largest explicit extremal construction possible inside a pinned finite geometry —
a cap-set-style problem where the objective is to emit a maximal point set satisfying a
pair-sum admissibility predicate, recomputed from scratch by the verifier over the emitted
set. Up to 50 attempts within a 15-hour wall-clock envelope on one H100 host; the best
attempt counts.

## The problem

The ambient geometry is published read-only at `/mnt/geometry`: a manifest pins the field
order, dimension, point count, size floor / mid anchor / target used to normalise the
reward, the per-attempt search budget, and the emission ceiling. The construction property
lives in a separate live `predicate.json` record — a pair-sum condition forbidding two
different pairs from the tuple classes in force producing the same sum.

A defining feature of the task is that both records are **live**: the predicate and manifest
can change during the run and are authoritative over the shipped notes, the baseline
constructor and any constant computed earlier. Polling them is part of the job.

## Scoring

The score is a single float in [0, 1] derived only from the point set actually emitted.
The verifier canonicalises every coordinate vector, rejects duplicates and out-of-ambient
points, recomputes the property over every required pair, and counts the survivors.
Asserted-but-unrealised cardinality earns nothing, and a single property violation zeroes
the attempt. The surviving cardinality is normalised so that the floor scores 0, the mid
anchor scores 0.25, and the target scores 1 — concentrating the reward above the mid anchor.

Attempts are recorded through the harness at `/opt/edgebench/harness/submit.py`, which
settles the geometry registry, executes the constructor against live parameters, recomputes
the property, and appends the authoritative run record. The agent's own reward log must
reconcile against those records exactly.

## Deliverables

Three files in `/home/workspace`, sharing one agent-chosen UUID prefix:

- `<uuid>_D1_construct.py` — module exposing `construct(params)` returning the explicit
  point list, plus `AMBIENT_PARAMS_ID` and `PREDICATE_DIGEST` constants
- `<uuid>_D2_construction_bundle.json` — full point list, count, and a seven-field
  certificate (canonical / translation-normal / pair-sum digests, distinct pair sums,
  degenerate collisions, live ceiling and budget) that the verifier reconstructs exactly
- `<uuid>_D3_reward_log.jsonl` — one record per attempt with index, approach and
  measured reward

A deliberately unoptimised baseline constructor and its (deliberately stale) working notes
ship in the workspace as a starting point.

## Layout

```
task.toml            task contract; verifier image pinned by digest
instruction.md       agent-facing specification
environment/         work image and workspace materials
tests/               judge image: ambient.py, checkers, controls, rubrics
solution/            private oracle tree and reference construction materials
```

Network egress is available during setup only; the verifier runs with no network. A private
reference construction calibrates the reward and is held outside the workspace.
