# 304e275d-73d8-59d2-8c7e-94c7fe1e3beb

edgebench/arc_compiler_runtime — build a compiler and a runtime for the ARC instruction set,
then progressively optimise them. The objective is the weighted pass fraction the verifier
recomputes over a held-out suite of ARC source programs, where a program contributes nothing
unless the compiler and runtime reproduce its exact observable trace and exit status. Score is
a single float in [0, 1]; up to 50 attempts within a 15 hour envelope on one H100 host, best
attempt kept.

## The language and the ISA

ARCL is a small integer language: functions, function-scoped variables, `let`, assignment,
`if`/`else`, `while`, `out`, `return`, the full complement of comparison / bitwise / shift /
arithmetic operators, and calls into user functions and ISA-declared builtins. Every value is
a 32-bit word with wrapping arithmetic, signed truncating division, a trap on zero divisors,
and modulo-width shift counts. The observable trace is the sequence of `out` values; exit
status distinguishes normal halt, divide trap, instruction-ceiling overrun, and machine fault.

The instruction set is mounted read-only at `/mnt/isa`: `isa.json` (opcode table, operand
lists, word semantics, register/memory sizes, executed-instruction ceiling), `abi.json` (the
calling convention for linked intrinsic bodies), and `intrinsics.json` (pre-assembled intrinsic
bodies keyed by ISA revision, which must be copied into the program image exactly as
published). Both registries are live objects that can move during the run and are always
authoritative over prose notes and cached constants.

A public smoke slice under `/mnt/isa/public` carries sample programs with expected traces and
statuses; grading runs on a larger hidden suite that is never mounted.

## Scoring

Speed is measured as executed instruction count — exactly reproducible, never wall clock. Each
passing program earns a correctness floor plus a further share for beating a deliberately
unoptimised reference lowering, saturating at half its instruction count. Correctness is a
precondition, never a trade: one wrong trace on the graded suite scores zero, with a
machine-readable reason naming the first offending program.

## Deliverables

The compiler lives under `compiler/src` with entry points in `pipeline.py`:
`compile_program(source, context)`, `execute(program, ceiling)`, and `describe_pipeline()`.
Four artifacts share one UUID prefix:

- `<uuid>_D1_compiler_src.tar` — archive of `compiler/src/`
- `<uuid>_D2_suite_report.json` — pass fraction, counts, ISA revision id, ABI digest,
  miscompile count, measured over the public smoke slice
- `<uuid>_D3_reward_log.jsonl` — one record per attempt, reconciled against the harness
- `<uuid>_D4_pass_pipeline.json` — the pass list with per-pass preconditions and invariants
  drawn from a pinned fact vocabulary; the pipeline must end with physical registers, a fixed
  frame layout, marshalled calls and a resolved ABI

Attempts are recorded through `/opt/edgebench/harness/submit.py`, which settles the registries,
measures against the public slice, and appends the authoritative run record. Every reported
number is independently recomputed. A working but deliberately unoptimised compiler ships in
the workspace as a starting point, with a cheatsheet at `/mnt/isa/cheatsheet.md` to be read
critically.

## Layout

```
task.toml            task contract; work and judge images pinned by digest
instruction.md       agent-facing specification
environment/         work image and baseline compiler workspace
tests/               judge image, scoring entrypoint (test.sh), trajectory rubrics
solution/            private oracle tree
```

A trajectory rubric set (`tests/rubrics.jsonl`, compilation floor 0.7) grades the run record
alongside the scalar reward. Network egress is setup-only; the hidden suite, registry mounts
and `/opt/edgebench` are evaluator-owned.
