# efbd2e9b-fcb5-56b9-a946-c4275207032c

Act as the credit-review officer of a community-bank supervisor: allocate a finite
review-capacity budget across 2,728 US community banks ($100M-$1B in assets) as of the
2025-12-31 information boundary, targeting the banks whose credit is about to deteriorate.
The book is graded on the net charge-offs the reviewed banks actually realized in Q1-2026,
as reported in their real FDIC call reports — outcome data held only by the judge.

## The task

The agent works from public FDIC BankFind financial data (US Government work, public
domain) with no network access, and submits a `strategy/` directory:

- **`policy.py`** — exposes `allocate(universe, history, asof) -> {cert: weight}`, the
  capacity-allocation policy over bank certificates
- **`book_report.json`** — an honest self-report of the book's construction
- **`memo.md`** — a front-matter memo documenting the reasoning

Allocation constraints: weights sum to 1, maximum weight 0.0037 per bank (so the book
spreads across at least 270 banks). `policy.py` must pass a public static allowlist gate —
no filesystem access, no dynamic code execution, no randomness or time-dependence — which
keeps every submitted policy a pure function of the provided data.

## Scoring

The scorer (`credit_lib.py`) is fully public, and the scale is anchored at both ends by
measured references rather than arbitrary constants:

- **Score 0** is the *measured mechanical copy frontier* — the best single-column ranking
  any mechanical strategy achieves on the same data. Points exist only above every
  mechanical strategy, so copying an obvious risk column earns nothing.
- **Full marks** is the *hindsight oracle* — the allocation a grader with perfect knowledge
  of the Q1-2026 outcomes would construct, which is unreachable by design.

Everything in between rewards genuine forward-looking credit signal extracted from the
2025-12-31 snapshot and history. The information boundary is strict: the judge alone holds
the Q1-2026 call reports that settle the book.

## Submission loop

The agent iterates freely against `python3 check.py`, a public development pair that
exercises the same pipeline out of sample. The intended loop: build a policy, verify it
clears the gate and beats the mechanical frontier on the dev pair, then submit
`strategy/policy.py`, `strategy/book_report.json`, and `strategy/memo.md` for grading in a
separate judge container (`sforge` structured-json parser, score maximized, no network).

## Layout

```
task.toml                    task contract; work and judge images pinned by digest
instruction.md               agent-facing brief pointing into the workspace README
environment/                 work image: Dockerfile, README, FDIC data, public scorer
                             (credit_lib.py), static gate (gate.py), check.py dev
                             harness, strategy/ scaffold
tests/                       judge image: Dockerfile, score.py, gate.py, credit_lib.py,
                             test.sh, data/ (including the held-out Q1-2026 outcomes)
solution/                    reference strategy: policy.py, book_report.json, memo.md,
                             solve.sh
```

Provenance: authored 2026-08-06, Mephisto-native design with a copy-frontier-anchored
triage book; source data from the FDIC BankFind Suite financials endpoint, US-government
public domain.
