#!/usr/bin/env python3
"""
score.py - per-lane scoring for fed_funds_regime_positioning_book.

Lane anchors set by rates-frontier realistic values per PKW-FAMILIES section 3
Framework B. Anchors are set by reality and never moved to hit a desired score
band per MEPHISTO section 1.2.

Lanes (total 100, plus +10 aggregated FOMC-decision bonus):
  L1 regime_classification            20 pts   weekly regime accuracy (5 states)
  L2 yield_2y_forecast                15 pts   MAE bps on 2Y next-week forecast
  L3 yield_10y_forecast               15 pts   MAE bps on 10Y next-week forecast
  L4 duration_positioning_pnl         15 pts   Sharpe of 2Y/10Y weighted PnL (cap 2.0)
  L5 slope_positioning_pnl            10 pts   Sharpe of 2s10s PnL (cap 2.0)
  L6 carry_position_pnl               10 pts   sum PnL from carry_front_end positions
  L7 anti_fabrication                  5 pts   self-report vs judge-recompute agreement
  L8 cross_cadence_stability          10 pts   variance-of-lanes across 6mo buckets

FOMC bonus (+10, aggregated): saturates at 3+ correct decisions.
"""
from __future__ import annotations

from typing import Any
import numpy as np


REGIME_ACC_FULL = 1.00
REGIME_ACC_ZERO = 0.60

YIELD_2Y_MAE_FULL_BPS = 5.0
YIELD_2Y_MAE_ZERO_BPS = 50.0

YIELD_10Y_MAE_FULL_BPS = 8.0
YIELD_10Y_MAE_ZERO_BPS = 80.0

DURATION_SHARPE_CAP = 2.0
SLOPE_SHARPE_CAP = 2.0

CARRY_PNL_FULL = 2.0
CARRY_PNL_ZERO = -2.0

ANTI_FAB_TOLERANCES = {
    "regime_accuracy": 0.15,
    "yield_2y_mae_bps": 8.0,
    "yield_10y_mae_bps": 8.0,
    "duration_pnl_sum": 5.0,
    "slope_pnl_sum": 3.0,
    "carry_pnl_sum": 3.0,
}

LANE_WEIGHTS = {
    "L1_regime_classification": 20,
    "L2_yield_2y_forecast": 15,
    "L3_yield_10y_forecast": 15,
    "L4_duration_positioning_pnl": 15,
    "L5_slope_positioning_pnl": 10,
    "L6_carry_position_pnl": 10,
    "L7_anti_fabrication": 5,
    "L8_cross_cadence_stability": 10,
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
    if x >= floor:
        return 0.0
    if x <= full:
        return pts
    return pts * (floor - x) / (floor - full)


def score_regime_accuracy(accuracy: float) -> float:
    return _linear_score(accuracy, REGIME_ACC_ZERO, REGIME_ACC_FULL,
                         LANE_WEIGHTS["L1_regime_classification"])


def score_yield_2y_mae(mae_bps: float) -> float:
    return _linear_score(mae_bps, YIELD_2Y_MAE_ZERO_BPS, YIELD_2Y_MAE_FULL_BPS,
                         LANE_WEIGHTS["L2_yield_2y_forecast"])


def score_yield_10y_mae(mae_bps: float) -> float:
    return _linear_score(mae_bps, YIELD_10Y_MAE_ZERO_BPS, YIELD_10Y_MAE_FULL_BPS,
                         LANE_WEIGHTS["L3_yield_10y_forecast"])


def _sharpe(pnl_series: list[float], periods_per_year: float = 52.0) -> float:
    if not pnl_series or len(pnl_series) < 3:
        return 0.0
    a = np.array(pnl_series, dtype=float)
    mu = float(np.mean(a))
    sd = float(np.std(a)) + 1e-12
    return mu / sd * float(np.sqrt(periods_per_year))


def score_duration_sharpe(pnl_series: list[float]) -> float:
    pts = LANE_WEIGHTS["L4_duration_positioning_pnl"]
    sh = _sharpe(pnl_series)
    capped = min(max(sh, 0.0), DURATION_SHARPE_CAP)
    frac = capped / DURATION_SHARPE_CAP
    return pts * frac


def score_slope_sharpe(pnl_series: list[float]) -> float:
    pts = LANE_WEIGHTS["L5_slope_positioning_pnl"]
    sh = _sharpe(pnl_series)
    capped = min(max(sh, 0.0), SLOPE_SHARPE_CAP)
    frac = capped / SLOPE_SHARPE_CAP
    return pts * frac


def score_carry_pnl(pnl_sum: float) -> float:
    return _linear_score(pnl_sum, CARRY_PNL_ZERO, CARRY_PNL_FULL,
                         LANE_WEIGHTS["L6_carry_position_pnl"])


def score_anti_fabrication(self_reported: dict, judge_recomputed: dict) -> tuple[float, bool, list[str]]:
    violations: list[str] = []
    if not self_reported or not judge_recomputed:
        return 0.0, True, ["missing self_reported_metrics or judge_recomputed"]
    for key, tol in ANTI_FAB_TOLERANCES.items():
        sr = self_reported.get(key)
        jm = judge_recomputed.get(key)
        if sr is None or jm is None:
            continue
        if not (np.isfinite(sr) and np.isfinite(jm)):
            violations.append(f"{key}: nonfinite sr={sr} jm={jm}")
            continue
        if abs(float(sr) - float(jm)) > tol:
            violations.append(f"{key}: sr={sr:.4f} vs judge={jm:.4f} (tol {tol})")
    if not violations:
        return LANE_WEIGHTS["L7_anti_fabrication"], False, []
    return 0.0, True, violations


def score_cross_cadence_stability(bucket_lane_scores: list[dict[str, float]]) -> float:
    if not bucket_lane_scores or len(bucket_lane_scores) < 2:
        return LANE_WEIGHTS["L8_cross_cadence_stability"] * 0.5
    keys = ["L1_regime_classification", "L2_yield_2y_forecast", "L3_yield_10y_forecast",
            "L4_duration_positioning_pnl", "L5_slope_positioning_pnl", "L6_carry_position_pnl"]
    norm_by_bucket = []
    for b in bucket_lane_scores:
        norms = [b.get(k, 0.0) / LANE_WEIGHTS[k] for k in keys if k in LANE_WEIGHTS]
        norm_by_bucket.append(np.mean(norms) if norms else 0.0)
    mean_perf = float(np.mean(norm_by_bucket))
    var_perf = float(np.var(norm_by_bucket))
    var_baseline = 0.10
    var_frac = max(0.0, min(1.0, 1.0 - var_perf / max(var_baseline, 1e-9)))
    return LANE_WEIGHTS["L8_cross_cadence_stability"] * mean_perf * var_frac


def fomc_decision_bonus(detected: list[dict], truth: list[dict],
                         saturation_hits: int = 3) -> tuple[float, int, int]:
    if not truth or not detected:
        return 0.0, 0, len(truth) if truth else 0
    truth_by_date = {t.get("meeting_date"): t.get("true_rate_decision")
                     for t in truth}
    non_hold_hits = 0
    hold_hits = 0
    total_hits = 0
    for d in detected:
        md = d.get("meeting_date")
        pred = d.get("predicted_decision")
        real = truth_by_date.get(md)
        if pred is not None and real is not None and pred == real:
            total_hits += 1
            if real == "hold":
                hold_hits += 1
            else:
                non_hold_hits += 1
    weighted = non_hold_hits + 0.15 * hold_hits
    bonus_frac = min(1.0, weighted / saturation_hits)
    return 10.0 * bonus_frac, total_hits, len(truth)
