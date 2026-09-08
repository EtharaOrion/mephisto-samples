"""JUDGE-ONLY scorer for fdic_community_credit_triage.

Reads its OWN copies of the five public quarters and the hidden Q1-2026
outcomes, runs the submitted policy once through the static gate and a
restricted namespace, recomputes every reported statistic from the weights
actually returned (anti-fabrication), and emits one structured result whose
agent-visible surface carries LANE SCORES ONLY - realized magnitudes are
answer-key aggregates and are redacted (a seed-only TRIAGE_JUDGE_AUDIT env
reveals them for authoring audits; it is never set in the shipped eval).
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

JUDGE = Path(__file__).resolve().parent
sys.path.insert(0, str(JUDGE))          # judge's own credit_lib + gate copies
import credit_lib as CL                 # noqa: E402
from gate import gate_violations        # noqa: E402

DATA = JUDGE / "data"
PUBLIC_QS = ["20241231", "20250331", "20250630", "20250930", "20251231"]
BOUNDARY_Q = "20251231"
GRADED = "outcomes_20260331.csv"
ASOF = "2025-12-31"
FAB_TOL = {"n_names": 0, "max_weight": 1e-6, "effective_names": 1.0,
           "weighted_boundary_nco": 0.02, "weighted_boundary_nperfv": 0.05}


def load_quarter(q):
    with open(DATA / f"fdic_{q}.csv", newline="") as fh:
        return [CL.coerce(r) for r in csv.DictReader(fh)]


def emit(valid, score, summary, details, metrics):
    report = {"valid": valid, "score": float(score),
              "pass_rate": 1.0 if valid and score > 0 else 0.0,
              "total_tests": max(1, len(details)),
              "passed": sum(1 for d in details if d.get("status") == "PASSED"),
              "failed": sum(1 for d in details if d.get("status") == "FAILED"),
              "errors": sum(1 for d in details if d.get("status") == "ERROR"),
              "summary": summary, "details": details, "metrics": metrics}
    print(">>>>> Start Structured Result")
    print(json.dumps(report, ensure_ascii=False))
    print(">>>>> End Structured Result")


def main():
    details, metrics = [], {}
    strat = Path(os.environ.get("TRIAGE_WORKSPACE", "/home/workspace")) / "strategy"
    policy_p = strat / "policy.py"
    report_p = strat / "book_report.json"
    memo_p = strat / "memo.md"

    for p, name in ((policy_p, "policy.py"), (report_p, "book_report.json"),
                    (memo_p, "memo.md")):
        if not p.exists():
            details.append({"name": f"deliverable:{name}", "status": "FAILED",
                            "score": 0.0, "message": "missing deliverable"})
    if any(d["status"] == "FAILED" for d in details):
        metrics["rejected"] = "missing_deliverable"
        emit(False, 0.0, "missing deliverable", details, metrics)
        return

    src = policy_p.read_text()
    gv = gate_violations(src)
    if gv:
        metrics["rejected"] = "static_allowlist_gate"
        metrics["detail"] = {"gate_violations": gv[:20]}
        details.append({"name": "gate", "status": "FAILED", "score": 0.0,
                        "message": f"{len(gv)} gate violation(s): "
                                   f"{gv[0]['rule']}:{gv[0]['detail']}"})
        emit(False, 0.0, "rejected by the static allowlist gate", details, metrics)
        return
    details.append({"name": "gate", "status": "PASSED", "score": 0.0,
                    "message": "static allowlist clean"})

    hist = {q: load_quarter(q) for q in PUBLIC_QS}
    universe = CL.eligible(hist[BOUNDARY_Q])
    certs = [r["CERT"] for r in universe]
    bd = {r["CERT"]: r for r in universe}

    ns = {"__builtins__": {k: __builtins__[k] if isinstance(__builtins__, dict)
                           else getattr(__builtins__, k)
                           for k in ("abs", "min", "max", "sum", "len", "range",
                                     "sorted", "enumerate", "zip", "map",
                                     "filter", "list", "dict", "set", "tuple",
                                     "float", "int", "str", "bool", "round",
                                     "any", "all", "isinstance", "ValueError",
                                     "KeyError", "TypeError", "Exception",
                                     "print", "reversed", "divmod", "pow",
                                     "__import__")}}
    try:
        exec(compile(src, "policy.py", "exec"), ns)          # noqa: S102
        w = ns["allocate"](universe, hist, ASOF)
    except Exception as e:                                   # noqa: BLE001
        metrics["rejected"] = "policy_exception"
        details.append({"name": "allocate", "status": "ERROR", "score": 0.0,
                        "message": f"{type(e).__name__}: {e}"[:500]})
        emit(False, 0.0, "policy raised", details, metrics)
        return
    if not isinstance(w, dict) or not w:
        metrics["rejected"] = "empty_or_malformed_book"
        details.append({"name": "allocate", "status": "FAILED", "score": 0.0,
                        "message": "allocate() must return a non-empty dict"})
        emit(False, 0.0, "empty book", details, metrics)
        return

    violations = CL.check_constraints(w, certs)
    if any(v.get("check") in ("finite_weights",) for v in violations):
        metrics["rejected"] = "nonfinite_weight"
        emit(False, 0.0, "non-finite weight", details, metrics)
        return
    metrics["violations"] = len(violations)
    if violations:
        metrics["violation_detail"] = [v.get("check") for v in violations][:10]

    # anti-fabrication: recompute the reported book stats from the weights
    try:
        rep = json.loads(report_p.read_text())
    except Exception:
        rep = None
    held = {c: x for c, x in w.items() if x > 0}
    tw = sum(held.values()) or 1.0
    nw = {c: x / tw for c, x in held.items()}
    truth = {
        "n_names": len(held),
        "max_weight": max(held.values()) if held else 0.0,
        "effective_names": (1.0 / sum(x * x for x in nw.values())) if nw else 0.0,
        "weighted_boundary_nco": sum(
            nw[c] * (bd[c]["NTLNLSR"] or 0.0) for c in nw if c in bd),
        "weighted_boundary_nperfv": sum(
            nw[c] * (bd[c]["NPERFV"] or 0.0) for c in nw if c in bd),
    }
    fab = rep is None
    if rep is not None:
        for k, tol in FAB_TOL.items():
            try:
                if abs(float(rep.get(k)) - truth[k]) > tol:
                    fab = True
            except (TypeError, ValueError):
                fab = True
    metrics["anti_fabrication_triggered"] = fab
    if fab:
        details.append({"name": "anti_fabrication", "status": "FAILED",
                        "score": 0.0,
                        "message": "book_report diverges from the submitted "
                                   "book (or is unreadable); performance zeroed"})
        emit(True, 0.0, "anti-fabrication triggered", details, metrics)
        return
    details.append({"name": "anti_fabrication", "status": "PASSED",
                    "score": 0.0, "message": "book_report matches recompute"})

    with open(DATA / GRADED, newline="") as fh:
        outcomes = {}
        for r in csv.DictReader(fh):
            try:
                outcomes[r["CERT"]] = {
                    "nco": float(r["NCO_REALIZED"]),
                    "nco_boundary": float(r["NCO_BOUNDARY"])
                    if r["NCO_BOUNDARY"] != "" else None}
            except ValueError:
                continue

    m = CL.book_metrics(w, outcomes)
    if m is None:
        metrics["rejected"] = "no_gradable_exposure"
        emit(False, 0.0, "no gradable exposure", details, metrics)
        return
    lanes = CL.score(m)
    total, pen = CL.total_score(lanes, violations)
    audit = os.environ.get("TRIAGE_JUDGE_AUDIT") == "1"
    for name in CL.LANE_ORDER:
        details.append({"name": name, "status": "PASSED" if lanes[name] > 0
                        else "FAILED", "score": round(lanes[name], 4),
                        "message": f"{lanes[name]:.2f}/"
                                   f"{CL.LANES[name]['points']:.0f} pts"})
    metrics.update({"lane_scores": {k: round(v, 4) for k, v in lanes.items()},
                    "compliance_penalty": round(pen, 4),
                    "n_names_held": m["n_names_held"],
                    "effective_names": round(m["effective_names"], 1)})
    if audit:
        metrics["audit_realized"] = {k: round(m[k], 6) for k in
                                     ("T1_decile_coverage", "T2_nco_captured_pp",
                                      "T3_deterioration_capture",
                                      "book_realized_nco", "bench_realized_nco")}
    emit(True, round(total, 4),
         f"Score {total:.2f}/100 over {m['n_names_held']} reviewed banks; "
         f"penalty {pen:.2f}", details, metrics)


if __name__ == "__main__":
    main()
