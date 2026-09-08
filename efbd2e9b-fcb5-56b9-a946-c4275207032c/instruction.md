Read README.md in your workspace, then act as the credit-review officer of a
community-bank supervisor: allocate a finite review-capacity budget across the
eligible universe of US community banks as of the 2025-12-31 information
boundary, targeting the banks whose credit will deteriorate. Submit the
`strategy/` directory: `policy.py` exposing `allocate(universe, history, asof)
-> {cert: weight}`, an honest `book_report.json`, and `memo.md` front-matter.
Your book is graded on the net charge-offs those banks actually realized in
Q1-2026 per their real FDIC call reports, held only by the judge. The scorer
(`credit_lib.py`) is public: score 0 is the measured copy frontier (the best
mechanical single-column ranking), so points exist only above every mechanical
strategy; full marks is the unreachable hindsight oracle. Constraints: weights
sum to 1, max weight 0.0037 (>= 270 banks). `policy.py` must pass the public
static allowlist gate (no filesystem, no dynamic code, no random/time). Iterate
freely with `python3 check.py` (public dev pair); submit when your policy beats
the mechanical frontier out of sample.
