#!/usr/bin/env python3
"""
score.py - per-print 8-lane scoring for cpi_nowcast_positioning_book.

Lane anchors are capped at macroeconomic-frontier values per PKW-FAMILIES
section 3 Framework B (headline CPI MAE floor 0.10pp = 10bps annualized;
core CPI/PCE/core-PCE MAE floors chosen to bracket realistic 30-50bps
monthly nowcast standard error). Anchors are set by reality and never moved
to hit a desired score band per MEPHISTO section 1.2.

Lanes (total 100, plus +10 aggregated Fed-pivot detection bonus):
  L1 headline_cpi_nowcast_accuracy   20 pts   MAE pp on CPIAUCSL YoY (12 prints)
  L2 core_cpi_nowcast_accuracy       15 pts   MAE pp on CPILFESL YoY (12 prints)
  L3 pce_nowcast_accuracy            15 pts   MAE pp on PCEPI YoY (12 prints)
  L4 core_pce_nowcast_accuracy       10 pts   MAE pp on PCEPILFE YoY (12 prints)
  L5 positioning_book_pnl            15 pts   Sum PnL across 12 prints (Sharpe cap 1.5)
  L6 directional_accuracy_vs_carry   10 pts   Beat-rate vs naive year-ago-carry
  L7 anti_fabrication                 5 pts   Self-report vs judge-recompute agreement
  L8 cross_series_stability          10 pts   Variance-and-mean across L1-L4 lane scores

Fed-pivot bonus (+10 pts, aggregated): detected Fed pivots matching
true_fed_pivot_events.json within 1-month tolerance, saturating at 3 hits.
"""
from __future__ import annotations

from typing import Any

import numpy as np


HEADLINE_MAE_FULL_PP = 0.10
HEADLINE_MAE_ZERO_PP = 0.80

CORE_MAE_FULL_PP = 0.10
CORE_MAE_ZERO_PP = 0.60

PCE_MAE_FULL_PP = 0.10
PCE_MAE_ZERO_PP = 0.60

CORE_PCE_MAE_FULL_PP = 0.10
CORE_PCE_MAE_ZERO_PP = 0.50

POSITIONING_PNL_FULL = 0.15
POSITIONING_PNL_ZERO = -0.10

BEAT_RATE_FULL = 0.65
BEAT_RATE_ZERO = 0.35

ANTI_FAB_MAE_TOL_PP = 0.05
ANTI_FAB_PNL_TOL_ABS = 0.020
ANTI_FAB_BEAT_TOL = 0.05

LANE_WEIGHTS = {
    "L1_headline_cpi_nowcast_accuracy": 20,
    "L2_core_cpi_nowcast_accuracy": 15,
    "L3_pce_nowcast_accuracy": 15,
    "L4_core_pce_nowcast_accuracy": 10,
    "L5_positioning_book_pnl": 15,
    "L6_directional_accuracy_vs_carry": 10,
    "L7_anti_fabrication": 5,
    "L8_cross_series_stability": 10,
}
LANE_TOTAL = sum(LANE_WEIGHTS.values())

SERIES_LANE_MAP = {
    "CPIAUCSL": "L1_headline_cpi_nowcast_accuracy",
    "CPILFESL": "L2_core_cpi_nowcast_accuracy",
    "PCEPI": "L3_pce_nowcast_accuracy",
    "PCEPILFE": "L4_core_pce_nowcast_accuracy",
}

SERIES_MAE_ANCHORS = {
    "CPIAUCSL": (HEADLINE_MAE_FULL_PP, HEADLINE_MAE_ZERO_PP, LANE_WEIGHTS["L1_headline_cpi_nowcast_accuracy"]),
    "CPILFESL": (CORE_MAE_FULL_PP, CORE_MAE_ZERO_PP, LANE_WEIGHTS["L2_core_cpi_nowcast_accuracy"]),
    "PCEPI": (PCE_MAE_FULL_PP, PCE_MAE_ZERO_PP, LANE_WEIGHTS["L3_pce_nowcast_accuracy"]),
    "PCEPILFE": (CORE_PCE_MAE_FULL_PP, CORE_PCE_MAE_ZERO_PP, LANE_WEIGHTS["L4_core_pce_nowcast_accuracy"]),
}


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


def score_series_mae(series: str, agent_errs: list[float]) -> float:
    if series not in SERIES_MAE_ANCHORS or not agent_errs:
        return 0.0
    full, zero, pts = SERIES_MAE_ANCHORS[series]
    mae = float(np.mean(agent_errs))
    return _linear_score(mae, zero, full, pts)


def score_positioning_pnl(pnl_sum: float, pnl_per_print: list[float] | None = None) -> float:
    pts = LANE_WEIGHTS["L5_positioning_book_pnl"]
    base = _linear_score(pnl_sum, POSITIONING_PNL_ZERO, POSITIONING_PNL_FULL, pts)
    if pnl_per_print and len(pnl_per_print) >= 3:
        mu = float(np.mean(pnl_per_print))
        sd = float(np.std(pnl_per_print)) + 1e-9
        sharpe = mu / sd * np.sqrt(12.0)
        sharpe_cap = 1.5
        sharpe_capped = min(max(sharpe, -sharpe_cap), sharpe_cap)
        sharpe_frac = (sharpe_capped + sharpe_cap) / (2.0 * sharpe_cap)
        blend = 0.6 * base + 0.4 * (pts * sharpe_frac)
        return float(min(max(blend, 0.0), pts))
    return base


def score_directional_beat(beat_rate: float) -> float:
    return _linear_score(beat_rate, BEAT_RATE_ZERO, BEAT_RATE_FULL,
                         LANE_WEIGHTS["L6_directional_accuracy_vs_carry"])


def score_anti_fabrication(self_reported: dict[str, float],
                           judge_recomputed: dict[str, float]) -> tuple[float, bool, list[str]]:
    violations: list[str] = []
    if not self_reported or not judge_recomputed:
        return 0.0, True, ["missing self_reported_metrics or judge_recomputed"]
    checks = [
        ("headline_cpi_mae_pp", ANTI_FAB_MAE_TOL_PP),
        ("core_cpi_mae_pp", ANTI_FAB_MAE_TOL_PP),
        ("pce_mae_pp", ANTI_FAB_MAE_TOL_PP),
        ("core_pce_mae_pp", ANTI_FAB_MAE_TOL_PP),
        ("positioning_pnl_sum", ANTI_FAB_PNL_TOL_ABS),
        ("directional_beat_consensus_rate", ANTI_FAB_BEAT_TOL),
    ]
    for key, tol in checks:
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


def score_cross_series_stability(lane_scores: dict[str, float]) -> float:
    keys = ["L1_headline_cpi_nowcast_accuracy", "L2_core_cpi_nowcast_accuracy",
            "L3_pce_nowcast_accuracy", "L4_core_pce_nowcast_accuracy"]
    vals = [lane_scores.get(k, 0.0) for k in keys]
    lane_maxes = [LANE_WEIGHTS[k] for k in keys]
    norm = [v / m if m > 0 else 0.0 for v, m in zip(vals, lane_maxes)]
    mean_frac = float(np.mean(norm))
    var = float(np.var(norm))
    var_baseline = 0.20
    var_frac = max(0.0, min(1.0, 1.0 - var / max(var_baseline, 1e-9)))
    return LANE_WEIGHTS["L8_cross_series_stability"] * mean_frac * var_frac


def fed_pivot_bonus(detected_events: list[dict], true_events: list[dict],
                    tolerance_months: int = 1) -> tuple[float, int, int]:
    if not true_events or not detected_events:
        return 0.0, 0, len(true_events) if true_events else 0
    from datetime import datetime as _dt

    def _month(ds: str) -> int:
        try:
            d = _dt.strptime(str(ds), "%Y-%m-%d")
        except Exception:
            try:
                d = _dt.strptime(str(ds), "%Y-%m")
            except Exception:
                return -9999
        return d.year * 12 + d.month

    true_months = [_month(e.get("event_date", e.get("event_month", ""))) for e in true_events]
    det_months = [_month(e.get("event_date", e.get("event_month", ""))) for e in detected_events]
    hits = 0
    matched = set()
    for tm in true_months:
        if tm in matched:
            continue
        for dm in det_months:
            if abs(dm - tm) <= tolerance_months:
                hits += 1
                matched.add(tm)
                break
    saturation = 3
    bonus_frac = min(1.0, hits / saturation)
    return 10.0 * bonus_frac, hits, len(true_events)
