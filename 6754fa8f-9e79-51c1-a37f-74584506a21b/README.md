# 6754fa8f-9e79-51c1-a37f-74584506a21b

Build and progressively improve an instruction scheduler for a very long instruction word (VLIW)
target, minimising the mean normalised cycle count of the bundle schedules it emits over a pinned
kernel family. The score is a single float in [0.0, 1.0], higher is better, with up to 50 attempts
inside a 15-hour wall-clock envelope on one H100 host; the final result is the best-scoring
attempt.

## The machine

A statically scheduled in-order target with no hardware interlock. A schedule is an ordered list
of bundles; the bundle at index k issues at cycle k, and a result issued at cycle c becomes
readable at cycle c plus the opcode's latency. Nothing stalls on the scheduler's behalf — an
operation that reads a register before its producer retires reads a stale value, making the
schedule illegal rather than slow. The cycle count of a schedule is the largest issue-cycle plus
latency over every operation, never less than the number of bundles emitted; empty bundles are
legal and express stalls.

A schedule is legal only when all of the following hold: no bundle exceeds the issue width or any
functional-unit port capacity; unpipelined units respect their occupancy distance; every register
read lands at or after its producer's write and strictly before the next write; same-register
writes land in program order and never in the same cycle; the same three rules hold for memory
words (conflicting exactly on equal addresses); and every source operation appears in exactly one
bundle, exactly once — nothing dropped, duplicated, or algebraically rewritten.

## Inputs and live authority

- `/mnt/kernels` (read-only) — the kernel family. `manifest.json` names the graded sweep size,
  the public fixture count, and the budgets. Public fixtures live at
  `public/public_kNNN.json` with register count, memory word count, and the operation list in
  program order. The graded family is never mounted and must never be read, reconstructed, or
  inferred.
- `/mnt/machine_model` (read-only) — `registry.json` is the sole authority for the live target
  and declares the machine model identifier. It is live and authoritative over any cached copy.

## Graded artifacts

```
<uuid>_D1_scheduler_src.tar       the scheduler source
<uuid>_D2_schedule_bundle.jsonl   emitted schedules
<uuid>_D3_reward_log.jsonl        reward log
```

Reward metric `score` in [0.0, 1.0], aggregation `single`, full reward at 1.0. A rubric is
present with a compilation floor of 0.7 and trajectory rubrics at `tests/rubrics.jsonl`.

## Environment

- Work image pinned by digest, workdir `/home/workspace`, `linux/amd64`, one-H100 compute
  envelope, solver egress `setup_only`, verifier `no-network`.
- Separate judge image pinned by digest, entrypoint `tests/test.sh`, reward written to
  `/logs/verifier/reward.json`.
- Submission ships the workspace root, excluding `starter/`, `notes/`, `tests/`, caches, and
  `.git/`; selection `score_first`, `score_direction = maximize`.

## Layout

```
task.toml            task contract; images pinned by digest
instruction.md       agent-facing specification
environment/         work image: Dockerfile, build, harness, starter workspace
tests/               judge image: Dockerfile, checkers, controls, kernels.py, machine.py,
                     registry.py, score.py, rubrics.jsonl
solution/            private oracle tree: TRUTH.md, grounding.yaml, policy.yaml,
                     provenance.yaml, recompute.py, reference_scheduler.py, rubrics.json,
                     solve.sh
```
