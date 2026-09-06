#!/usr/bin/env python3
"""Certify optima for p6zeta v2 candidate instances with HiGHS (scipy.optimize.milp).

Same authoring method as v1 (see grounding.yaml: "author-computed via
scipy.optimize.milp HiGHS backend"). For every *.ip.json under --instances it
writes one JSON record to --out/<instance_id>.opt.json:

  {"instance_id", "family", "status": "optimal" | "unproven",
   "objective_value", "variables", "solver": "highs", "solver_wall_seconds",
   "mip_gap"}

Only records with status "optimal" (HiGHS proved optimality within --time-limit)
are eligible for the hidden set. `solver_wall_seconds` is the L3 hardness oracle,
exactly as in v1.

Runs at most --workers instances at a time. Use `nice -n 19` around it when a
trajectory is live on the same host.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix


def solve_one(path: str, time_limit: float) -> dict:
    d = json.load(open(path))
    n = d["n_vars"]
    c = np.array(d["objective_coefficients"], dtype=float)
    if d["objective_sense"] == "max":
        c = -c
    rows, lb, ub = [], [], []
    for con in d["constraints"]:
        rows.append(con["coefficients"])
        if con["sense"] == "<=":
            lb.append(-np.inf); ub.append(con["rhs"])
        elif con["sense"] == ">=":
            lb.append(con["rhs"]); ub.append(np.inf)
        else:
            lb.append(con["rhs"]); ub.append(con["rhs"])
    A = csr_matrix(np.array(rows, dtype=float))
    t0 = time.perf_counter()
    res = milp(c, constraints=LinearConstraint(A, lb, ub), integrality=np.ones(n),
               bounds=Bounds(0, 1), options={"time_limit": time_limit, "disp": False,
                                             "mip_rel_gap": 0.0})
    wall = time.perf_counter() - t0
    rec = {"instance_id": d["instance_id"], "family": d["family"], "solver": "highs",
           "solver_wall_seconds": round(wall, 3), "status": "unproven",
           "objective_value": None, "variables": None, "mip_gap": None,
           "highs_status": int(res.status), "highs_message": str(res.message)[:120]}
    if res.status == 0 and res.x is not None:  # optimal, proven
        x = [int(round(v)) for v in res.x]
        obj = float(sum(ci * xi for ci, xi in zip(d["objective_coefficients"], x)))
        rec.update(status="optimal", objective_value=obj, variables=x,
                   mip_gap=float(getattr(res, "mip_gap", 0.0) or 0.0))
    elif res.x is not None:  # time limit with incumbent: record but do not certify
        x = [int(round(v)) for v in res.x]
        rec.update(objective_value=float(sum(ci * xi for ci, xi in zip(d["objective_coefficients"], x))),
                   variables=x, mip_gap=float(getattr(res, "mip_gap", 1.0) or 1.0))
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--time-limit", type=float, default=300.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    paths = sorted(str(p) for p in a.instances.glob("*.ip.json"))
    if a.skip_existing:
        done = {p.stem.replace(".opt", "") for p in a.out.glob("*.opt.json")}
        paths = [p for p in paths if Path(p).name.replace(".ip.json", "") not in done]
    print(f"{len(paths)} instances, {a.workers} workers, time limit {a.time_limit}s", flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(solve_one, p, a.time_limit): p for p in paths}
        for f in as_completed(futs):
            rec = f.result()
            (a.out / f"{rec['instance_id']}.opt.json").write_text(json.dumps(rec) + "\n")
            print(f"{rec['instance_id']:60s} {rec['status']:9s} {rec['solver_wall_seconds']:8.1f}s "
                  f"obj={rec['objective_value']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
