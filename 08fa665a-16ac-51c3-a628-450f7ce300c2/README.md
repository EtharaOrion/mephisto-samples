# 08fa665a-16ac-51c3-a628-450f7ce300c2

edgebench/cap_set_extremal_construction — build the largest explicit extremal construction
inside a pinned finite geometry. The agent emits a full point set that must satisfy the pinned
pair-sum construction property when that property is recomputed from scratch over the emitted
set. Score is a single float in [0, 1]; up to 50 attempts within a 15 hour wall-clock envelope
on one H100 host, with the best-scoring attempt kept.

## The geometry

The ambient geometry is published read-only at `/mnt/geometry`. The manifest pins the ambient
identity, field order, dimension, point count, the size floor / mid anchor / target that the
reward is normalised against, the per-attempt search budget, and the emission ceiling. A point
is a list of exactly `dimension` integers modulo the field order, added coordinatewise.

The construction property lives in a separate live record at `/mnt/geometry/predicate.json`:
a pair-sum condition under which no two different pairs drawn from the tuple classes in force
may produce the same sum. Both the manifest and the predicate are live objects that can change
during the run and are authoritative over every prose note, baseline, and helper — the agent
is expected to poll them.

## Scoring

The verifier ingests only the emitted point list: it canonicalises every coordinate vector
against the live ambient, rejects duplicates and out-of-ambient points outright, recomputes
the property over every required pair, and counts the survivors. An asserted cardinality earns
nothing unless realised as an explicit list, and a single property violation zeroes the set.

The surviving cardinality is normalised against the manifest's anchors: at or below the floor
scores 0, the mid anchor scores 0.25, and at or above the target scores 1 — the reward is
concentrated above the mid anchor rather than spread evenly.

Every attempt also carries a seven-field certificate that the verifier reconstructs from the
emitted set and the live registry alone: `canonical_point_digest`, `translation_normal_digest`,
`pair_sum_digest`, `distinct_pair_sums`, `degenerate_collision_count`, `emission_ceiling` and
`search_budget_seconds` — all must match the reconstruction exactly.

## Submission loop

Attempts are recorded through `/opt/edgebench/harness/submit.py`, which settles the geometry
registry, executes the constructor against the live parameters, recomputes the property, and
appends the authoritative run record. The agent's own reward log must reconcile against those
records exactly, and repeating an approach summary already used is treated as resubmitting a
refuted configuration. A local checker (`localcheck.py`) and an `ambient` helper module ship
alongside the harness.

Three deliverables in `/home/workspace`, sharing one agent-chosen UUID prefix:

- `<uuid>_D1_construct.py` — module exposing `construct(params)` plus `AMBIENT_PARAMS_ID`
  and `PREDICATE_DIGEST` constants
- `<uuid>_D2_construction_bundle.json` — the explicit point list, count, certificate and
  search seconds
- `<uuid>_D3_reward_log.jsonl` — one record per attempt with `attempt_index`, `approach`
  and `measured_reward`

A deliberately unoptimised baseline constructor (`starter_construct.py`) with working notes
ships in the workspace as a starting point. Network egress is setup-only; everything under
`/mnt/geometry`, `/opt/edgebench` and `/logs` is evaluator-owned.

## Layout

```
task.toml            task contract; work and judge images pinned by digest
instruction.md       agent-facing specification
environment/         work image and workspace baseline
tests/               judge image, scoring entrypoint (test.sh), trajectory rubrics
solution/            private oracle tree
```

A trajectory rubric set (`tests/rubrics.jsonl`, compilation floor 0.7) grades the run record
alongside the scalar reward.
