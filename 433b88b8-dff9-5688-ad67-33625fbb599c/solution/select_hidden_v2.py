#!/usr/bin/env python3
"""Select the v2 hidden set from certified candidates and write the judge data.

Inputs
  --candidates DIR   *.ip.json produced by generate_instances_v2.py
  --optima DIR       *.opt.json produced by compute_optima_v2.py
  --probes DIR...    optional: directories of a frontier solver's outputs on the
                     candidates (<iid>.out.json), used only to REPORT how hard the
                     chosen set is for a real from-scratch solver under 60 s
  --out-instances DIR, --out-optima FILE

Rules
  * only candidates HiGHS proved optimal are eligible
  * per family, take the target count (30 MDK, 10 each otherwise) preferring
    the candidates with the LONGEST HiGHS wall time (hardest for an exact
    solver), but keep the original 000.. numbering by renumbering the chosen
    instances densely so ids stay p6zeta__hidden__<family>__NNN
  * hidden_optima.json has the v1 schema: family, instance_id, objective_value,
    solver_wall_seconds (L3 hardness oracle), status, variables, plus
    cross_verified=True and solver="highs"
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

TARGET = {"multi-dimensional-knapsack": 30, "zero-one-knapsack": 10, "set-cover": 10,
          "generalized-assignment": 10, "capacitated-facility-location": 10,
          "graph-coloring-ip": 10, "tsp-cutting-plane-ip": 10}


def gap(reported, optimum, sense):
    if reported is None or optimum is None:
        return None
    d = max(abs(optimum), 1.0)
    return max(0.0, (optimum - reported) / d) if sense == "max" else max(0.0, (reported - optimum) / d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, type=Path)
    ap.add_argument("--optima", required=True, type=Path)
    ap.add_argument("--probes", nargs="*", type=Path, default=[])
    ap.add_argument("--out-instances", required=True, type=Path)
    ap.add_argument("--out-optima", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    recs = {}
    for p in a.optima.glob("*.opt.json"):
        r = json.load(open(p))
        recs[r["instance_id"]] = r
    by_fam = {}
    for p in sorted(a.candidates.glob("*.ip.json")):
        d = json.load(open(p))
        r = recs.get(d["instance_id"])
        if not r or r["status"] != "optimal":
            continue
        by_fam.setdefault(d["family"], []).append((r["solver_wall_seconds"], p, d, r))

    chosen = []
    print(f"{'family':32s} certified  chosen  highs_s(min/med/max of chosen)")
    for fam, target in TARGET.items():
        pool = sorted(by_fam.get(fam, []), key=lambda t: -t[0])  # hardest first
        pick = pool[:target]
        pick.sort(key=lambda t: t[1].name)  # stable order for renumbering
        ts = [t[0] for t in pick]
        print(f"{fam:32s} {len(pool):9d}  {len(pick):6d}  "
              f"{min(ts) if ts else 0:.1f}/{sorted(ts)[len(ts)//2] if ts else 0:.1f}/{max(ts) if ts else 0:.1f}")
        if len(pick) < target:
            print(f"  !! only {len(pick)} certified candidates for {fam}, need {target}")
        for k, (_, p, d, r) in enumerate(pick):
            chosen.append((fam, k, p, d, r))

    # probe report: how a real 60 s solver did on the chosen set
    for probe in a.probes:
        solved = total = 0
        credits = []
        for fam, k, p, d, r in chosen:
            op = probe / f"{d['instance_id']}.out.json"
            total += 1
            try:
                o = json.loads(op.read_text())
                g = gap(o.get("objective_value"), r["objective_value"], d["objective_sense"])
                if o.get("status") in ("optimal", "feasible") and g is not None:
                    credits.append(g)
                    if g <= 1e-9:
                        solved += 1
                else:
                    credits.append(None)
            except Exception:
                credits.append(None)
        ok = [c for c in credits if c is not None]
        print(f"probe {probe.name}: gap 0 on {solved}/{total}; feasible answers {len(ok)}/{total}; "
              f"median gap {sorted(ok)[len(ok)//2] if ok else 'n/a'}")

    if a.dry_run:
        return 0
    a.out_instances.mkdir(parents=True, exist_ok=True)
    for f in a.out_instances.glob("*.ip.json"):
        f.unlink()
    optima = {}
    for fam, k, p, d, r in chosen:
        new_id = f"p6zeta__hidden__{fam.replace('-', '_')}__{k:03d}"
        d = dict(d)
        d["instance_id"] = new_id
        (a.out_instances / f"{new_id}.ip.json").write_text(
            json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n")
        optima[new_id] = {
            "cross_verified": True,
            "family": fam,
            "instance_id": new_id,
            "objective_value": r["objective_value"],
            "solver": "highs",
            "solver_wall_seconds": r["solver_wall_seconds"],
            "status": "optimal",
            "variables": r["variables"],
        }
    a.out_optima.write_text(json.dumps(optima, sort_keys=True, indent=1) + "\n")
    print(f"wrote {len(chosen)} instances and optima")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
