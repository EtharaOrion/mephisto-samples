# Community Bank Credit-Review Triage Book

You are the credit-review officer of a community-bank supervisor. You have a
finite review-capacity budget and 2,728 eligible US community banks
($100M-$1B assets). Allocate the budget toward the banks whose credit will
deteriorate: your book is graded on the net charge-offs those banks ACTUALLY
realized in Q1-2026, from their real FDIC call reports. Nobody authored the
answer; reality did.

## Deliverables (submit the `strategy/` directory)

- `strategy/policy.py` — `allocate(universe, history, asof) -> {cert: weight}`.
  Pure function of boundary data. The judge runs it ONCE with ITS OWN copy of
  the data; it never reads yours.
- `strategy/book_report.json` — `{n_names, max_weight, effective_names,
  weighted_boundary_nco, weighted_boundary_nperfv}` recomputed from your own
  weights. The judge recomputes all five from the weights your policy actually
  returns; any divergence zeroes the performance score.
- `strategy/memo.md` — YAML front-matter (`thesis_code`, `risk_flags`,
  `sizing_rationale_code`). Prose is not graded.

## Rules

- Constraints: weights sum to 1 (+/-1e-6); max weight 0.0037 (your budget must
  spread over >= 271 banks). Violations are penalized, never rewarded.
- `policy.py` passes a static allowlist gate BEFORE it runs: imports limited to
  math/statistics/collections/itertools/functools/heapq/bisect/operator; no
  open/eval/exec/getattr/globals, no dunder access, no random, no time. Run
  `python3 check.py` locally - it is the same gate.
- The scorer is public: read `credit_lib.py`. Score 0 on every lane is the
  measured COPY FRONTIER - the best mechanical single-column book (sort by
  boundary NCO, historical-mean NCO, noncurrent, or provision). Sorting one
  column earns ~0 BY CONSTRUCTION. Points exist only above every mechanical
  strategy. Full marks is the hindsight oracle; no boundary-time policy
  reaches it.
- Data: `data/fdic_<q>.csv`, five public quarters through 2025-12-31 (the
  information boundary). Q1-2026 exists only on the judge host.
- `python3 check.py` grades your policy on the public dev pair (allocate at
  2024-12-31, graded on the real, public 2025-03-31 outcomes) - same plumbing,
  free iteration. Dev scores do not predict hidden scores.

## Scoring (100 points, all on realized Q1-2026 charge-offs)

- T1 (35): share of your budget on the realized worst-decile cohort.
- T2 (40): realized charge-off rate your book captured, minus the equal-weight
  benchmark, in pp.
- T3 (25): share of your budget on banks whose rate rose >0.25pp vs their own
  boundary rate.
Each lane is linear from the copy frontier (0) to the oracle (full). A
compliance multiplier in [0.70, 1.0] can only subtract. Hygiene earns nothing.
