#!/usr/bin/env python3
"""
score.py — per-window 8-lane scoring for treasury_curve_positioning_book.

Lane anchors are capped at institutional-frontier values per PKW-FAMILIES
section 3 Framework B (Sharpe full=2.0 for curve trading, thinner than equity;
Sortino full=3.0; IR full=1.5). Anchors are set by reality and never moved
to hit a desired score band.

Lanes (total 100, plus +10 aggregated regime-shift bonus):
  L1 risk_adjusted_return       25 pts   Sharpe over window returns
  L2 directional_accuracy       20 pts   Hit rate on flatten/steepen calls
  L3 duration_precision         15 pts   RMSE of realized vs target duration
  L4 convexity_capture          15 pts   Butterfly PnL vs equal-DV01 benchmark
  L5 drawdown_control           10 pts   Max within-window drawdown
  L6 turnover_discipline         5 pts   Annualized one-way turnover in-band
  L7 anti_fabrication            5 pts   Judge recompute vs self-report match
  L8 cross_window_stability      5 pts   Aggregated at grader level (returned 0 here)
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


SHARPE_FLOOR = 0.0
SHARPE_FULL = 2.0
SHARPE_MIN_ZERO = -0.5

HIT_RATE_FLOOR = 0.45
HIT_RATE_FULL = 0.65

DURATION_PRECISION_FULL_RMSE = 0.05
DURATION_PRECISION_ZERO_RMSE = 0.30

CONVEXITY_PNL_FULL_SIGN = 1.0
CONVEXITY_PNL_FLOOR_SIGN = -1.0

DRAWDOWN_FULL = 0.03
DRAWDOWN_ZERO = 0.10

TURNOVER_LOW_BAND = 0.60
TURNOVER_HIGH_BAND = 1.00
TURNOVER_SOFT_LOW = 0.40
TURNOVER_SOFT_HIGH = 1.40

ANTI_FAB_SHARPE_TOL = 0.20
ANTI_FAB_DD_TOL = 0.02
ANTI_FAB_TURNOVER_TOL = 0.50

LANE_WEIGHTS = {
    "L1_risk_adjusted_return": 25,
    "L2_directional_accuracy": 20,
    "L3_duration_precision": 15,
    "L4_convexity_capture": 15,
    "L5_drawdown_control": 10,
    "L6_turnover_discipline": 5,
    "L7_anti_fabrication": 5,
    "L8_cross_window_stability": 5,
}
LANE_TOTAL = sum(LANE_WEIGHTS.values())


def _linear_score(x: float, floor: float, full: float, pts: float) -> float:
    if not np.isfinite(x):
        return 0.0
    if full > floor:
        if x <= floor:
            return 0.0
        if x >= full:
            return pts
        return pts * (x - floor) / (full - floor)
    else:
        if x >= floor:
            return 0.0
        if x <= full:
            return pts
        return pts * (floor - x) / (floor - full)


def score_L1_sharpe(sharpe: float) -> float:
    if not np.isfinite(sharpe):
        return 0.0
    if sharpe <= SHARPE_MIN_ZERO:
        return 0.0
    if sharpe >= SHARPE_FULL:
        return LANE_WEIGHTS["L1_risk_adjusted_return"]
    if sharpe <= SHARPE_FLOOR:
        return LANE_WEIGHTS["L1_risk_adjusted_return"] * 0.35 * (sharpe - SHARPE_MIN_ZERO) / (SHARPE_FLOOR - SHARPE_MIN_ZERO)
    frac = (sharpe - SHARPE_FLOOR) / (SHARPE_FULL - SHARPE_FLOOR)
    return LANE_WEIGHTS["L1_risk_adjusted_return"] * (0.35 + 0.65 * frac)


def score_L2_hit_rate(hit_rate: float) -> float:
    return _linear_score(hit_rate, HIT_RATE_FLOOR, HIT_RATE_FULL, LANE_WEIGHTS["L2_directional_accuracy"])


def score_L3_duration_precision(rmse: float) -> float:
    return _linear_score(rmse, DURATION_PRECISION_ZERO_RMSE, DURATION_PRECISION_FULL_RMSE,
                         LANE_WEIGHTS["L3_duration_precision"])


def score_L4_convexity_capture(pnl_sign: float) -> float:
    if not np.isfinite(pnl_sign):
        return LANE_WEIGHTS["L4_convexity_capture"] * 0.4
    if pnl_sign >= CONVEXITY_PNL_FULL_SIGN:
        return LANE_WEIGHTS["L4_convexity_capture"]
    if pnl_sign <= CONVEXITY_PNL_FLOOR_SIGN:
        return 0.0
    frac = (pnl_sign - CONVEXITY_PNL_FLOOR_SIGN) / (CONVEXITY_PNL_FULL_SIGN - CONVEXITY_PNL_FLOOR_SIGN)
    return LANE_WEIGHTS["L4_convexity_capture"] * frac


def score_L5_drawdown(max_dd: float) -> float:
    dd = abs(max_dd) if np.isfinite(max_dd) else 1.0
    return _linear_score(dd, DRAWDOWN_ZERO, DRAWDOWN_FULL, LANE_WEIGHTS["L5_drawdown_control"])


def score_L6_turnover(turnover: float) -> float:
    if not np.isfinite(turnover):
        return 0.0
    if TURNOVER_LOW_BAND <= turnover <= TURNOVER_HIGH_BAND:
        return LANE_WEIGHTS["L6_turnover_discipline"]
    if TURNOVER_SOFT_LOW <= turnover < TURNOVER_LOW_BAND:
        return LANE_WEIGHTS["L6_turnover_discipline"] * 0.5
    if TURNOVER_HIGH_BAND < turnover <= TURNOVER_SOFT_HIGH:
        return LANE_WEIGHTS["L6_turnover_discipline"] * 0.5
    return 0.0


def score_L7_anti_fabrication(self_reported: dict[str, float],
                               recomputed: dict[str, float]) -> tuple[float, bool, list[str]]:
    violations: list[str] = []
    if not self_reported or not recomputed:
        return 0.0, True, ["missing metrics"]

    sr_sharpe = self_reported.get("sharpe", 0.0)
    re_sharpe = recomputed.get("sharpe", 0.0)
    if np.isfinite(sr_sharpe) and np.isfinite(re_sharpe):
        if abs(sr_sharpe - re_sharpe) > ANTI_FAB_SHARPE_TOL:
            violations.append(f"sharpe mismatch {sr_sharpe:.3f} vs {re_sharpe:.3f}")

    sr_dd = abs(self_reported.get("max_drawdown", 0.0))
    re_dd = abs(recomputed.get("max_drawdown", 0.0))
    if np.isfinite(sr_dd) and np.isfinite(re_dd):
        if abs(sr_dd - re_dd) > ANTI_FAB_DD_TOL:
            violations.append(f"drawdown mismatch {sr_dd:.3f} vs {re_dd:.3f}")

    sr_to = self_reported.get("turnover_annualized", 0.0)
    re_to = recomputed.get("turnover_annualized", 0.0)
    if np.isfinite(sr_to) and np.isfinite(re_to):
        if abs(sr_to - re_to) > ANTI_FAB_TURNOVER_TOL:
            violations.append(f"turnover mismatch {sr_to:.3f} vs {re_to:.3f}")

    if not violations:
        return LANE_WEIGHTS["L7_anti_fabrication"], False, []
    else:
        return 0.0, True, violations


def score_window(window_result: dict[str, Any], recomputed: dict[str, float]) -> dict[str, Any]:
    sr = window_result.get("self_reported_metrics", {})
    l7_pts, l7_veto, l7_notes = score_L7_anti_fabrication(sr, recomputed)

    sharpe_used = float(recomputed.get("sharpe", sr.get("sharpe", 0.0)) or 0.0)
    dd_used = float(recomputed.get("max_drawdown", sr.get("max_drawdown", 0.0)) or 0.0)
    turnover_used = float(recomputed.get("turnover_annualized", sr.get("turnover_annualized", 0.0)) or 0.0)
    hit_rate_used = float(recomputed.get("hit_rate_flatten_steepen", sr.get("hit_rate_flatten_steepen", 0.5)) or 0.5)
    duration_rmse_used = float(recomputed.get("duration_precision_rmse", sr.get("duration_precision_rmse", 0.15)) or 0.15)
    _conv_pnl = float(recomputed.get("convexity_capture_pnl", sr.get("convexity_capture_pnl", 0.0)) or 0.0)
    convex_pnl_used = float(recomputed.get("convexity_capture_pnl_sign", np.sign(_conv_pnl)))

    l1 = score_L1_sharpe(sharpe_used)
    l2 = score_L2_hit_rate(hit_rate_used)
    l3 = score_L3_duration_precision(duration_rmse_used)
    l4 = score_L4_convexity_capture(convex_pnl_used)
    l5 = score_L5_drawdown(dd_used)
    l6 = score_L6_turnover(turnover_used)
    l7 = l7_pts

    if l7_veto:
        l1 = 0.0

    return {
        "window_start": window_result.get("window_start"),
        "window_end": window_result.get("window_end"),
        "lanes": {
            "L1_risk_adjusted_return": round(l1, 3),
            "L2_directional_accuracy": round(l2, 3),
            "L3_duration_precision": round(l3, 3),
            "L4_convexity_capture": round(l4, 3),
            "L5_drawdown_control": round(l5, 3),
            "L6_turnover_discipline": round(l6, 3),
            "L7_anti_fabrication": round(l7, 3),
        },
        "l7_veto": l7_veto,
        "l7_notes": l7_notes,
        "sub_total": round(l1 + l2 + l3 + l4 + l5 + l6 + l7, 3),
        "used_metrics": {
            "sharpe": sharpe_used,
            "max_drawdown": dd_used,
            "hit_rate_flatten_steepen": hit_rate_used,
            "duration_precision_rmse": duration_rmse_used,
            "convexity_capture_pnl_sign": convex_pnl_used,
            "turnover_annualized": turnover_used,
        },
    }


def cross_window_stability_score(per_window_scores: list[float]) -> float:
    if len(per_window_scores) < 2:
        return 0.0
    arr = np.array(per_window_scores, dtype=float)
    mean = float(np.mean(arr))
    var = float(np.var(arr))
    if mean < 3.0:
        return 0.0
    var_baseline = 200.0
    var_frac = max(0.0, min(1.0, 1.0 - var / max(var_baseline, 1e-9)))
    mean_frac = min(1.0, mean / 8.0)
    return LANE_WEIGHTS["L8_cross_window_stability"] * mean_frac * var_frac


def regime_shift_bonus(detected_events_dates: list[str], true_events: list[dict[str, Any]],
                       tolerance_days: int = 3) -> tuple[float, int, int]:
    from datetime import datetime
    hits = 0
    if not true_events or not detected_events_dates:
        return 0.0, 0, len(true_events) if true_events else 0
    true_dates = [datetime.strptime(e["event_date"], "%Y-%m-%d") for e in true_events]
    det_dates = [datetime.strptime(d, "%Y-%m-%d") for d in detected_events_dates]
    for td in true_dates:
        for dd in det_dates:
            if abs((dd - td).days) <= tolerance_days:
                hits += 1
                break
    total = len(true_dates)
    if total == 0:
        return 0.0, 0, 0
    saturation_threshold = 3
    bonus_frac = min(1.0, hits / saturation_threshold)
    return 10.0 * bonus_frac, hits, total
