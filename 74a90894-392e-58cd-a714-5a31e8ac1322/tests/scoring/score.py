#!/usr/bin/env python3
from __future__ import annotations

import math
import statistics
from typing import Any

LANE_WEIGHTS: dict[str, float] = {
    "L1_timing_rmse_lane": 20.0,
    "L2_circuit_regime_classification": 15.0,
    "L3_stall_detection": 15.0,
    "L4_case_type_ordering": 10.0,
    "L5_motion_count_regression": 10.0,
    "L6_disposition_timing_pnl": 10.0,
    "L7_anti_fabrication": 5.0,
    "L8_cross_month_stability": 10.0,
}
LANE_BASE_TOTAL = sum(LANE_WEIGHTS.values())
FREE_PADDING = 5.0
BONUS_MAX = 10.0
GRAND_MAX = 110.0

L1_RMSE_RATIO_FULL = 0.30
L1_RMSE_RATIO_ZERO = 1.00

L2_ACC_FLOOR = 0.25
L2_ACC_FULL = 0.85

L3_F1_FLOOR = 0.10
L3_F1_FULL = 1.00

L4_RHO_FLOOR = 0.00
L4_RHO_FULL = 0.50

L5_R2_FLOOR = 0.00
L5_R2_FULL = 0.50

L6_SHARPE_FLOOR = 0.0
L6_SHARPE_FULL = 1.5

L7_TOLERANCES: dict[str, float] = {
    "L1_timing_rmse_lane_est": 0.20,
    "L2_circuit_regime_classification_est": 0.20,
    "L3_stall_detection_est": 0.20,
    "L4_case_type_ordering_est": 0.20,
    "L5_motion_count_regression_est": 0.20,
    "L6_disposition_timing_pnl_est": 0.20,
    "L8_cross_month_stability_est": 0.20,
}

L8_VARIANCE_BASELINE = 0.08
BONUS_SATURATION = 0.75


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


def _index_predictions(rows: list[dict]) -> dict[str, dict]:
    return {r["case_id"]: r for r in rows if r.get("case_id")}


def score_l1_timing_rmse(sub_rows: list[dict], true_days: dict[str, int]) -> dict:
    sub = _index_predictions(sub_rows)
    errs: list[float] = []
    trues: list[float] = []
    for cid in sorted(set(sub) & set(true_days)):
        t = true_days[cid]
        s = sub[cid].get("predicted_days_to_disposition")
        if t is None or s is None:
            continue
        try:
            errs.append((float(s) - float(t)) ** 2)
            trues.append(float(t))
        except (ValueError, TypeError):
            continue
    if len(errs) < 10:
        return _lane_result("L1_timing_rmse_lane", 0.0,
                            f"insufficient paired cases ({len(errs)})")
    rmse = math.sqrt(statistics.fmean(errs))
    median_days = statistics.median(trues) if trues else 400.0
    ratio = rmse / max(median_days, 1.0)
    if ratio >= L1_RMSE_RATIO_ZERO:
        pts = 0.0
    elif ratio <= L1_RMSE_RATIO_FULL:
        pts = LANE_WEIGHTS["L1_timing_rmse_lane"]
    else:
        pts = LANE_WEIGHTS["L1_timing_rmse_lane"] * (L1_RMSE_RATIO_ZERO - ratio) / (L1_RMSE_RATIO_ZERO - L1_RMSE_RATIO_FULL)
    return _lane_result("L1_timing_rmse_lane", pts,
                        f"RMSE = {rmse:.2f} days, median_true = {median_days:.1f}, ratio = {ratio:.4f} "
                        f"(anchor {L1_RMSE_RATIO_FULL}->full, {L1_RMSE_RATIO_ZERO}->zero, n={len(errs)})")


def score_l2_circuit_regime(sub_rows: list[dict],
                             sub_circuit_month: dict[str, str],
                             true_circuit_month: dict[str, str]) -> dict:
    if not true_circuit_month:
        return _lane_result("L2_circuit_regime_classification", 0.0, "no truth regime cells")
    per_case_by_key: dict[str, list[str]] = {}
    sub = _index_predictions(sub_rows)
    for cid, p in sub.items():
        c = p.get("court_id") or ""
        date_str = p.get("predicted_disposition_date") or ""
        m = date_str[:7] if date_str else ""
        key = f"{c}|{m}"
        per_case_by_key.setdefault(key, []).append(p.get("regime_label") or "")

    matched = 0
    total = 0
    for key, t in sorted(true_circuit_month.items()):
        if t is None:
            continue
        total += 1
        s = sub_circuit_month.get(key)
        if s is None:
            case_regs = [x for x in per_case_by_key.get(key, []) if x]
            if case_regs:
                s = max(set(case_regs), key=case_regs.count)
        if s == t:
            matched += 1
    if total == 0:
        return _lane_result("L2_circuit_regime_classification", 0.0, "no regime pairs")
    acc = matched / total
    pts = _linear_score(acc, L2_ACC_FLOOR, L2_ACC_FULL, LANE_WEIGHTS["L2_circuit_regime_classification"])
    return _lane_result("L2_circuit_regime_classification", pts,
                        f"accuracy = {acc:.4f} ({matched}/{total})")


def score_l3_stall_detection(sub_rows: list[dict], true_stall: dict[str, bool]) -> dict:
    sub = _index_predictions(sub_rows)
    tp = fp = fn = tn = 0
    for cid in sorted(set(sub) & set(true_stall)):
        t = bool(true_stall[cid])
        s = bool(sub[cid].get("stall_flag"))
        if t and s: tp += 1
        elif not t and s: fp += 1
        elif t and not s: fn += 1
        else: tn += 1
    if tp + fp + fn == 0:
        return _lane_result("L3_stall_detection", 0.0,
                            "no positive stall events in submission or truth")
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    pts = _linear_score(f1, L3_F1_FLOOR, L3_F1_FULL, LANE_WEIGHTS["L3_stall_detection"])
    return _lane_result("L3_stall_detection", pts,
                        f"F1 = {f1:.4f} (P={prec:.3f} R={rec:.3f} TP={tp} FP={fp} FN={fn} TN={tn})")


def _spearman(a: list[float], b: list[float]) -> float:
    if len(a) < 3 or len(a) != len(b):
        return 0.0
    def _rank(xs):
        n = len(xs)
        idx = sorted(range(n), key=lambda i: xs[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and xs[idx[j + 1]] == xs[idx[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[idx[k]] = avg
            i = j + 1
        return r
    ra = _rank(a)
    rb = _rank(b)
    n = len(ra)
    mean_a = statistics.fmean(ra)
    mean_b = statistics.fmean(rb)
    num = sum((ra[i] - mean_a) * (rb[i] - mean_b) for i in range(n))
    da = math.sqrt(sum((x - mean_a) ** 2 for x in ra))
    db = math.sqrt(sum((x - mean_b) ** 2 for x in rb))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def score_l4_case_type_ordering(sub_rows: list[dict], true_days: dict[str, int]) -> dict:
    sub = _index_predictions(sub_rows)
    per_group: dict[str, list[tuple]] = {}
    for cid, p in sub.items():
        if cid not in true_days:
            continue
        key = p.get("case_type_rank_key") or f"{p.get('court_id','')}|{p.get('case_type_bucket','')}"
        per_group.setdefault(key, []).append((cid, float(p.get("predicted_days_to_disposition") or 0.0),
                                              float(true_days[cid])))
    rhos = []
    for key, lst in per_group.items():
        if len(lst) < 3:
            continue
        preds = [x[1] for x in lst]
        trues = [x[2] for x in lst]
        rhos.append(_spearman(preds, trues))
    if not rhos:
        return _lane_result("L4_case_type_ordering", 0.0, "no valid ranking groups (need >=3 per group)")
    mean_rho = statistics.fmean(rhos)
    pts = _linear_score(mean_rho, L4_RHO_FLOOR, L4_RHO_FULL, LANE_WEIGHTS["L4_case_type_ordering"])
    return _lane_result("L4_case_type_ordering", pts,
                        f"mean_rho = {mean_rho:.4f} across {len(rhos)} groups")


def score_l5_motion_count_regression(sub_rows: list[dict], true_motion: dict[str, float]) -> dict:
    sub = _index_predictions(sub_rows)
    preds = []
    trues = []
    for cid in sorted(set(sub) & set(true_motion)):
        t = true_motion.get(cid)
        s = sub[cid].get("predicted_motion_count")
        if t is None or s is None:
            continue
        try:
            preds.append(float(s))
            trues.append(float(t))
        except (ValueError, TypeError):
            continue
    if len(preds) < 10:
        return _lane_result("L5_motion_count_regression", 0.0,
                            f"insufficient pairs ({len(preds)})")
    mean_t = statistics.fmean(trues)
    ss_tot = sum((t - mean_t) ** 2 for t in trues)
    ss_res = sum((t - p) ** 2 for p, t in zip(preds, trues))
    if ss_tot < 1e-9:
        return _lane_result("L5_motion_count_regression", 0.0, "true motion counts have zero variance")
    r2 = 1.0 - ss_res / ss_tot
    r2 = max(0.0, r2)
    pts = _linear_score(r2, L5_R2_FLOOR, L5_R2_FULL, LANE_WEIGHTS["L5_motion_count_regression"])
    return _lane_result("L5_motion_count_regression", pts,
                        f"R2 = {r2:.4f} across {len(preds)} pairs")


def score_l6_disposition_timing_pnl(sub_rows: list[dict], true_days: dict[str, int]) -> dict:
    sub = _index_predictions(sub_rows)
    pnl_per_case: list[float] = []
    for cid in sorted(set(sub) & set(true_days)):
        t = true_days.get(cid)
        s = sub[cid].get("predicted_days_to_disposition")
        cert = sub[cid].get("self_reported_certainty") or 0.5
        if t is None or s is None:
            continue
        try:
            err = abs(float(s) - float(t)) / max(float(t), 1.0)
            weighted_pnl = float(cert) * (1.0 - err)
            pnl_per_case.append(weighted_pnl)
        except (ValueError, TypeError):
            continue
    if len(pnl_per_case) < 10:
        return _lane_result("L6_disposition_timing_pnl", 0.0,
                            f"insufficient pnl obs ({len(pnl_per_case)})")
    mu = statistics.fmean(pnl_per_case)
    sd = statistics.pstdev(pnl_per_case)
    sharpe = 0.0 if sd < 1e-9 else mu / sd
    capped = _clip(sharpe, 0.0, L6_SHARPE_FULL)
    pts = LANE_WEIGHTS["L6_disposition_timing_pnl"] * (capped / L6_SHARPE_FULL)
    return _lane_result("L6_disposition_timing_pnl", pts,
                        f"Sharpe = {sharpe:.4f} (mu={mu:.4f} sd={sd:.4f} n={len(pnl_per_case)})")


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


def score_l8_cross_month_stability(sub_rows: list[dict], true_days: dict[str, int]) -> dict:
    sub = _index_predictions(sub_rows)
    monthly_err: dict[str, list[float]] = {}
    for cid in sorted(set(sub) & set(true_days)):
        p = sub[cid]
        date_str = p.get("predicted_disposition_date") or ""
        m = date_str[:7] if date_str else "unknown"
        try:
            err = abs(float(p.get("predicted_days_to_disposition") or 0.0) - float(true_days[cid]))
            monthly_err.setdefault(m, []).append(err)
        except (ValueError, TypeError):
            continue
    if len(monthly_err) < 4:
        return _lane_result("L8_cross_month_stability", 0.0,
                            f"only {len(monthly_err)} months; need >=4")
    monthly_means = [statistics.fmean(v) for _, v in sorted(monthly_err.items())]
    mean_err = statistics.fmean(monthly_means)
    mean_perf_norm = _clip(1.0 - mean_err / 400.0, 0.0, 1.0)
    if len(monthly_means) >= 2:
        var_perf = statistics.pvariance(monthly_means)
    else:
        var_perf = 0.0
    var_norm = var_perf / (statistics.fmean([abs(m) for m in monthly_means]) + 1e-9)
    var_frac = _clip(1.0 - var_norm / max(L8_VARIANCE_BASELINE * 400.0, 1e-9), 0.0, 1.0)
    pts = LANE_WEIGHTS["L8_cross_month_stability"] * mean_perf_norm * var_frac
    return _lane_result("L8_cross_month_stability", pts,
                        f"mean_norm={mean_perf_norm:.4f} var_frac={var_frac:.4f} months={len(monthly_means)}")


def score_timing_calibration_bonus(sub_rows: list[dict],
                                    true_days: dict[str, int],
                                    q2_2025_case_ids: set) -> dict:
    sub = _index_predictions(sub_rows)
    errs = []
    for cid in sorted(set(sub) & set(true_days) & q2_2025_case_ids):
        s = sub[cid].get("predicted_days_to_disposition")
        t = true_days.get(cid)
        if s is None or t is None:
            continue
        try:
            errs.append(abs(float(s) - float(t)) / max(float(t), 1.0))
        except (ValueError, TypeError):
            continue
    if len(errs) < 3:
        pts = 0.5 * BONUS_MAX
        return {
            "lane": "timing_calibration_bonus",
            "sub_score": round(pts, 4),
            "max": BONUS_MAX,
            "reason": f"insufficient Q2-2025 backlog-transition cases ({len(errs)}); default half bonus",
        }
    mean_err_ratio = statistics.fmean(errs)
    precision = max(0.0, 1.0 - mean_err_ratio)
    pts = BONUS_MAX * _clip(precision / BONUS_SATURATION, 0.0, 1.0)
    return {
        "lane": "timing_calibration_bonus",
        "sub_score": round(pts, 4),
        "max": BONUS_MAX,
        "reason": (f"backlog_precision={precision:.4f} across {len(errs)} Q2-2025 cases; "
                   f"saturates at {BONUS_SATURATION}"),
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
