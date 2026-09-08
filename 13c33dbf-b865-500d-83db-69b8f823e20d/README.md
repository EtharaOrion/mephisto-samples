# 13c33dbf-b865-500d-83db-69b8f823e20d

edgebench/arc_compiler_runtime — build a compiler and a runtime for the ARC instruction set
from scratch, then progressively optimise them. The score is the weighted pass fraction the
verifier recomputes over a held-out suite of ARC source programs, where a program contributes
nothing unless the compiler and runtime reproduce its exact observable trace and exit status.
Score is a single float in [0, 1]; up to 50 attempts within a 15 hour wall-clock envelope on
one H100 host, best attempt kept.

## The language and the ISA

ARCL is a small integer language: functions, `let`, assignment, `if`/`else`, `while`, `out`,
`return`, the full complement of comparison / bitwise / shift / arithmetic operators, and
calls into program-declared functions and ISA-declared builtins. Every value is a 32-bit word
with wrapping arithmetic, signed truncating division, a trap on zero divisors, and both
arithmetic (`>>`) and logical (`>>>`) right shifts. Exit statuses distinguish normal halt,
divide trap, instruction-ceiling overrun, and machine fault.

The instruction set is mounted read-only at `/mnt/isa`:

- `isa.json` — sole authority for the opcode table, operand lists, word semantics, register
  and memory sizes, and the executed-instruction ceiling
- `abi.json` — sole authority for the calling convention into linked intrinsic bodies
- `intrinsics.json` — pre-assembled intrinsic bodies keyed by ISA revision, which every
  source-level builtin call must be lowered into exactly as published

Both registries are live and can move during the run; they win over every prose note, header
table, or previously written constant. A public smoke slice under `/mnt/isa/public` carries
programs with expected traces, statuses, weights and categories; grading runs on a larger
hidden suite that must never be read, reconstructed, or fingerprinted.

## Scoring

Speed is measured as executed instruction count — never wall clock — so every figure is
exactly reproducible. Each passing program earns a correctness floor plus a further share for
executing fewer instructions than a deliberately unoptimised reference lowering, saturating
at half the reference count. Correctness is a precondition, not a trade: one wrong trace on
the graded suite scores zero, with a machine-readable reason and the first offending program
named. Handing compilation or execution to an external compiler, assembler, interpreter or
JIT scores zero.

## Submission loop

Attempts go through `/opt/edgebench/harness/submit.py`, which settles the registries,
measures the compiler against the public smoke slice, and appends the authoritative run
record. The agent's reward log must reconcile against those records exactly.

Four deliverables in `/home/workspace`, sharing one UUID prefix:

- `<uuid>_D1_compiler_src.tar` — archive of `compiler/src/` exposing `compile_program`,
  `execute` and `describe_pipeline` from `pipeline.py`
- `<uuid>_D2_suite_report.json` — weighted pass fraction, raw counts, ISA revision id,
  calling-convention digest, miscompile count over the public slice
- `<uuid>_D3_reward_log.jsonl` — per-attempt index, pipeline summary, semantics verdict,
  measured reward
- `<uuid>_D4_pass_pipeline.json` — the pass list with per-pass preconditions and invariants
  drawn from a pinned 13-fact vocabulary; the pipeline must end with physical registers,
  fixed frame layout, marshalled calls and a resolved ABI

Every reported number is independently recomputed. A deliberately unoptimised but correct
baseline compiler ships under `compiler/src` as a starting point, alongside a non-normative
cheatsheet at `/mnt/isa/cheatsheet.md`. Network egress is setup-only.

## Layout

```
task.toml            task contract; work and judge images pinned by digest
instruction.md       agent-facing specification
environment/         work image and baseline compiler workspace
tests/               judge image, scoring entrypoint (test.sh), trajectory rubrics
solution/            private oracle tree
```

A trajectory rubric set (`tests/rubrics.jsonl`, compilation floor 0.7) grades the run record
alongside the scalar reward.
