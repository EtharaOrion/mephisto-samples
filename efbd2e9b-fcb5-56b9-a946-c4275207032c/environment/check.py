#!/usr/bin/env python3
"""Local pre-flight: run the SAME static gate and constraint checks the judge
runs, plus a dev-pair rehearsal grade (allocate at 20241231, graded on the
real public 20250331 outcomes) so you can iterate without spending a
submission. The hidden Q1-2026 outcome is NOT here; dev-pair scores do not
predict hidden scores, but the plumbing is identical.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import credit_lib as CL          # noqa: E402
from gate import gate_violations  # noqa: E402

DEV_BOUNDARY = "20241231"
DEV_GRADED = "20250331"


def load(q):
    with open(HERE / "data" / f"fdic_{q}.csv", newline="") as fh:
        return [CL.coerce(r) for r in csv.DictReader(fh)]


def main():
    src = (HERE / "strategy" / "policy.py").read_text()
    gv = gate_violations(src)
    if gv:
        print("GATE: FAIL")
        for v in gv[:10]:
            print(f"  {v['rule']} line {v['lineno']}: {v['detail']}")
        return 1
    print("GATE: clean")

    hist_all = {q: load(q) for q in
                ["20241231", "20250331", "20250630", "20250930", "20251231"]}
    dev_universe = CL.eligible(hist_all[DEV_BOUNDARY])
    dev_hist = {DEV_BOUNDARY: hist_all[DEV_BOUNDARY]}
    ns = {}
    exec(compile(src, "policy.py", "exec"), ns)  # noqa: S102
    w = ns["allocate"](dev_universe, dev_hist, "2024-12-31")
    certs = [r["CERT"] for r in dev_universe]
    v = CL.check_constraints(w, certs)
    print(f"CONSTRAINTS: {len(v)} violation(s)")
    for x in v[:5]:
        print("  ", x)

    bd = {r["CERT"]: r for r in dev_universe}
    outcomes = {}
    for r in load(DEV_GRADED):
        c = r["CERT"]
        if c in bd and r["NTLNLSR"] is not None:
            outcomes[c] = {"nco": r["NTLNLSR"], "nco_boundary": bd[c]["NTLNLSR"]}
    m = CL.book_metrics(w, outcomes)
    if m is None:
        print("DEV GRADE: no gradable exposure")
        return 1
    lanes = CL.score(m)
    total, pen = CL.total_score(lanes, v)
    print(f"DEV-PAIR GRADE (rehearsal only): {total:.2f}/100 "
          f"(penalty {pen:.2f})")
    print(json.dumps({k: round(x, 3) for k, x in lanes.items()}, indent=1))
    print("NOTE: dev-pair lane anchors are the HIDDEN pair's frozen anchors; "
          "the rehearsal indicates plumbing and rough shape, not your hidden "
          "score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
