#!/usr/bin/env python3
"""
leverage_trajectory_reference.py - JUDGE-SIDE Framework B reference solver
for sec_leverage_trajectory_projection_book.

Contract SHA: cb68e81c405253bb6aa8642eb0aad9d3b7e063f049bc5f9c45876b131793e3e5
Framework:    B (reference-anchored projector, PKW-FAMILIES §3)
Boundary:     PRIVATE (judge-only). NEVER shipped into the work image.
              Method-family class names (see seed/TRUTH.md) are OPAQUE per
              contract.boundaries.leak_gate_invariant and NEVER appear in
              this file. Only function names appear.

Numeric contract: byte-identical to seed/recompute.py functions:
  - compute_trajectory_scores (5-quarter rolling slope on Liab/Assets +
    NetDebt/Assets + InterestCoverage)
  - compute_peer_delta_ranks (Assets-decile peer grouping)
  - compute_refi_surprises (DGS10 trailing-4Q change x LTD/Assets percentile)
  - compute_extremes_and_positioning (top/bottom decile with rate-cycle overlay)
  - price_response_proxy (Baker-Wurgler 2002 JF anchored, hash-seeded noise)

CLI:
  python3 leverage_trajectory_reference.py \
      --input-dir dataset/d3cd6658-d997-5f26-89e3-97e5443046b4/ \
      --output    trajectory_results.json

Determinism guarantees:
  - PYTHONHASHSEED=0 at process spawn
  - No numpy / pandas / scipy: stdlib only (matches seed/recompute.py imports)
  - Sorted iteration on every dict / set
  - JSON output uses sort_keys=True
  - price_response_proxy noise seeded from sha256(cik|period) - reproducible
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import random
import statistics
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTHONHASHSEED", "0")

TRAIN_QUARTERS: list[tuple[int, int]] = [(y, q) for y in range(2018, 2025) for q in (1, 2, 3, 4)]
TEST_QUARTERS: list[tuple[int, int]] = [(2025, q) for q in (1, 2, 3, 4)] + [(2026, 1)]

CONCEPTS_STOCK_USD = [
    "Assets", "Liabilities", "StockholdersEquity", "LongTermDebt",
    "ShortTermBorrowings", "CashAndCashEquivalentsAtCarryingValue",
]
CONCEPTS_FLOW_USD = ["InterestExpense", "OperatingIncomeLoss", "NetIncomeLoss"]

PEER_DECILE_N = 10
TRAJECTORY_WINDOW_QUARTERS = 5

PRICE_RESPONSE_ALPHA = 0.03
PRICE_RESPONSE_COMPOSITE_CAP = 2.0
PRICE_RESPONSE_NOISE_AMPLITUDE = 0.02

TOP_DECILE_CUTOFF = 0.90
BOTTOM_DECILE_CUTOFF = 0.10

REFI_RATE_CHANGE_BPS_THRESHOLD = 25.0
REFI_LEVERAGE_PERCENTILE_HIGH = 0.60
REFI_LEVERAGE_PERCENTILE_LOW = 0.40


def _period_key(y: int, q: int) -> str:
    return f"{y}Q{q}"


def _q_offset(pk: str, n: int) -> str:
    y = int(pk[:4]); q = int(pk[-1])
    idx = y * 4 + (q - 1) - n
    return f"{idx // 4}Q{(idx % 4) + 1}"


def _q_index(pk: str) -> int:
    y = int(pk[:4]); q = int(pk[-1])
    return y * 4 + (q - 1)


def _linear_slope(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


def _liab_over_assets(r: dict[str, Any]) -> float | None:
    liab = r.get("Liabilities"); assets = r.get("Assets")
    if liab is None or assets is None or assets == 0:
        return None
    return float(liab) / float(assets)


def _net_debt_over_assets(r: dict[str, Any]) -> float | None:
    ltd = r.get("LongTermDebt")
    st = r.get("ShortTermBorrowings") or 0.0
    cash = r.get("CashAndCashEquivalentsAtCarryingValue") or 0.0
    assets = r.get("Assets")
    if ltd is None or assets is None or assets == 0:
        return None
    return (float(ltd) + float(st) - float(cash)) / float(assets)


def _interest_coverage(r: dict[str, Any]) -> float | None:
    op = r.get("OperatingIncomeLoss"); ie = r.get("InterestExpense")
    if op is None or ie is None or ie == 0:
        return None
    return float(op) / float(ie)


def compute_trajectory_scores(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    per_cik: dict[int, dict[str, dict[str, Any]]] = {}
    for r in rows:
        per_cik.setdefault(r["cik"], {})[r["period"]] = r

    raw: dict[tuple[str, int], dict[str, Any]] = {}
    for cik, periods in per_cik.items():
        for pk, r in periods.items():
            window_pks = [pk] + [_q_offset(pk, n) for n in range(1, TRAJECTORY_WINDOW_QUARTERS)]
            liab_vals: list[tuple[float, float]] = []
            netd_vals: list[tuple[float, float]] = []
            cov_vals: list[tuple[float, float]] = []
            for w_pk in window_pks:
                w_r = periods.get(w_pk)
                if w_r is None:
                    continue
                x = float(_q_index(w_pk))
                lv = _liab_over_assets(w_r)
                nv = _net_debt_over_assets(w_r)
                cv = _interest_coverage(w_r)
                if lv is not None:
                    liab_vals.append((x, lv))
                if nv is not None:
                    netd_vals.append((x, nv))
                if cv is not None:
                    cov_vals.append((x, cv))

            dl = None
            if len(liab_vals) >= 3:
                sl = _linear_slope([xv for xv, _ in liab_vals], [yv for _, yv in liab_vals])
                dl = None if sl is None else -sl
            nds = None
            if len(netd_vals) >= 3:
                sl = _linear_slope([xv for xv, _ in netd_vals], [yv for _, yv in netd_vals])
                nds = None if sl is None else -sl
            ci = None
            if len(cov_vals) >= 3:
                ci = _linear_slope([xv for xv, _ in cov_vals], [yv for _, yv in cov_vals])

            raw[(pk, cik)] = {"deleverage_slope": dl, "net_debt_shrink": nds, "coverage_improvement": ci}

    by_period: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for (pk, cik), comps in raw.items():
        by_period.setdefault(pk, []).append((cik, comps))

    z_scored: dict[tuple[str, int], dict[str, Any]] = {}
    for pk, cik_comps in by_period.items():
        for comp_name in ("deleverage_slope", "net_debt_shrink", "coverage_improvement"):
            vals = [(cik, c[comp_name]) for cik, c in cik_comps if c[comp_name] is not None]
            if len(vals) < 3:
                continue
            values = [v for _, v in vals]
            mean = statistics.fmean(values)
            std = max(statistics.pstdev(values), 1e-9)
            for cik, v in vals:
                key = (pk, cik)
                if key not in z_scored:
                    z_scored[key] = {"z_deleverage_slope": None, "z_net_debt_shrink": None,
                                     "z_coverage_improvement": None}
                z_scored[key][f"z_{comp_name}"] = (v - mean) / std

    result: dict[tuple[str, int], dict[str, Any]] = {}
    for key, raw_comps in raw.items():
        zs = z_scored.get(key, {})
        components = [zs.get(f"z_{c}") for c in ("deleverage_slope", "net_debt_shrink", "coverage_improvement")]
        non_null = [c for c in components if c is not None]
        composite = statistics.fmean(non_null) if len(non_null) >= 2 else None
        result[key] = {**raw_comps, "composite_score": composite, "n_components": len(non_null),
                       "z_deleverage_slope": zs.get("z_deleverage_slope"),
                       "z_net_debt_shrink": zs.get("z_net_debt_shrink"),
                       "z_coverage_improvement": zs.get("z_coverage_improvement")}
    return result


def compute_peer_delta_ranks(scores, assets_by_quarter, xbrl_rows) -> dict[tuple[str, int], dict[str, Any]]:
    la_now: dict[tuple[str, int], float] = {}
    for r in xbrl_rows:
        v = _liab_over_assets(r)
        if v is not None:
            la_now[(r["period"], r["cik"])] = v

    result: dict[tuple[str, int], dict[str, Any]] = {}
    by_period: dict[str, list[tuple[int, float, float | None]]] = {}
    for (pk, cik), row in scores.items():
        assets = assets_by_quarter.get(pk, {}).get(cik)
        if assets is None:
            continue
        by_period.setdefault(pk, []).append((cik, assets, row.get("composite_score")))

    for pk, entries in by_period.items():
        entries.sort(key=lambda t: (t[1], t[0]))
        n = len(entries)
        for i, (cik, _assets, _score) in enumerate(entries):
            decile = min(9, (i * PEER_DECILE_N) // max(n, 1))
            result[(pk, cik)] = {"assets_decile": decile}
        for decile_val in range(PEER_DECILE_N):
            decile_entries = [(cik, score) for cik, _, score in entries
                              if result[(pk, cik)]["assets_decile"] == decile_val and score is not None]
            decile_entries.sort(key=lambda t: (t[1], t[0]))
            m = len(decile_entries)
            for rank_i, (cik, _) in enumerate(decile_entries):
                result[(pk, cik)]["peer_rank_percentile"] = (rank_i + 0.5) / m if m > 0 else 0.5
        all_scored = [(cik, score) for cik, _, score in entries if score is not None]
        all_scored.sort(key=lambda t: (t[1], t[0]))
        for rank_i, (cik, _) in enumerate(all_scored):
            result[(pk, cik)]["global_rank_percentile"] = (rank_i + 0.5) / len(all_scored) if all_scored else 0.5
        for cik, _assets, _score in entries:
            key = (pk, cik)
            la_now_v = la_now.get(key)
            la_prev_v = la_now.get((_q_offset(pk, 4), cik))
            if la_now_v is not None and la_prev_v is not None:
                result[key]["delta_liab_over_assets_yoy"] = la_now_v - la_prev_v
            else:
                result[key]["delta_liab_over_assets_yoy"] = None

    return result


def compute_refi_surprises(ranks, xbrl_rows, macro_rows) -> dict[tuple[str, int], dict[str, Any]]:
    dgs10_monthly = [(r["month"], r.get("DGS10")) for r in macro_rows if r.get("DGS10") is not None]
    monthly_map = {m: v for m, v in dgs10_monthly}

    def _quarter_avg_dgs10(pk: str) -> float | None:
        y = int(pk[:4]); q = int(pk[-1])
        months = [f"{y}-{((q - 1) * 3 + i):02d}" for i in (1, 2, 3)]
        vals = [monthly_map[m] for m in months if m in monthly_map]
        return statistics.fmean(vals) if vals else None

    ltd_over_assets: dict[tuple[str, int], float] = {}
    for r in xbrl_rows:
        ltd = r.get("LongTermDebt"); assets = r.get("Assets")
        if ltd is None or assets is None or assets == 0:
            continue
        ltd_over_assets[(r["period"], r["cik"])] = float(ltd) / float(assets)

    by_period_decile: dict[tuple[str, int], list[tuple[int, float]]] = {}
    for (pk, cik), val in ltd_over_assets.items():
        decile = ranks.get((pk, cik), {}).get("assets_decile")
        if decile is None:
            continue
        by_period_decile.setdefault((pk, decile), []).append((cik, val))

    ltd_percentile: dict[tuple[str, int], float] = {}
    for (pk, decile), entries in by_period_decile.items():
        entries.sort(key=lambda t: (t[1], t[0]))
        m = len(entries)
        for rank_i, (cik, _) in enumerate(entries):
            ltd_percentile[(pk, cik)] = (rank_i + 0.5) / m if m > 0 else 0.5

    result: dict[tuple[str, int], dict[str, Any]] = {}
    for (pk, cik) in sorted(ranks.keys()):
        rate_now = _quarter_avg_dgs10(pk)
        rate_lag4 = _quarter_avg_dgs10(_q_offset(pk, 4))
        if rate_now is None or rate_lag4 is None:
            direction = "neutral"
            rate_change_bps = None
        else:
            rate_change_bps = 100.0 * (rate_now - rate_lag4)
            filer_ltd_pct = ltd_percentile.get((pk, cik))
            if filer_ltd_pct is None:
                direction = "neutral"
            else:
                if rate_change_bps > REFI_RATE_CHANGE_BPS_THRESHOLD and filer_ltd_pct >= REFI_LEVERAGE_PERCENTILE_HIGH:
                    direction = "risk_up"
                elif rate_change_bps < -REFI_RATE_CHANGE_BPS_THRESHOLD and filer_ltd_pct <= REFI_LEVERAGE_PERCENTILE_LOW:
                    direction = "risk_down"
                else:
                    direction = "neutral"
        result[(pk, cik)] = {"refi_direction": direction,
                             "rate_change_bps_4q": None if rate_change_bps is None else round(rate_change_bps, 4),
                             "filer_ltd_percentile": ltd_percentile.get((pk, cik))}
    return result


def compute_extremes_and_positioning(ranks, universe, refi):
    extremes: dict[tuple[str, int], dict[str, Any]] = {}
    positions: dict[str, list[dict[str, Any]]] = {}
    for pk in sorted(universe.keys(), key=lambda pk: (int(pk[:4]), int(pk[-1]))):
        entries = [(cik, ranks.get((pk, cik), {}).get("global_rank_percentile"))
                   for cik in universe[pk]]
        entries = [(cik, p) for cik, p in entries if p is not None]
        entries.sort(key=lambda t: (t[1], t[0]))
        if not entries:
            positions[pk] = []
            continue
        long_ciks = [cik for cik, p in entries if p >= TOP_DECILE_CUTOFF]
        short_ciks = [cik for cik, p in entries if p <= BOTTOM_DECILE_CUTOFF]
        n_long = max(len(long_ciks), 1)
        n_short = max(len(short_ciks), 1)
        book: list[dict[str, Any]] = []
        for cik, p in entries:
            weight = 0.0
            in_top = p >= TOP_DECILE_CUTOFF
            in_bot = p <= BOTTOM_DECILE_CUTOFF
            r_dir = refi.get((pk, cik), {}).get("refi_direction", "neutral")
            if in_top:
                weight = (1.0 / n_long) * (1.10 if r_dir == "risk_down" else 1.0)
            elif in_bot:
                weight = (-1.0 / n_short) * (1.10 if r_dir == "risk_up" else 1.0)
            extremes[(pk, cik)] = {"in_top_decile": in_top, "in_bottom_decile": in_bot,
                                   "rank_percentile": p}
            if weight != 0.0:
                book.append({"cik": cik, "weight": round(weight, 6), "rank_percentile": p,
                             "refi_direction": r_dir})
        book.sort(key=lambda d: (-d["weight"], d["cik"]))
        positions[pk] = book
    return extremes, positions


def price_response_proxy(cik: int, period: str, composite: float | None) -> float:
    if composite is None:
        composite = 0.0
    clipped = max(-PRICE_RESPONSE_COMPOSITE_CAP, min(PRICE_RESPONSE_COMPOSITE_CAP, composite))
    core = PRICE_RESPONSE_ALPHA * clipped / PRICE_RESPONSE_COMPOSITE_CAP
    h = hashlib.sha256(f"{cik}|{period}".encode()).digest()
    rng = random.Random(int.from_bytes(h[:8], "big"))
    noise = rng.uniform(-PRICE_RESPONSE_NOISE_AMPLITUDE, PRICE_RESPONSE_NOISE_AMPLITUDE)
    return round(core + noise, 6)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _assets_by_quarter(xbrl: list[dict[str, Any]]) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for r in xbrl:
        assets = r.get("Assets")
        if assets is None:
            continue
        out.setdefault(r["period"], {})[int(r["cik"])] = float(assets)
    return out


def _universe_from_flags(universe_rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    universe: dict[str, set[int]] = {}
    for row in universe_rows:
        if row.get("exit"):
            continue
        universe.setdefault(row["period"], set()).add(int(row["cik"]))
    return {pk: sorted(ciks) for pk, ciks in universe.items()}


def run_reference(input_dir: Path) -> dict[str, Any]:
    train_xbrl = _read_jsonl(input_dir / "train" / "xbrl.jsonl")
    test_xbrl = _read_jsonl(input_dir / "test" / "xbrl.jsonl")
    train_universe_rows = _read_jsonl(input_dir / "train" / "universe.jsonl")
    test_universe_rows = _read_jsonl(input_dir / "test" / "universe.jsonl")
    train_macro = _read_jsonl(input_dir / "train" / "macro.jsonl")
    test_macro = _read_jsonl(input_dir / "test" / "macro.jsonl")
    with (input_dir / "test" / "test_filer_quarters.json").open("r") as f:
        test_targets = json.load(f)

    all_xbrl = train_xbrl + test_xbrl
    all_macro = train_macro + test_macro
    universe = _universe_from_flags(train_universe_rows + test_universe_rows)
    assets = _assets_by_quarter(all_xbrl)

    scores = compute_trajectory_scores(all_xbrl)
    ranks = compute_peer_delta_ranks(scores, assets, all_xbrl)
    refi = compute_refi_surprises(ranks, all_xbrl, all_macro)
    extremes, positions = compute_extremes_and_positioning(ranks, universe, refi)

    test_periods = {_period_key(y, q) for y, q in TEST_QUARTERS}

    per_filer_quarter: list[dict[str, Any]] = []
    targets_sorted = sorted([(t["period"], int(t["cik"])) for t in test_targets],
                            key=lambda t: (t[0], t[1]))
    for pk, cik in targets_sorted:
        if pk not in test_periods:
            continue
        key = (pk, cik)
        s = scores.get(key, {})
        r = ranks.get(key, {})
        refi_row = refi.get(key, {})
        ex = extremes.get(key, {})
        composite = s.get("composite_score")
        peer_pct = r.get("peer_rank_percentile")
        global_pct = r.get("global_rank_percentile")

        direction = refi_row.get("refi_direction", "neutral")
        rc = refi_row.get("rate_change_bps_4q")
        confidence = min(1.0, abs(rc) / 100.0) if rc is not None else 0.0

        proxy = price_response_proxy(cik, pk, composite) if composite is not None else 0.0

        in_top = bool(ex.get("in_top_decile", False))
        in_bot = bool(ex.get("in_bottom_decile", False))
        if in_top or in_bot:
            extreme_prob = 1.0
        elif global_pct is not None:
            edge = min(global_pct, 1.0 - global_pct)
            extreme_prob = max(0.0, 1.0 - edge / 0.10)
            extreme_prob = round(extreme_prob, 6)
        else:
            extreme_prob = 0.0

        n_top = sum(1 for _pk, _cik in extremes if _pk == pk and extremes[(_pk, _cik)].get("in_top_decile"))
        n_bot = sum(1 for _pk, _cik in extremes if _pk == pk and extremes[(_pk, _cik)].get("in_bottom_decile"))
        if in_top:
            weight = (1.0 / max(n_top, 1)) * (1.10 if direction == "risk_down" else 1.0)
        elif in_bot:
            weight = (-1.0 / max(n_bot, 1)) * (1.10 if direction == "risk_up" else 1.0)
        else:
            weight = 0.0
        weight = round(weight, 6)

        per_filer_quarter.append({
            "cik": cik, "period": pk,
            "composite_score": round(composite, 6) if composite is not None else None,
            "peer_rank_percentile": round(peer_pct, 6) if peer_pct is not None else None,
            "global_rank_percentile": round(global_pct, 6) if global_pct is not None else None,
            "refi_direction": direction,
            "refi_confidence": round(confidence, 6),
            "extreme_probability": extreme_prob,
            "in_top_decile": in_top,
            "in_bottom_decile": in_bot,
            "position_weight": weight,
            "price_response_20d_proxy": proxy,
        })

    n = len(per_filer_quarter)
    n_top = sum(1 for r in per_filer_quarter if r["in_top_decile"])
    n_bot = sum(1 for r in per_filer_quarter if r["in_bottom_decile"])
    n_risk_up = sum(1 for r in per_filer_quarter if r["refi_direction"] == "risk_up")
    n_risk_down = sum(1 for r in per_filer_quarter if r["refi_direction"] == "risk_down")
    n_neutral = sum(1 for r in per_filer_quarter if r["refi_direction"] == "neutral")

    per_quarter_pnl: dict[str, float] = {}
    for pk in sorted({r["period"] for r in per_filer_quarter}):
        pnl = sum(r["position_weight"] * r["price_response_20d_proxy"]
                  for r in per_filer_quarter if r["period"] == pk)
        per_quarter_pnl[pk] = round(pnl, 6)

    self_reported = {
        "L1_composite_trajectory_rank_correlation_est": 0.17,
        "L2_refinancing_risk_direction_accuracy_est": 1.0,
        "L3_extreme_mover_detection_f1_est": 1.0,
        "L4_delta_liabilities_growth_ranking_ic_est": 0.78,
        "L5_interest_coverage_direction_accuracy_est": 0.53,
        "L6_composite_position_pnl_sharpe_est": None,
        "L8_cross_quarter_stability_est": None,
        "n_predictions": n,
        "n_top_decile": n_top,
        "n_bottom_decile": n_bot,
        "n_risk_up": n_risk_up,
        "n_risk_down": n_risk_down,
        "n_neutral": n_neutral,
        "per_quarter_positioning_pnl": per_quarter_pnl,
    }

    return {
        "task_id": "sec_leverage_trajectory_projection_book",
        "bundle_uuid": "d3cd6658-d997-5f26-89e3-97e5443046b4",
        "generated_by": "leverage_trajectory_reference.py (Framework B judge-side reference)",
        "per_filer_quarter": per_filer_quarter,
        "self_reported_metrics": self_reported,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FORGE Phase 2 Framework B reference solver (sec_leverage_trajectory_projection_book)",
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = run_reference(args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(results, sort_keys=True, indent=2) + "\n"
    args.output.write_text(body)
    print(f"reference solver produced {len(results['per_filer_quarter'])} filer-quarter predictions -> {args.output}")


if __name__ == "__main__":
    main()
