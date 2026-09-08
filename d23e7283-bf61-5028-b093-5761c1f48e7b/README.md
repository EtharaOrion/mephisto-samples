# d23e7283-bf61-5028-b093-5761c1f48e7b

Build and progressively improve an instruction scheduler for a VLIW (very long instruction word)
target, minimising the mean normalised cycle count of the bundle schedules it emits over a pinned
kernel family. The machine is statically scheduled and in-order with no hardware interlock:
nothing stalls on the scheduler's behalf, so an operation that reads a register before its
producer retires reads a stale value and the schedule is illegal rather than slow.

## The problem

A schedule is an ordered list of bundles; the bundle at index k issues at cycle k, and a result
becomes readable at issue cycle plus opcode latency. Legality requires, simultaneously: issue
width respected per bundle, per-port functional-unit capacity respected, unpipelined-unit
occupancy distances honoured, RAW/WAR/WAW hazards clean on both registers and memory words, and
every source operation appearing exactly once — nothing dropped, duplicated, or algebraically
rewritten.

Distinctive pressures that keep the task honest:

- **Live mounts.** The machine-model registry at `/mnt/machine_model/registry.json` is the sole
  authority for issue width, port capacities, occupancy and latencies — and it can change during
  the run. Convenience carriers (a latency manifest, a prose MODEL.md) ship beside it; the
  registry wins whenever they disagree. Polling is part of the task.
- **Deterministic compute budget.** The scheduler runs under an interpreter line-event tracer;
  line events are the scheduling cost, charged at a fixed rate named in the kernel manifest.
  Exceeding the per-kernel or sweep budget scores zero, so cycle reduction cannot be bought with
  unbounded search.
- **Hidden graded family.** Public fixture kernels are readable under `/mnt/kernels/public/`;
  grading runs on a larger family that is never mounted and must never be probed.
- **Bit-exact semantics.** Scheduled kernels are executed on held-out inputs and the final
  register file and memory image are compared bit for bit against sequential execution — any
  divergence scores zero.

## Scoring

Reward is a single float in [0, 1]. It is computed from the mean over the graded family of cycle
count divided by an analytic lower bound per kernel, mapped so a schedule at the lower bound
approaches 1.0 and a fully serialised schedule stays near 0.0. Every claimed number is
independently recomputed by the verifier from the emitted bundles. A compilation floor of 0.7
and trajectory rubrics apply.

Up to 50 attempts inside a 15-hour wall-clock envelope on one H100 host; final selection is the
best-scoring attempt. Attempts are recorded through `/opt/edgebench/harness/submit.py`, and the
agent's own reward log must reconcile exactly against the harness run records.

## Deliverables

Three artifacts in `/home/workspace`, sharing one agent-chosen UUID prefix:

- `<uuid>_D1_scheduler_src.tar` — scheduler source tree with a `build.sh` producing an
  executable `bin/schedule` honouring `--kernel --machine-model --out --budget-seconds`
- `<uuid>_D2_schedule_bundle.jsonl` — one schedule per public fixture kernel, resolved against
  the live registry and manifest
- `<uuid>_D3_reward_log.jsonl` — one record per attempt: `attempt_index`, `approach`,
  `measured_reward`

A deliberately unoptimised starter tree is provided: it builds, produces legal schedules on any
target, and scores poorly (one operation per bundle, widest-latency spacing) — a starting point
to read critically, not a specification.

## Layout

```
task.toml                    Harbor contract: 50 attempts, 15 h, best selection,
                             setup-only egress, one-H100 envelope
instruction.md               agent-facing specification
environment/                 work image
tests/                       judge image: score.py, machine.py, kernels.py, registry.py,
                             trace_run.py, verifier_lib.py, checkers/, controls/, private/,
                             rubrics.jsonl, test.sh
solution/                    private oracle tree: TRUTH.md, reference_scheduler.py,
                             grounding.yaml, policy.yaml, provenance.yaml,
                             recompute.py, rubrics.json, solve.sh
```
