#!/usr/bin/env python3
from __future__ import annotations

import math
import statistics
from typing import Any

LANE_WEIGHTS: dict[str, float] = {
    "L1_ladder_return_lane": 20.0,
    "L2_repo_regime_classification": 15.0,
    "L3_extreme_stress_detection": 15.0,
    "L4_bill_supply_direction_ranking": 10.0,
    "L5_ny_fed_pd_position_change": 10.0,
    "L6_money_market_pnl_proxy": 10.0,
    "L7_anti_fabrication": 5.0,
    "L8_cross_week_stability": 10.0,
}
LANE_BASE_TOTAL = sum(LANE_WEIGHTS.values())
FREE_PADDING = 5.0
BONUS_MAX = 10.0
GRAND_MAX = 110.0

L1_SHARPE_FLOOR = 0.0
L1_SHARPE_FULL = 1.5

L2_ACC_FLOOR = 0.25
L2_ACC_FULL = 0.85

L3_F1_FLOOR = 0.10
L3_F1_FULL = 0.85

L4_ACC_FLOOR = 0.33
L4_ACC_FULL = 0.85

L5_ACC_FLOOR = 0.33
L5_ACC_FULL = 0.75

L6_SHARPE_FLOOR = 0.0
L6_SHARPE_FULL = 1.5

L7_TOLERANCES: dict[str, float] = {
    "L1_ladder_return_lane_est": 0.20,
    "L2_regime_classification_est": 0.20,
    "L3_extreme_stress_detection_est": 0.20,
    "L4_supply_direction_est": 0.20,
    "L6_money_market_pnl_proxy_est": 0.20,
    "L8_cross_week_stability_est": 0.20,
}

L8_VARIANCE_BASELINE = 0.08
BONUS_SATURATION = 0.75

BINS = ["b4w", "b8w", "b13w", "b26w", "rrp", "iorb"]


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
    return 0.0


def _lane_result(lane: str, sub_score: float, reason: str) -> dict[str, Any]:
    return {
        "lane": lane,
        "sub_score": round(float(sub_score), 4),
        "max": LANE_WEIGHTS.get(lane, BONUS_MAX),
        "reason": reason,
    }


def _index_by_date(rows: list[dict]) -> dict[str, dict]:
    return {r["date"]: r for r in rows}


def score_l1_ladder_return(sub_rows: list[dict], true_returns: dict[str, dict]) -> dict:
    sub = _index_by_date(sub_rows)
    daily_pnl: list[float] = []
    for d in sorted(set(sub) & set(true_returns)):
        alloc = sub[d].get("allocation") or {}
        rets = true_returns[d]
        pnl = 0.0
        for b in BINS:
            w = float(alloc.get(b) or 0.0)
            r = rets.get(b)
            if r is None:
                continue
            pnl += w * float(r)
        if math.isfinite(pnl):
            daily_pnl.append(pnl)
    if len(daily_pnl) < 5:
        return _lane_result("L1_ladder_return_lane", 0.0,
                            f"insufficient paired dates ({len(daily_pnl)})")
    mu = statistics.fmean(daily_pnl)
    sd = statistics.pstdev(daily_pnl)
    sharpe = 0.0 if sd < 1e-12 else mu/sd * math.sqrt(252.0)
    capped = _clip(sharpe, 0.0, L1_SHARPE_FULL)
    pts = LANE_WEIGHTS["L1_ladder_return_lane"] * (capped / L1_SHARPE_FULL)
    return _lane_result("L1_ladder_return_lane", pts,
                        f"Sharpe (annualized) = {sharpe:.4f} over {len(daily_pnl)} dates "
                        f"(cap {L1_SHARPE_FULL}; mu={mu:.6f} sd={sd:.6f})")


def score_l2_repo_regime(sub_rows: list[dict], true_regimes: dict[str, str]) -> dict:
    sub = _index_by_date(sub_rows)
    matched = 0; total = 0
    for d in sorted(set(sub) & set(true_regimes)):
        t = true_regimes[d]
        s = sub[d].get("regime_label")
        if t is None:
            continue
        total += 1
        if s == t:
            matched += 1
    if total == 0:
        return _lane_result("L2_repo_regime_classification", 0.0, "no truth regimes")
    acc = matched/total
    pts = _linear_score(acc, L2_ACC_FLOOR, L2_ACC_FULL, LANE_WEIGHTS["L2_repo_regime_classification"])
    return _lane_result("L2_repo_regime_classification", pts,
                        f"accuracy = {acc:.4f} ({matched}/{total}) "
                        f"(anchor {L2_ACC_FLOOR}->0pt, {L2_ACC_FULL}->{LANE_WEIGHTS['L2_repo_regime_classification']}pt)")


def score_l3_extreme_stress(sub_rows: list[dict], true_stress: dict[str, bool]) -> dict:
    sub = _index_by_date(sub_rows)
    tp = fp = fn = tn = 0
    for d in sorted(set(sub) & set(true_stress)):
        t = bool(true_stress[d])
        s = bool(sub[d].get("extreme_stress_flag"))
        if t and s: tp += 1
        elif not t and s: fp += 1
        elif t and not s: fn += 1
        else: tn += 1
    if tp + fp + fn == 0:
        return _lane_result("L3_extreme_stress_detection", 0.0,
                            "no positive stress events in submission or truth")
    prec = tp/(tp+fp) if (tp+fp) > 0 else 0.0
    rec = tp/(tp+fn) if (tp+fn) > 0 else 0.0
    f1 = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0.0
    pts = _linear_score(f1, L3_F1_FLOOR, L3_F1_FULL, LANE_WEIGHTS["L3_extreme_stress_detection"])
    return _lane_result("L3_extreme_stress_detection", pts,
                        f"F1 = {f1:.4f} (P={prec:.3f} R={rec:.3f} TP={tp} FP={fp} FN={fn} TN={tn})")


def score_l4_bill_supply_direction(sub_rows: list[dict], true_supply_dir: dict[str, str]) -> dict:
    sub = _index_by_date(sub_rows)
    matched = 0; total = 0
    for d in sorted(set(sub) & set(true_supply_dir)):
        t = true_supply_dir[d]
        s = sub[d].get("supply_direction")
        if t is None:
            continue
        total += 1
        if s == t:
            matched += 1
    if total == 0:
        return _lane_result("L4_bill_supply_direction_ranking", 0.0, "no truth supply directions")
    acc = matched/total
    pts = _linear_score(acc, L4_ACC_FLOOR, L4_ACC_FULL, LANE_WEIGHTS["L4_bill_supply_direction_ranking"])
    return _lane_result("L4_bill_supply_direction_ranking", pts,
                        f"accuracy = {acc:.4f} ({matched}/{total})")


def score_l5_pd_position(sub_rows: list[dict], true_pd: dict[str, str]) -> dict:
    if not true_pd:
        return _lane_result("L5_ny_fed_pd_position_change", 0.5 * LANE_WEIGHTS["L5_ny_fed_pd_position_change"],
                            "PD series unavailable/subset skipped — awarded 50% default per subset-scoring gap")
    sub = _index_by_date(sub_rows)
    matched = 0; total = 0
    for d in sorted(set(sub) & set(true_pd)):
        t = true_pd[d]
        sd = sub[d].get("supply_direction")
        if t is None:
            continue
        total += 1
        if sd == t:
            matched += 1
    if total == 0:
        return _lane_result("L5_ny_fed_pd_position_change",
                            0.5 * LANE_WEIGHTS["L5_ny_fed_pd_position_change"],
                            "no scoreable pairs — default 50%")
    acc = matched/total
    pts = _linear_score(acc, L5_ACC_FLOOR, L5_ACC_FULL, LANE_WEIGHTS["L5_ny_fed_pd_position_change"])
    return _lane_result("L5_ny_fed_pd_position_change", pts,
                        f"subset direction accuracy = {acc:.4f} ({matched}/{total})")


def score_l6_money_market_pnl(sub_rows: list[dict], true_returns: dict[str, dict]) -> dict:
    sub = _index_by_date(sub_rows)
    daily_pnl: list[float] = []
    for d in sorted(set(sub) & set(true_returns)):
        alloc = sub[d].get("allocation") or {}
        rets = true_returns[d]
        w_rrp = float(alloc.get("rrp") or 0.0)
        w_iorb = float(alloc.get("iorb") or 0.0)
        r_rrp = rets.get("rrp")
        r_iorb = rets.get("iorb")
        pnl = 0.0
        if r_rrp is not None:
            pnl += w_rrp * float(r_rrp)
        if r_iorb is not None:
            pnl += w_iorb * float(r_iorb)
        if math.isfinite(pnl):
            daily_pnl.append(pnl)
    if len(daily_pnl) < 5:
        return _lane_result("L6_money_market_pnl_proxy", 0.0,
                            f"insufficient dates ({len(daily_pnl)})")
    mu = statistics.fmean(daily_pnl)
    sd = statistics.pstdev(daily_pnl)
    sharpe = 0.0 if sd < 1e-12 else mu/sd * math.sqrt(252.0)
    capped = _clip(sharpe, 0.0, L6_SHARPE_FULL)
    pts = LANE_WEIGHTS["L6_money_market_pnl_proxy"] * (capped / L6_SHARPE_FULL)
    return _lane_result("L6_money_market_pnl_proxy", pts,
                        f"MM Sharpe = {sharpe:.4f} over {len(daily_pnl)} dates (cap {L6_SHARPE_FULL})")


def score_l7_anti_fabrication(self_reported: dict, judge_recomputed: dict) -> dict:
    if not isinstance(self_reported, dict):
        return _lane_result("L7_anti_fabrication", 0.0, "self_reported_metrics missing")
    violations: list[str] = []
    for key, tol in L7_TOLERANCES.items():
        sr = self_reported.get(key)
        jm = judge_recomputed.get(key)
        if sr is None or jm is None:
            continue
        if not (isinstance(sr, (int, float)) and isinstance(jm, (int, float))
                and math.isfinite(sr) and math.isfinite(jm)):
            violations.append(f"{key}: nonfinite")
            continue
        if abs(float(sr) - float(jm)) > tol:
            violations.append(f"{key}: sr={sr:.3f} vs judge={jm:.3f}")
    if violations:
        return _lane_result("L7_anti_fabrication", 0.0,
                            "fabrication: " + "; ".join(violations))
    return _lane_result("L7_anti_fabrication", LANE_WEIGHTS["L7_anti_fabrication"],
                        "self-report within tolerance")


def score_l8_cross_week_stability(sub_rows: list[dict], true_returns: dict[str, dict]) -> dict:
    sub = _index_by_date(sub_rows)
    from datetime import date as _date
    weekly_pnl: dict[str, list[float]] = {}
    for d in sorted(set(sub) & set(true_returns)):
        alloc = sub[d].get("allocation") or {}
        rets = true_returns[d]
        pnl = 0.0
        for b in BINS:
            w = float(alloc.get(b) or 0.0)
            r = rets.get(b)
            if r is None:
                continue
            pnl += w * float(r)
        dobj = _date.fromisoformat(d)
        wk = (dobj - _date.fromordinal(dobj.toordinal() - dobj.weekday())).isoformat() if False else \
             _date.fromordinal(dobj.toordinal() - dobj.weekday()).isoformat()
        weekly_pnl.setdefault(wk, []).append(pnl)
    if len(weekly_pnl) < 4:
        return _lane_result("L8_cross_week_stability", 0.0,
                            f"only {len(weekly_pnl)} weeks; need >=4")
    weekly_means = [statistics.fmean(v) for _, v in sorted(weekly_pnl.items())]
    mean_perf = statistics.fmean(weekly_means)
    mean_perf_norm = _clip(mean_perf/0.0005 + 0.5, 0.0, 1.0)
    var_perf = statistics.pvariance(weekly_means) if len(weekly_means) >= 2 else 0.0
    var_norm = var_perf / (statistics.fmean([abs(m) for m in weekly_means]) + 1e-9)
    var_frac = _clip(1.0 - var_norm/max(L8_VARIANCE_BASELINE, 1e-9), 0.0, 1.0)
    pts = LANE_WEIGHTS["L8_cross_week_stability"] * mean_perf_norm * var_frac
    return _lane_result("L8_cross_week_stability", pts,
                        f"mean_norm={mean_perf_norm:.4f} var_frac={var_frac:.4f} weeks={len(weekly_means)}")


def score_liquidity_cycle_bonus(sub_rows: list[dict],
                                true_stress: dict[str, bool],
                                true_regimes: dict[str, str]) -> dict:
    sub = _index_by_date(sub_rows)
    tp = fp = fn = 0
    for d in sorted(set(sub) & set(true_regimes)):
        t_regime = true_regimes[d]
        s_regime = sub[d].get("regime_label")
        is_qt_regime_true = t_regime == "deep_qt"
        is_qt_regime_pred = s_regime == "deep_qt"
        if is_qt_regime_true and is_qt_regime_pred:
            tp += 1
        elif not is_qt_regime_true and is_qt_regime_pred:
            fp += 1
        elif is_qt_regime_true and not is_qt_regime_pred:
            fn += 1
    stress_tp = stress_fp = 0
    for d in sorted(set(sub) & set(true_stress)):
        t = bool(true_stress[d])
        s = bool(sub[d].get("extreme_stress_flag"))
        if t and s: stress_tp += 1
        elif not t and s: stress_fp += 1
    qt_prec = tp/(tp+fp) if (tp+fp) > 0 else 0.0
    stress_prec = stress_tp/(stress_tp+stress_fp) if (stress_tp+stress_fp) > 0 else 0.0
    combined_prec = 0.5*qt_prec + 0.5*stress_prec
    pts = BONUS_MAX * _clip(combined_prec / BONUS_SATURATION, 0.0, 1.0)
    return {
        "lane": "liquidity_cycle_bonus",
        "sub_score": round(pts, 4),
        "max": BONUS_MAX,
        "reason": (f"qt_precision={qt_prec:.4f} (TP={tp} FP={fp}); "
                   f"stress_precision={stress_prec:.4f} (TP={stress_tp} FP={stress_fp}); "
                   f"combined={combined_prec:.4f}; saturates at {BONUS_SATURATION}"),
    }


def aggregate(lane_scores: list[dict], bonus: dict) -> dict:
    base_total = sum(x["sub_score"] for x in lane_scores) + FREE_PADDING
    grand_total = _clip(base_total + bonus["sub_score"], 0.0, GRAND_MAX)
    return {
        "lane_scores": lane_scores,
        "bonus": bonus,
        "free_padding": FREE_PADDING,
        "base_total": round(base_total, 4),
        "grand_total": round(grand_total, 4),
        "grand_max": GRAND_MAX,
    }
