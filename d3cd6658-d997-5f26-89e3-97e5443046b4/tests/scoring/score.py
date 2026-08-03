#!/usr/bin/env python3
"""
score.py — per-lane scoring for sec_leverage_trajectory_projection_book.

Contract SHA: cb68e81c405253bb6aa8642eb0aad9d3b7e063f049bc5f9c45876b131793e3e5
Framework:    B (reference-anchored projector, PKW-FAMILIES §3)

Lane weights match seed/contract.yaml.reference_emulation exactly:
    L1 composite_trajectory_rank_correlation  20 pts
    L2 refinancing_risk_direction             15 pts
    L3 extreme_mover_detection                15 pts
    L4 delta_liabilities_growth_ranking       10 pts
    L5 interest_coverage_direction            10 pts
    L6 composite_position_pnl                 10 pts
    L7 anti_fabrication                        5 pts
    L8 cross_quarter_stability                10 pts
                                              ----
    Base                                      95  (+ 5 free padding = 100)
    leverage_cycle_bonus                      10  (additive over 100)
    Total scale                               0-110

Anchors calibrated per Baker-Wurgler 2002 JF + Frank-Goyal 2009 JFE +
Fama-French 2015 literature. NEVER moved to hit a desired score band per
requirements/MEPHISTO.md §1.2.
"""
from __future__ import annotations

import math
import statistics
from typing import Any

LANE_WEIGHTS: dict[str, float] = {
    "L1_composite_trajectory_rank_correlation": 20.0,
    "L2_refinancing_risk_direction": 15.0,
    "L3_extreme_mover_detection": 15.0,
    "L4_delta_liabilities_growth_ranking": 10.0,
    "L5_interest_coverage_direction": 10.0,
    "L6_composite_position_pnl": 10.0,
    "L7_anti_fabrication": 5.0,
    "L8_cross_quarter_stability": 10.0,
}
LANE_BASE_TOTAL = sum(LANE_WEIGHTS.values())
FREE_PADDING = 5.0
BONUS_MAX = 10.0
GRAND_MAX = 110.0

L1_IC_FLOOR = 0.00
L1_IC_FULL = 0.50

L2_ACC_FLOOR = 0.33
L2_ACC_FULL = 1.00

L3_F1_FLOOR = 0.10
L3_F1_FULL = 1.00

L4_IC_FLOOR = 0.00
L4_IC_FULL = 0.70

L5_ACC_FLOOR = 0.33
L5_ACC_FULL = 0.70

L6_SHARPE_FLOOR = 0.00
L6_SHARPE_FULL = 5.00

L7_TOLERANCES: dict[str, float] = {
    "L1_composite_trajectory_rank_correlation_est": 0.15,
    "L2_refinancing_risk_direction_accuracy_est": 0.15,
    "L3_extreme_mover_detection_f1_est": 0.15,
    "L4_delta_liabilities_growth_ranking_ic_est": 0.15,
    "L5_interest_coverage_direction_accuracy_est": 0.15,
}

L8_VARIANCE_BASELINE = 0.10

BONUS_SATURATION_PRECISION = 0.85


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _linear_score(value: float, floor: float, full: float, pts: float) -> float:
    if not math.isfinite(value):
        return 0.0
    if full > floor:
        if value <= floor:
            return 0.0
        if value >= full:
            return pts
        return pts * (value - floor) / (full - floor)
    if value >= floor:
        return 0.0
    if value <= full:
        return pts
    return pts * (floor - value) / (floor - full)


def _spearman_rank(values: list[float]) -> list[float]:
    n = len(values)
    if n == 0:
        return []
    indexed = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[indexed[j + 1]] == values[indexed[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman_ic(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 3:
        return 0.0
    rx = _spearman_rank(xs)
    ry = _spearman_rank(ys)
    n = len(rx)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    num = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    dx = math.sqrt(sum((r - mean_x) ** 2 for r in rx))
    dy = math.sqrt(sum((r - mean_y) ** 2 for r in ry))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _index_by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    return {(r["period"], int(r["cik"])): r for r in rows}


def _paired_by_key(
    sub: dict[tuple[str, int], dict[str, Any]],
    truth: dict[tuple[str, int], dict[str, Any]],
    field_sub: str,
    field_truth: str,
) -> list[tuple[str, int, float, float]]:
    out: list[tuple[str, int, float, float]] = []
    for key in sorted(set(sub.keys()) & set(truth.keys())):
        pk, cik = key
        a = sub[key].get(field_sub)
        b = truth[key].get(field_truth)
        if a is None or b is None:
            continue
        if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
            continue
        if not (math.isfinite(a) and math.isfinite(b)):
            continue
        out.append((pk, cik, float(a), float(b)))
    return out


def _lane_result(lane: str, sub_score: float, reason: str) -> dict[str, Any]:
    return {
        "lane": lane,
        "sub_score": round(float(sub_score), 4),
        "max": LANE_WEIGHTS.get(lane, BONUS_MAX),
        "reason": reason,
    }


def score_l1_composite_ic(sub_rows, truth_rows) -> dict[str, Any]:
    if not sub_rows:
        return _lane_result("L1_composite_trajectory_rank_correlation", 0.0, "empty submission")
    sub = _index_by_key(sub_rows)
    truth = _index_by_key(truth_rows)
    pairs = _paired_by_key(sub, truth, "composite_score", "price_response_20d_proxy")
    if not pairs:
        return _lane_result("L1_composite_trajectory_rank_correlation", 0.0,
                            "no paired (composite_score, price_response_20d_proxy)")
    per_q: dict[str, tuple[list[float], list[float]]] = {}
    for pk, _cik, a, b in pairs:
        xs, ys = per_q.setdefault(pk, ([], []))
        xs.append(a)
        ys.append(b)
    ics: list[float] = []
    for pk in sorted(per_q):
        xs, ys = per_q[pk]
        ics.append(_spearman_ic(xs, ys))
    ic_mean = statistics.fmean(ics) if ics else 0.0
    pts = _linear_score(ic_mean, L1_IC_FLOOR, L1_IC_FULL,
                        LANE_WEIGHTS["L1_composite_trajectory_rank_correlation"])
    return _lane_result(
        "L1_composite_trajectory_rank_correlation",
        pts,
        f"mean per-quarter Spearman IC = {ic_mean:.4f} over {len(ics)} quarters "
        f"(anchor {L1_IC_FLOOR}->0pt, {L1_IC_FULL}->{LANE_WEIGHTS['L1_composite_trajectory_rank_correlation']}pt)",
    )


def score_l2_refi_direction(sub_rows, truth_rows) -> dict[str, Any]:
    if not sub_rows:
        return _lane_result("L2_refinancing_risk_direction", 0.0, "empty submission")
    sub = _index_by_key(sub_rows)
    truth = _index_by_key(truth_rows)
    matched = 0
    total = 0
    for key in sorted(set(sub.keys()) & set(truth.keys())):
        t_dir = truth[key].get("refi_direction")
        s_dir = sub[key].get("refi_direction")
        if t_dir not in ("risk_up", "neutral", "risk_down"):
            continue
        total += 1
        if s_dir == t_dir:
            matched += 1
    if total == 0:
        return _lane_result("L2_refinancing_risk_direction", 0.0,
                            "no truth-side refi_direction labels")
    acc = matched / total
    pts = _linear_score(acc, L2_ACC_FLOOR, L2_ACC_FULL,
                        LANE_WEIGHTS["L2_refinancing_risk_direction"])
    return _lane_result(
        "L2_refinancing_risk_direction",
        pts,
        f"3-class accuracy = {acc:.4f} ({matched}/{total}) "
        f"(anchor {L2_ACC_FLOOR}->0pt, {L2_ACC_FULL}->{LANE_WEIGHTS['L2_refinancing_risk_direction']}pt)",
    )


def score_l3_extreme_f1(sub_rows, truth_rows) -> dict[str, Any]:
    if not sub_rows:
        return _lane_result("L3_extreme_mover_detection", 0.0, "empty submission")
    sub = _index_by_key(sub_rows)
    truth = _index_by_key(truth_rows)
    tp = fp = fn = tn = 0
    for key in sorted(set(sub.keys()) & set(truth.keys())):
        t_ext = bool(truth[key].get("in_top_decile")) or bool(truth[key].get("in_bottom_decile"))
        s_ext = bool(sub[key].get("in_top_decile")) or bool(sub[key].get("in_bottom_decile"))
        if t_ext and s_ext:
            tp += 1
        elif (not t_ext) and s_ext:
            fp += 1
        elif t_ext and (not s_ext):
            fn += 1
        else:
            tn += 1
    if tp + fp + fn == 0:
        return _lane_result("L3_extreme_mover_detection", 0.0,
                            "no positive extremes in either submission or truth")
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    pts = _linear_score(f1, L3_F1_FLOOR, L3_F1_FULL,
                        LANE_WEIGHTS["L3_extreme_mover_detection"])
    return _lane_result(
        "L3_extreme_mover_detection",
        pts,
        f"F1 = {f1:.4f} (P={precision:.3f} R={recall:.3f} TP={tp} FP={fp} FN={fn} TN={tn}) "
        f"(anchor {L3_F1_FLOOR}->0pt, {L3_F1_FULL}->{LANE_WEIGHTS['L3_extreme_mover_detection']}pt)",
    )


def score_l4_delta_liab_ic(sub_rows, delta_liab_yoy) -> dict[str, Any]:
    if not sub_rows:
        return _lane_result("L4_delta_liabilities_growth_ranking", 0.0, "empty submission")
    if not delta_liab_yoy:
        return _lane_result("L4_delta_liabilities_growth_ranking", 0.0,
                            "no realized Liabilities/Assets YoY available in truth")
    sub = _index_by_key(sub_rows)
    per_q: dict[str, tuple[list[float], list[float]]] = {}
    for key in sorted(sub.keys()):
        pk, cik = key
        rank = sub[key].get("peer_rank_percentile")
        liab_delta = delta_liab_yoy.get(key)
        if rank is None or liab_delta is None:
            continue
        if not (isinstance(rank, (int, float)) and math.isfinite(rank)
                and isinstance(liab_delta, (int, float)) and math.isfinite(liab_delta)):
            continue
        xs, ys = per_q.setdefault(pk, ([], []))
        xs.append(float(rank))
        ys.append(-float(liab_delta))
    if not per_q:
        return _lane_result("L4_delta_liabilities_growth_ranking", 0.0,
                            "no paired (peer_rank_percentile, delta_liab_yoy)")
    ics = [_spearman_ic(xs, ys) for pk, (xs, ys) in sorted(per_q.items())]
    ic_mean = statistics.fmean(ics)
    pts = _linear_score(ic_mean, L4_IC_FLOOR, L4_IC_FULL,
                        LANE_WEIGHTS["L4_delta_liabilities_growth_ranking"])
    return _lane_result(
        "L4_delta_liabilities_growth_ranking",
        pts,
        f"mean per-quarter Spearman IC = {ic_mean:.4f} over {len(ics)} quarters "
        f"(anchor {L4_IC_FLOOR}->0pt, {L4_IC_FULL}->{LANE_WEIGHTS['L4_delta_liabilities_growth_ranking']}pt)",
    )


def score_l5_coverage_direction(sub_rows, coverage_dir_truth) -> dict[str, Any]:
    if not sub_rows:
        return _lane_result("L5_interest_coverage_direction", 0.0, "empty submission")
    if not coverage_dir_truth:
        return _lane_result("L5_interest_coverage_direction", 0.0,
                            "no realized coverage-direction labels in truth")
    sub = _index_by_key(sub_rows)
    matched = 0
    total = 0
    for key in sorted(sub.keys()):
        t_dir = coverage_dir_truth.get(key)
        if t_dir not in ("up", "flat", "down"):
            continue
        cs = sub[key].get("composite_score")
        if cs is None or not isinstance(cs, (int, float)) or not math.isfinite(cs):
            continue
        s_dir = "up" if cs > 0.10 else ("down" if cs < -0.10 else "flat")
        total += 1
        if s_dir == t_dir:
            matched += 1
    if total == 0:
        return _lane_result("L5_interest_coverage_direction", 0.0,
                            "no scoreable (composite_score, coverage_direction) pairs")
    acc = matched / total
    pts = _linear_score(acc, L5_ACC_FLOOR, L5_ACC_FULL,
                        LANE_WEIGHTS["L5_interest_coverage_direction"])
    return _lane_result(
        "L5_interest_coverage_direction",
        pts,
        f"3-class direction accuracy = {acc:.4f} ({matched}/{total}) "
        f"(anchor {L5_ACC_FLOOR}->0pt, {L5_ACC_FULL}->{LANE_WEIGHTS['L5_interest_coverage_direction']}pt)",
    )


def score_l6_positioning_sharpe(sub_rows, truth_rows) -> dict[str, Any]:
    if not sub_rows:
        return _lane_result("L6_composite_position_pnl", 0.0, "empty submission")
    sub = _index_by_key(sub_rows)
    truth = _index_by_key(truth_rows)
    per_q_pnl: dict[str, float] = {}
    for key in sorted(set(sub.keys()) & set(truth.keys())):
        pk, _cik = key
        w = sub[key].get("position_weight")
        r = truth[key].get("price_response_20d_proxy")
        if w is None or r is None:
            continue
        if not (isinstance(w, (int, float)) and math.isfinite(w)):
            continue
        if not (isinstance(r, (int, float)) and math.isfinite(r)):
            continue
        per_q_pnl[pk] = per_q_pnl.get(pk, 0.0) + float(w) * float(r)
    if len(per_q_pnl) < 3:
        return _lane_result(
            "L6_composite_position_pnl",
            0.0,
            f"insufficient positioning quarters ({len(per_q_pnl)}); need >= 3 for Sharpe",
        )
    pnls = [per_q_pnl[pk] for pk in sorted(per_q_pnl)]
    mu = statistics.fmean(pnls)
    sd = statistics.pstdev(pnls)
    sharpe = mu / sd * math.sqrt(4.0) if sd > 1e-12 else 0.0
    capped = _clip(sharpe, 0.0, L6_SHARPE_FULL)
    pts = LANE_WEIGHTS["L6_composite_position_pnl"] * (capped / L6_SHARPE_FULL)
    return _lane_result(
        "L6_composite_position_pnl",
        pts,
        f"positioning Sharpe (quarterly, annualized) = {sharpe:.4f} over {len(pnls)} quarters "
        f"(cap {L6_SHARPE_FULL}; mean_pnl={mu:.5f} sd_pnl={sd:.5f})",
    )


def score_l7_anti_fabrication(self_reported, judge_recomputed) -> dict[str, Any]:
    if not isinstance(self_reported, dict):
        return _lane_result("L7_anti_fabrication", 0.0,
                            "self_reported_metrics missing or not a dict")
    violations: list[str] = []
    for key, tol in L7_TOLERANCES.items():
        sr = self_reported.get(key)
        jm = judge_recomputed.get(key)
        if sr is None or jm is None:
            continue
        if not (isinstance(sr, (int, float)) and isinstance(jm, (int, float))
                and math.isfinite(sr) and math.isfinite(jm)):
            violations.append(f"{key}: nonfinite (sr={sr}, jm={jm})")
            continue
        if abs(float(sr) - float(jm)) > tol:
            violations.append(f"{key}: sr={sr:.4f} vs judge={jm:.4f} (tol {tol})")
    if violations:
        return _lane_result(
            "L7_anti_fabrication",
            0.0,
            "fabrication tolerances exceeded: " + "; ".join(violations),
        )
    return _lane_result(
        "L7_anti_fabrication",
        LANE_WEIGHTS["L7_anti_fabrication"],
        "self_reported vs judge_recomputed agree within tolerance",
    )


def score_l8_cross_quarter_stability(sub_rows, truth_rows,
                                     delta_liab_yoy, coverage_dir_truth) -> dict[str, Any]:
    if not sub_rows:
        return _lane_result("L8_cross_quarter_stability", 0.0, "empty submission")
    sub = _index_by_key(sub_rows)
    quarters = sorted({k[0] for k in sub.keys()})
    if len(quarters) < 2:
        return _lane_result(
            "L8_cross_quarter_stability",
            0.5 * LANE_WEIGHTS["L8_cross_quarter_stability"],
            f"only {len(quarters)} test quarter(s); stability lane uncomputable, default 50%",
        )
    per_q_norms: list[float] = []
    for pk in quarters:
        pk_sub = [r for r in sub_rows if r["period"] == pk]
        pk_truth = [r for r in truth_rows if r["period"] == pk]
        pk_delta = {k: v for k, v in delta_liab_yoy.items() if k[0] == pk}
        pk_cov = {k: v for k, v in coverage_dir_truth.items() if k[0] == pk}
        parts: list[float] = []
        parts.append(score_l1_composite_ic(pk_sub, pk_truth)["sub_score"]
                     / LANE_WEIGHTS["L1_composite_trajectory_rank_correlation"])
        parts.append(score_l2_refi_direction(pk_sub, pk_truth)["sub_score"]
                     / LANE_WEIGHTS["L2_refinancing_risk_direction"])
        parts.append(score_l3_extreme_f1(pk_sub, pk_truth)["sub_score"]
                     / LANE_WEIGHTS["L3_extreme_mover_detection"])
        parts.append(score_l4_delta_liab_ic(pk_sub, pk_delta)["sub_score"]
                     / LANE_WEIGHTS["L4_delta_liabilities_growth_ranking"])
        parts.append(score_l5_coverage_direction(pk_sub, pk_cov)["sub_score"]
                     / LANE_WEIGHTS["L5_interest_coverage_direction"])
        per_q_norms.append(statistics.fmean(parts))
    mean_perf = statistics.fmean(per_q_norms)
    var_perf = statistics.pvariance(per_q_norms) if len(per_q_norms) >= 2 else 0.0
    var_frac = _clip(1.0 - var_perf / max(L8_VARIANCE_BASELINE, 1e-9), 0.0, 1.0)
    pts = LANE_WEIGHTS["L8_cross_quarter_stability"] * mean_perf * var_frac
    return _lane_result(
        "L8_cross_quarter_stability",
        pts,
        f"mean_norm={mean_perf:.4f} var_norm={var_perf:.5f} var_frac={var_frac:.4f} "
        f"across {len(per_q_norms)} quarters",
    )


def score_leverage_cycle_bonus(sub_rows, truth_rows, refi_cycle_turn_truth) -> dict[str, Any]:
    if not sub_rows or not refi_cycle_turn_truth:
        return {
            "lane": "leverage_cycle_bonus",
            "sub_score": 0.0,
            "max": BONUS_MAX,
            "reason": "no submission or no realized refi-cycle-turn labels in truth",
        }
    sub = _index_by_key(sub_rows)
    tp = fp = fn = 0
    for key, is_turn in refi_cycle_turn_truth.items():
        s_row = sub.get(key)
        if s_row is None:
            continue
        s_flag = bool(s_row.get("in_top_decile"))
        if is_turn and s_flag:
            tp += 1
        elif (not is_turn) and s_flag:
            fp += 1
        elif is_turn and (not s_flag):
            fn += 1
    denom = tp + fp
    if denom == 0:
        return {
            "lane": "leverage_cycle_bonus",
            "sub_score": 0.0,
            "max": BONUS_MAX,
            "reason": "no submitted top-decile flags overlap with refi-cycle-turn truth",
        }
    precision = tp / denom
    pts = BONUS_MAX * _clip(precision / BONUS_SATURATION_PRECISION, 0.0, 1.0)
    return {
        "lane": "leverage_cycle_bonus",
        "sub_score": round(float(pts), 4),
        "max": BONUS_MAX,
        "reason": (
            f"precision={precision:.4f} (TP={tp} FP={fp} FN={fn}); "
            f"saturates at precision >= {BONUS_SATURATION_PRECISION}"
        ),
    }


def aggregate(lane_scores, bonus) -> dict[str, Any]:
    base_total = sum(x["sub_score"] for x in lane_scores) + FREE_PADDING
    grand_total = base_total + bonus["sub_score"]
    grand_total = _clip(grand_total, 0.0, GRAND_MAX)
    return {
        "lane_scores": lane_scores,
        "bonus": bonus,
        "free_padding": FREE_PADDING,
        "base_total": round(base_total, 4),
        "grand_total": round(grand_total, 4),
        "grand_max": GRAND_MAX,
    }
