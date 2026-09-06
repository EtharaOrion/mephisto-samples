#!/usr/bin/env python3
"""p6zeta v2 instance generator.

Same seven families and the same JSON schema as v1 (dense coefficient rows,
binary variables, one of <=, >=, ==), but sized and structured so that a good
from-scratch 0-1 IP solver does NOT reach the proven optimum on every instance
inside the 60-second per-instance budget. v1's hidden set was solved to gap 0 on
all 90 instances by the first frontier run within 40 minutes, which left lane 2
(30 points) with no discriminating power.

Hardness comes from structure, not from size alone, because the format stores
every row densely (file size ~ rows x n_vars):

  multi-dimensional-knapsack   Chu-Beasley correlated profits, tight capacities
  zero-one-knapsack            almost-subset-sum and strongly/inversely correlated, coefficients to 10^6 (defeats DP)
  set-cover                    dense random cover, near-unicost costs (fractional LP)
  generalized-assignment       Martello-Toth type D min-cost (exact assignment, 5-8 machines x 40-60 jobs)
  capacitated-facility-location aggregated capacity only (weak LP), tight capacity
  graph-coloring-ip            dense graphs, DSATUR-tight colour budget, symmetry-breaking rows
  tsp-cutting-plane-ip         all subtour rows enumerated, 10-11 cities

Determinism: every instance is a pure function of (BASE_SEED, family, split,
index) via sha256, exactly like v1's derivation rule.

Usage:
  python3 generate_instances_v2.py --out <dir> --split hidden --candidates 2
  python3 generate_instances_v2.py --out <dir> --split dev

--candidates N emits N x the target count per family so that compute_optima_v2.py
can keep the ones HiGHS certifies within its time cap and that sit in the target
hardness band. Optima are NOT computed here.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

BASE_SEED = 20260905

FAMILY_MDK = "multi-dimensional-knapsack"
FAMILY_K01 = "zero-one-knapsack"
FAMILY_SC = "set-cover"
FAMILY_GAP = "generalized-assignment"
FAMILY_CFL = "capacitated-facility-location"
FAMILY_GC = "graph-coloring-ip"
FAMILY_TSP = "tsp-cutting-plane-ip"

TARGET_HIDDEN = {FAMILY_MDK: 30, FAMILY_K01: 10, FAMILY_SC: 10, FAMILY_GAP: 10,
                 FAMILY_CFL: 10, FAMILY_GC: 10, FAMILY_TSP: 10}
TARGET_DEV = {FAMILY_MDK: 1, FAMILY_K01: 1, FAMILY_SC: 1, FAMILY_GAP: 1,
              FAMILY_CFL: 1, FAMILY_GC: 1, FAMILY_TSP: 1}


def rng_for(family: str, split: str, index: int) -> random.Random:
    digest = hashlib.sha256(f"{BASE_SEED}|{family}|{split}|{index}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def iid(family: str, split: str, index: int) -> str:
    return f"p6zeta__{split}__{family.replace('-', '_')}__{index:03d}"


def row(coefs: List[float], rhs: float, sense: str) -> Dict:
    return {"coefficients": coefs, "rhs": rhs, "sense": sense}


def inst(family: str, split: str, index: int, sense: str, obj: List[float],
         cons: List[Dict], comment: str) -> Dict:
    return {
        "comment": comment,
        "constraints": cons,
        "family": family,
        "instance_id": iid(family, split, index),
        "n_vars": len(obj),
        "objective_coefficients": obj,
        "objective_sense": sense,
    }


# ---------------------------------------------------------------- families

def gen_mdk(split: str, index: int) -> Dict:
    r = rng_for(FAMILY_MDK, split, index)
    n = r.choice([100, 120, 150, 180])
    m = r.choice([5, 8, 10, 15])
    alpha = r.choice([0.25, 0.25, 0.5, 0.75])
    w = [[r.randint(1, 1000) for _ in range(n)] for _ in range(m)]
    # Chu-Beasley: profit correlated with average weight plus noise
    p = [int(sum(w[i][j] for i in range(m)) / m + r.randint(0, 500)) for j in range(n)]
    cons = [row(w[i], int(alpha * sum(w[i])), "<=") for i in range(m)]
    return inst(FAMILY_MDK, split, index, "max", p, cons,
                f"{FAMILY_MDK}:n={n},m={m},tightness={alpha}")


def gen_k01(split: str, index: int) -> Dict:
    r = rng_for(FAMILY_K01, split, index)
    # Kinds are weighted toward what an exact solver can still certify in minutes:
    # almost-subset-sum profits (hard for B&B, certifiable) twice as often as the
    # strongly/inversely correlated kinds, which are capped at n=1000 because HiGHS
    # cannot prove them at n>=1500 within the certification budget.
    kind = r.choice(["subset_sum_like", "subset_sum_like", "strongly", "inverse"])
    n = r.choice([1000, 1500, 2000, 3000]) if kind == "subset_sum_like" else r.choice([500, 700, 1000])
    R = 1_000_000
    w = [r.randint(R // 10, R) for _ in range(n)]
    if kind == "strongly":
        p = [wj + R // 10 for wj in w]
    elif kind == "inverse":
        p = [wj for wj in w]
        w = [pj + R // 10 for pj in p]
    else:  # almost subset-sum: profits equal weights with small noise
        p = [wj + r.randint(-1000, 1000) for wj in w]
    cap = int(0.5 * sum(w))
    return inst(FAMILY_K01, split, index, "max", p, [row(w, cap, "<=")],
                f"{FAMILY_K01}:n={n},capacity={cap},kind={kind}")


def gen_sc(split: str, index: int) -> Dict:
    r = rng_for(FAMILY_SC, split, index)
    n_sub = r.choice([300, 400, 500])
    n_el = r.choice([150, 200, 250])
    cover: List[set] = [set() for _ in range(n_sub)]
    # denser cover (each element in 6..12 subsets) with near-unicost costs: the LP
    # relaxation is fractional and many subsets tie, which is what makes exact
    # set cover hard; size-correlated costs make it LP-integral and trivial.
    for e in range(n_el):
        for s in r.sample(range(n_sub), r.randint(6, 12)):
            cover[s].add(e)
    for s in range(n_sub):
        if not cover[s]:
            cover[s].add(r.randrange(n_el))
    cost = [r.randint(1, 3) for _ in range(n_sub)]
    cons = []
    for e in range(n_el):
        cons.append(row([1 if e in cover[s] else 0 for s in range(n_sub)], 1, ">="))
    return inst(FAMILY_SC, split, index, "min", cost, cons,
                f"{FAMILY_SC}:n_subsets={n_sub},n_elements={n_el},near_unicost")


def gen_gap(split: str, index: int) -> Dict:
    r = rng_for(FAMILY_GAP, split, index)
    machines = r.choice([5, 6, 8])
    jobs = r.choice([40, 50, 60])
    # Martello-Toth type D, as a MINIMISATION: weights U[1,100], cost 111 - w + U[-10,10].
    # Cheap assignments are the heavy ones, so the tight capacities bind and the LP
    # relaxation is fractional; a maximisation of the same numbers is LP-integral.
    w = [[r.randint(1, 100) for _ in range(jobs)] for _ in range(machines)]
    cost = [[max(1, 111 - w[i][j] + r.randint(-10, 10)) for j in range(jobs)] for i in range(machines)]
    n = machines * jobs
    obj = [cost[i][j] for i in range(machines) for j in range(jobs)]
    cons = []
    for j in range(jobs):  # each job assigned to exactly one machine
        c = [0] * n
        for i in range(machines):
            c[i * jobs + j] = 1
        cons.append(row(c, 1, "=="))
    for i in range(machines):  # capacity: 0.8 * (sum of this machine's weights) / machines
        c = [0] * n
        for j in range(jobs):
            c[i * jobs + j] = w[i][j]
        cons.append(row(c, int(0.8 * sum(w[i]) / machines), "<="))
    return inst(FAMILY_GAP, split, index, "min", obj, cons,
                f"{FAMILY_GAP}:jobs={jobs},machines={machines},type=D,min-cost")


def gen_cfl(split: str, index: int) -> Dict:
    r = rng_for(FAMILY_CFL, split, index)
    F = r.choice([15, 20, 25])
    C = r.choice([40, 50, 60])
    fx = [(r.uniform(0, 100), r.uniform(0, 100)) for _ in range(F)]
    cx = [(r.uniform(0, 100), r.uniform(0, 100)) for _ in range(C)]
    demand = [r.randint(5, 35) for _ in range(C)]
    total = sum(demand)
    cap = [int(total / F * r.uniform(1.6, 2.4)) for _ in range(F)]
    fixed = [int(r.uniform(300, 900) + 0.6 * cap[f]) for f in range(F)]
    assign = [[int(demand[c] * (abs(fx[f][0] - cx[c][0]) + abs(fx[f][1] - cx[c][1])) / 10) + 1
               for c in range(C)] for f in range(F)]
    # variables: x_fc (F*C) then y_f (F)
    n = F * C + F
    obj = [assign[f][c] for f in range(F) for c in range(C)] + fixed
    cons = []
    for c in range(C):  # each customer served exactly once
        row_c = [0] * n
        for f in range(F):
            row_c[f * C + c] = 1
        cons.append(row(row_c, 1, "=="))
    for f in range(F):  # aggregated capacity: sum d_c x_fc - cap_f y_f <= 0  (weak LP)
        row_f = [0] * n
        for c in range(C):
            row_f[f * C + c] = demand[c]
        row_f[F * C + f] = -cap[f]
        cons.append(row(row_f, 0, "<="))
    return inst(FAMILY_CFL, split, index, "min", obj, cons,
                f"{FAMILY_CFL}:facilities={F},customers={C},aggregated_capacity")


def _dsatur(V: int, adj: List[set]) -> int:
    colour = [-1] * V
    for _ in range(V):
        best, bsat, bdeg = -1, -1, -1
        for v in range(V):
            if colour[v] >= 0:
                continue
            sat = len({colour[u] for u in adj[v] if colour[u] >= 0})
            if sat > bsat or (sat == bsat and len(adj[v]) > bdeg):
                best, bsat, bdeg = v, sat, len(adj[v])
        used = {colour[u] for u in adj[best] if colour[u] >= 0}
        k = 0
        while k in used:
            k += 1
        colour[best] = k
    return max(colour) + 1


def gen_gc(split: str, index: int) -> Dict:
    r = rng_for(FAMILY_GC, split, index)
    V = r.choice([26, 28, 30, 32])
    p_edge = r.choice([0.5, 0.55, 0.6, 0.65])
    edges = [(u, v) for u, v in itertools.combinations(range(V), 2) if r.random() < p_edge]
    for u in range(V - 1):  # keep it connected
        if (u, u + 1) not in edges:
            edges.append((u, u + 1))
    edges = sorted(set(edges))
    adj: List[set] = [set() for _ in range(V)]
    for u, v in edges:
        adj[u].add(v); adj[v].add(u)
    # colour budget = DSATUR greedy bound: feasible by construction, no slack to hide in
    K = _dsatur(V, adj)
    n = V * K + K  # x_vk then y_k ; minimise colours used
    obj = [0] * (V * K) + [1] * K
    cons = []
    for v in range(V):  # exactly one colour per vertex
        c = [0] * n
        for k in range(K):
            c[v * K + k] = 1
        cons.append(row(c, 1, "=="))
    for (u, v) in edges:  # adjacent vertices differ; a colour must be open to be used
        for k in range(K):
            c = [0] * n
            c[u * K + k] = 1
            c[v * K + k] = 1
            c[V * K + k] = -1
            cons.append(row(c, 0, "<="))
    for k in range(K - 1):  # symmetry breaking: colour k+1 only if colour k is used
        c = [0] * n
        c[V * K + k] = -1
        c[V * K + k + 1] = 1
        cons.append(row(c, 0, "<="))
    return inst(FAMILY_GC, split, index, "min", obj, cons,
                f"{FAMILY_GC}:n_v={V},K={K},edges={len(edges)},p={p_edge},dsatur_budget,symbreak")


def gen_tsp(split: str, index: int) -> Dict:
    r = rng_for(FAMILY_TSP, split, index)
    N = r.choice([10, 11])
    pts = [(r.randint(0, 100), r.randint(0, 100)) for _ in range(N)]
    pairs = list(itertools.combinations(range(N), 2))
    n = len(pairs)
    pos = {pr: i for i, pr in enumerate(pairs)}
    dist = [int(round(((pts[a][0] - pts[b][0]) ** 2 + (pts[a][1] - pts[b][1]) ** 2) ** 0.5)) + 1
            for a, b in pairs]
    cons = []
    for v in range(N):  # degree 2
        c = [0] * n
        for u in range(N):
            if u != v:
                c[pos[(min(u, v), max(u, v))]] = 1
        cons.append(row(c, 2, "=="))
    # subtour elimination for every subset S with 2 <= |S| <= N-2 (each once)
    for size in range(2, N - 1):
        for S in itertools.combinations(range(N), size):
            if 0 not in S and size > N // 2:
                continue  # complementary subsets are equivalent given degree rows
            c = [0] * n
            for a, b in itertools.combinations(S, 2):
                c[pos[(a, b)]] = 1
            cons.append(row(c, size - 1, "<="))
    return inst(FAMILY_TSP, split, index, "min", dist, cons,
                f"{FAMILY_TSP}:n={N},edges={n},subtour_rows={len(cons) - N}")


GENERATORS = {
    FAMILY_MDK: gen_mdk, FAMILY_K01: gen_k01, FAMILY_SC: gen_sc, FAMILY_GAP: gen_gap,
    FAMILY_CFL: gen_cfl, FAMILY_GC: gen_gc, FAMILY_TSP: gen_tsp,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--split", choices=["hidden", "dev"], default="hidden")
    ap.add_argument("--candidates", type=int, default=1,
                    help="multiplier on the target count per family")
    ap.add_argument("--families", nargs="*", default=None)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    targets = TARGET_HIDDEN if a.split == "hidden" else TARGET_DEV
    written = 0
    for fam, count in targets.items():
        if a.families and fam not in a.families:
            continue
        for idx in range(count * a.candidates):
            d = GENERATORS[fam](a.split, idx)
            path = a.out / f"{d['instance_id']}.ip.json"
            path.write_text(json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n")
            written += 1
    print(f"wrote {written} instances to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
