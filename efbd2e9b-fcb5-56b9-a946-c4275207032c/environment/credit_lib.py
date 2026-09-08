"""Metric + scoring definitions for the community-bank credit-review triage book.

PUBLIC ON PURPOSE. The agent gets this file. Nothing here is secret. The only
secret is the realized Q1-2026 net charge-off outcome the judge holds. The task
is credit-surveillance skill, not scorer-guessing.

THE FLOOR IS THE COPY FRONTIER. Score 0 on every lane is the measured best of
the mechanical single-column books on this exact universe (sort by boundary
NCO, 5-quarter historical-mean NCO, boundary noncurrent NPERFV, boundary
provision ELNATR; each a 270-name equal-weight book). Sorting any one column
therefore earns approximately nothing: points exist only ABOVE the best
mechanical strategy. Full marks on every lane is the hindsight oracle (the 271
banks with the worst realized Q1-2026 rate, the best constraint-feasible
hindsight book), which no boundary-time policy
reaches. Anchors were measured offline on 2026-08-06 and are frozen; do not
re-tune.

Pure standard library: no numpy (a file-reading module would defeat the
allowlist gate that keeps the hidden answer key off the policy's reach) and no
random/time (they would make a submission score differently on two runs).
"""
from __future__ import annotations

# ---- universe geometry (measured 2026-08-06, frozen) -----------------------
ASSET_LO = 100000            # thousands USD: $100M
ASSET_HI = 1000000           # thousands USD: $1B (exclusive)
K_NAMES = 271                # the review budget spreads over >= 271 banks (cap 0.0037)
MAX_WEIGHT = 0.0037          # ~1/270 per-bank cap
SUM_TOL = 1e-6
TAIL_PCT = 0.10              # worst decile by realized rate
DETER_PP = 0.25              # deterioration: Q1 rate rose > 0.25pp vs own boundary

# ---- lanes: linear between the copy frontier (0) and the oracle (full) -----
# floor = per-lane best of the four mechanical copy books; full = hindsight
# oracle. Measured on the real graded window and frozen.
LANES = {
    "T1_decile_coverage":      {"points": 35.0, "floor": 36.9811, "full": 99.631},
    "T2_nco_captured_pp":      {"points": 40.0, "floor": 0.4947,  "full": 0.9736},
    "T3_deterioration_capture": {"points": 25.0, "floor": 13.0597, "full": 53.1365},
}
LANE_ORDER = ["T1_decile_coverage", "T2_nco_captured_pp", "T3_deterioration_capture"]

VIOLATION_PENALTY = 0.05
VIOLATION_PENALTY_CAP = 0.30

FEATURE_COLS = ["CERT", "NAME", "ASSET", "DEP", "NETINC", "ROA", "ROE",
                "NTLNLSR", "NPERFV", "P3ASSET", "P9ASSET", "RBC1AAJ", "RBCT1J",
                "RBCRWAJ", "LNATRES", "ELNATR", "NIMY", "LNLSNET", "LNCRCD",
                "LNCONOTH", "LNRENRES", "EQ", "LNLSGR", "DRLNLS", "CRLNLS"]
_NUMERIC = tuple(c for c in FEATURE_COLS if c not in ("CERT", "NAME"))


def coerce(row):
    """CSV strings -> typed dict. Missing numerics become None, never 0.0: a
    bank with no reported ratio is not a bank with a zero ratio."""
    out = {"CERT": row.get("CERT", "").strip(), "NAME": row.get("NAME", "")}
    for k in _NUMERIC:
        v = row.get(k, "")
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            out[k] = None
    return out


def eligible(rows):
    """Boundary-only universe filter: community banks with a reported NCO rate
    and $100M <= assets < $1B. Survivorship-safe by construction."""
    out = []
    for r in rows:
        if r.get("NTLNLSR") is None or r.get("ASSET") is None:
            continue
        if ASSET_LO <= r["ASSET"] < ASSET_HI:
            out.append(r)
    return out


def equal_weight_book(certs):
    """The un-triaged desk: capacity spread evenly. A legal submission; it
    scores 0 because it sits far below the copy frontier."""
    n = len(certs)
    return {c: 1.0 / n for c in certs}


def check_constraints(w, universe_ids, cons=None):
    """Return a list of violation dicts. Pure."""
    max_weight = (cons or {}).get("max_weight", MAX_WEIGHT)
    sum_tol = (cons or {}).get("sum_tolerance", SUM_TOL)
    v = []
    ids = set(universe_ids)
    total = 0.0
    max_w = 0.0
    for c, x in w.items():
        if not isinstance(x, (int, float)) or x != x or x in (float("inf"), float("-inf")):
            v.append({"check": "finite_weights", "cert": c})
            return v
        if x < 0:
            v.append({"check": "nonnegative_weights", "cert": c})
        if c not in ids:
            v.append({"check": "unknown_cert", "cert": c})
        total += x
        max_w = max(max_w, x)
    if abs(total - 1.0) > sum_tol:
        v.append({"check": "weights_sum", "sum": total})
    if max_w > max_weight + 1e-12:
        v.append({"check": "max_weight", "max_weight": max_w, "limit": max_weight})
    return v


def _median(xs):
    s = sorted(xs)
    n = len(s)
    m = n // 2
    return s[m] if n % 2 else 0.5 * (s[m - 1] + s[m])


def book_metrics(w, outcomes):
    """Recompute every graded quantity from the realized cross-section.

    w        : {cert: weight} as submitted (raw).
    outcomes : {cert: {"nco": realized Q1-2026 rate, "nco_boundary": FY2025
               rate}} - the graded universe (banks that filed Q1-2026).
    Weights on filed names are renormalized to sum to 1; each metric is the
    share of the review BUDGET landing on each realized cohort.
    """
    certs = sorted(outcomes)
    n = len(certs)
    if n == 0:
        return None
    realized = [outcomes[c]["nco"] for c in certs]
    bench = sum(realized) / n
    k = max(1, round(TAIL_PCT * n))
    dec_cut = sorted(realized, reverse=True)[k - 1]

    held = {c: x for c, x in w.items() if c in outcomes and x > 0}
    tw = sum(held.values())
    if tw <= 0:
        return None
    nw = {c: x / tw for c, x in held.items()}

    book_nco = sum(nw[c] * outcomes[c]["nco"] for c in nw)
    cov = 100.0 * sum(nw[c] for c in nw if outcomes[c]["nco"] >= dec_cut)
    deter = 100.0 * sum(
        nw[c] for c in nw
        if outcomes[c]["nco_boundary"] is not None
        and outcomes[c]["nco"] - outcomes[c]["nco_boundary"] > DETER_PP)

    return {
        "T1_decile_coverage": cov,
        "T2_nco_captured_pp": book_nco - bench,
        "T3_deterioration_capture": deter,
        # diagnostics (realized magnitudes - the judge redacts these from the
        # agent-facing report; they are answer-key aggregates)
        "book_realized_nco": book_nco,
        "bench_realized_nco": bench,
        "decile_cutoff": dec_cut,
        "n_graded_universe": n,
        "n_names_held": len(held),
        "effective_names": (1.0 / sum(x * x for x in nw.values())) if nw else 0.0,
        "median_universe_nco": _median(realized),
    }


def score(m):
    """0-100 lane scores. Each lane is linear between its frozen copy-frontier
    floor (0 points) and its frozen oracle full (max points), clamped."""
    out = {}
    for name in LANE_ORDER:
        cfg = LANES[name]
        lo, hi = cfg["floor"], cfg["full"]
        x = m[name]
        frac = 0.0 if hi == lo else max(0.0, min(1.0, (x - lo) / (hi - lo)))
        out[name] = frac * cfg["points"]
    return out


def total_score(s, violations, cons=None):
    """Sum the performance lanes, then apply the compliance multiplier.

    The concentration penalty is proportionate to the SIZE of a max_weight
    breach, not just the count: a book betting the whole review budget on a
    handful of banks is not "slightly" out of mandate, and the
    diversification floor (>= 270 names via the cap) is load-bearing. Still a
    capped multiplier; hygiene earns no points.
    """
    max_weight = (cons or {}).get("max_weight", MAX_WEIGHT)
    pen = 0.0
    for v in violations:
        pen += VIOLATION_PENALTY
        if v.get("check") == "max_weight":
            ratio = v["max_weight"] / max_weight
            pen += VIOLATION_PENALTY * min(ratio - 1.0, 10.0)
    pen = min(pen, VIOLATION_PENALTY_CAP)
    return sum(s.values()) * (1.0 - pen), pen
