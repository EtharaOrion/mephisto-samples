#!/usr/bin/env python3
"""
score.py — per-auction 8-lane scoring for treasury_auction_bidding_calibration.

Lane anchors are capped at institutional-frontier values per PKW-FAMILIES
section 3 Framework B (tail RMSE floor 1 bp for bills / 2 bps for notes+bonds;
bidToCover MAPE floor 8%; indirect-share MAE floor 0.05). Anchors are set by
reality and never moved to hit a desired score band.

Lanes (total 100, plus +10 aggregated rate-regime-shift bonus):
  L1 bid_ladder_accuracy         25 pts   1 - EMD(predicted, realized cumulative)
  L2 bidToCover_prediction       15 pts   1 - MAPE of predicted vs realized bidToCover
  L3 tail_control                15 pts   RMSE of predicted vs realized tail_bps
  L4 allocation_share_calibration 10 pts  MAE of predicted vs realized allocation share
  L5 indirect_direct_share       10 pts   MAE of predicted vs realized shares
  L6 reference_yield_dislocation 10 pts   MAE of predicted vs realized dislocation
  L7 anti_fabrication             5 pts   self-report vs judge-recompute agreement
  L8 cross_product_mix_stability 10 pts   aggregated (returned 0 here)

Regime-shift bonus (+10 pts, aggregated): detected regime transitions matching
true_rate_regime_events.json within tolerance_days.
"""
from __future__ import annotations

from typing import Any

import numpy as np


LADDER_EMD_FULL_BPS = 5.0
LADDER_EMD_ZERO_BPS = 50.0

BTC_MAPE_FULL = 0.08
BTC_MAPE_ZERO = 0.40

TAIL_RMSE_FULL_BPS_BILL = 1.0
TAIL_RMSE_FULL_BPS_NOTE_BOND = 2.0
TAIL_RMSE_ZERO_BPS = 10.0

ALLOC_MAE_FULL = 0.03
ALLOC_MAE_ZERO = 0.25

SHARE_MAE_FULL = 0.05
SHARE_MAE_ZERO = 0.30

REF_DIS_MAE_FULL_BPS = 2.0
REF_DIS_MAE_ZERO_BPS = 20.0

ANTI_FAB_BTC_MAPE_TOL = 0.005
ANTI_FAB_TAIL_RMSE_TOL_BPS = 2.0
ANTI_FAB_IND_SHARE_MAE_TOL = 0.02
ANTI_FAB_ALLOC_MAE_TOL = 0.02
ANTI_FAB_REF_DIS_TOL_BPS = 5.0

LANE_WEIGHTS = {
    "L1_bid_ladder_accuracy": 25,
    "L2_bidToCover_prediction": 15,
    "L3_tail_control": 15,
    "L4_allocation_share_calibration": 10,
    "L5_indirect_direct_share": 10,
    "L6_reference_yield_dislocation": 10,
    "L7_anti_fabrication": 5,
    "L8_cross_product_mix_stability": 10,
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


def _ladder_emd_bps(predicted_ladder: list[dict], realized_curve: list[dict]) -> float:
    if not predicted_ladder or not realized_curve:
        return LADDER_EMD_ZERO_BPS
    p = sorted(predicted_ladder, key=lambda x: x.get("yield_bps", 0))
    r = sorted(realized_curve, key=lambda x: x.get("yield_bps", 0))
    py = np.array([x["yield_bps"] for x in p], dtype=float)
    pq = np.array([x["quantity_pct"] for x in p], dtype=float) / 100.0
    ry = np.array([x["yield_bps"] for x in r], dtype=float)
    rq = np.array([x["quantity_pct"] for x in r], dtype=float) / 100.0
    grid = np.unique(np.concatenate([py, ry]))
    if len(grid) < 2:
        return LADDER_EMD_ZERO_BPS
    p_cum = np.interp(grid, py, pq, left=0.0, right=1.0)
    r_cum = np.interp(grid, ry, rq, left=0.0, right=1.0)
    emd = float(np.trapezoid(np.abs(p_cum - r_cum), grid))
    return emd


def score_L1_bid_ladder(predicted_ladder: list[dict], realized_curve: list[dict]) -> float:
    emd = _ladder_emd_bps(predicted_ladder, realized_curve)
    return _linear_score(emd, LADDER_EMD_ZERO_BPS, LADDER_EMD_FULL_BPS, LANE_WEIGHTS["L1_bid_ladder_accuracy"])


def score_L2_bidToCover(pred: float, real: float) -> float:
    if not (np.isfinite(pred) and np.isfinite(real)) or real <= 0:
        return 0.0
    mape = abs(pred - real) / real
    return _linear_score(mape, BTC_MAPE_ZERO, BTC_MAPE_FULL, LANE_WEIGHTS["L2_bidToCover_prediction"])


def score_L3_tail(pred_bps: float, real_bps: float, security_type: str) -> float:
    if not (np.isfinite(pred_bps) and np.isfinite(real_bps)):
        return 0.0
    err = abs(pred_bps - real_bps)
    full = TAIL_RMSE_FULL_BPS_BILL if security_type == "Bill" else TAIL_RMSE_FULL_BPS_NOTE_BOND
    return _linear_score(err, TAIL_RMSE_ZERO_BPS, full, LANE_WEIGHTS["L3_tail_control"])


def score_L4_allocation(pred: float, real: float) -> float:
    if not (np.isfinite(pred) and np.isfinite(real)):
        return 0.0
    err = abs(pred - real)
    return _linear_score(err, ALLOC_MAE_ZERO, ALLOC_MAE_FULL, LANE_WEIGHTS["L4_allocation_share_calibration"])


def score_L5_shares(pred_ind: float, real_ind: float, pred_dir: float, real_dir: float) -> float:
    if not (np.isfinite(pred_ind) and np.isfinite(real_ind)
            and np.isfinite(pred_dir) and np.isfinite(real_dir)):
        return 0.0
    err = 0.5 * (abs(pred_ind - real_ind) + abs(pred_dir - real_dir))
    return _linear_score(err, SHARE_MAE_ZERO, SHARE_MAE_FULL, LANE_WEIGHTS["L5_indirect_direct_share"])


def score_L6_reference_dislocation(pred_bps: float, real_bps: float) -> float:
    if not (np.isfinite(pred_bps) and np.isfinite(real_bps)):
        return 0.0
    err = abs(pred_bps - real_bps)
    magnitude_score = _linear_score(err, REF_DIS_MAE_ZERO_BPS, REF_DIS_MAE_FULL_BPS,
                                    LANE_WEIGHTS["L6_reference_yield_dislocation"])
    directional_bonus = 0.0
    if np.sign(pred_bps) == np.sign(real_bps) and abs(real_bps) > 1.0:
        directional_bonus = LANE_WEIGHTS["L6_reference_yield_dislocation"] * 0.10
    return min(LANE_WEIGHTS["L6_reference_yield_dislocation"], magnitude_score + directional_bonus)


def score_L7_anti_fabrication(self_reported: dict[str, float],
                              judge_metrics: dict[str, float]) -> tuple[float, bool, list[str]]:
    violations: list[str] = []
    if not self_reported or not judge_metrics:
        return 0.0, True, ["missing self_reported_metrics or judge_metrics"]
    checks = [
        ("mean_bidToCover_mape", ANTI_FAB_BTC_MAPE_TOL),
        ("mean_tail_rmse_bps", ANTI_FAB_TAIL_RMSE_TOL_BPS),
        ("mean_indirect_share_mae", ANTI_FAB_IND_SHARE_MAE_TOL),
        ("mean_allocation_share_mae", ANTI_FAB_ALLOC_MAE_TOL),
        ("mean_reference_dislocation_mae_bps", ANTI_FAB_REF_DIS_TOL_BPS),
    ]
    for key, tol in checks:
        sr = self_reported.get(key)
        jm = judge_metrics.get(key)
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


def score_auction(pred_auction: dict[str, Any], realized_row: dict[str, Any],
                  realized_curve: list[dict],
                  judge_recompute_metrics: dict[str, float]) -> dict[str, Any]:
    pred_ladder = pred_auction.get("predicted_bid_ladder") or []
    pred_btc = float(pred_auction.get("predicted_bidToCover") or 0.0)
    pred_tail_bps = float(pred_auction.get("predicted_tail_bps") or 0.0)
    pred_alloc = float(pred_auction.get("predicted_allocation_share") or 0.0)
    pred_ind = float(pred_auction.get("predicted_indirect_share") or 0.0)
    pred_dir = float(pred_auction.get("predicted_direct_share") or 0.0)
    pred_ref_dis_bps = float(pred_auction.get("predicted_reference_dislocation_bps") or 0.0)

    real_btc = float(realized_row.get("bidToCoverRatio") or 0.0)
    real_hy = float(realized_row.get("highYield_effective") or 0.0)
    real_my = float(realized_row.get("averageMedianYield_effective") or 0.0)
    real_tail_bps = (real_hy - real_my) * 100.0 if (real_hy > 0 and real_my > 0) else float("nan")
    real_total = float(realized_row.get("totalAccepted") or 0.0)
    real_ind = (float(realized_row.get("indirectBidderAccepted") or 0.0) / real_total) if real_total > 0 else float("nan")
    real_dir = (float(realized_row.get("directBidderAccepted") or 0.0) / real_total) if real_total > 0 else float("nan")
    real_alloc = float(realized_row.get("allocationPercentage") or 0.0) / 100.0
    real_ref_dis_bps = float(realized_row.get("reference_dislocation_bps") or float("nan"))
    security_type = str(realized_row.get("securityType") or "Note")

    l1 = score_L1_bid_ladder(pred_ladder, realized_curve)
    l2 = score_L2_bidToCover(pred_btc, real_btc)
    l3 = score_L3_tail(pred_tail_bps, real_tail_bps, security_type)
    l4 = score_L4_allocation(pred_alloc, real_alloc)
    l5 = score_L5_shares(pred_ind, real_ind, pred_dir, real_dir)
    l6 = score_L6_reference_dislocation(pred_ref_dis_bps, real_ref_dis_bps)

    return {
        "cusip": pred_auction.get("cusip"),
        "securityType": security_type,
        "lanes": {
            "L1_bid_ladder_accuracy": round(l1, 3),
            "L2_bidToCover_prediction": round(l2, 3),
            "L3_tail_control": round(l3, 3),
            "L4_allocation_share_calibration": round(l4, 3),
            "L5_indirect_direct_share": round(l5, 3),
            "L6_reference_yield_dislocation": round(l6, 3),
        },
        "sub_total": round(l1 + l2 + l3 + l4 + l5 + l6, 3),
        "l7_pending_aggregate": True,
    }


def cross_product_mix_stability_score(per_auction: list[dict]) -> float:
    if len(per_auction) < 3:
        return 0.0
    by_type: dict[str, list[float]] = {}
    for row in per_auction:
        st = row.get("securityType", "Note")
        by_type.setdefault(st, []).append(row["lanes"]["L1_bid_ladder_accuracy"])
    means = [float(np.mean(v)) for v in by_type.values() if v]
    if len(means) < 2:
        return LANE_WEIGHTS["L8_cross_product_mix_stability"] * 0.5
    var = float(np.var(means))
    mean_over_types = float(np.mean(means))
    var_baseline = 30.0
    var_frac = max(0.0, min(1.0, 1.0 - var / max(var_baseline, 1e-9)))
    mean_frac = min(1.0, mean_over_types / 12.0)
    return LANE_WEIGHTS["L8_cross_product_mix_stability"] * mean_frac * var_frac


def regime_shift_bonus(detected_events: list[dict], true_events: list[dict],
                       tolerance_days: int = 3) -> tuple[float, int, int]:
    from datetime import datetime
    if not true_events or not detected_events:
        return 0.0, 0, len(true_events) if true_events else 0
    try:
        true_dates = [datetime.strptime(e["event_date"], "%Y-%m-%d") for e in true_events]
        det_dates = [datetime.strptime(e["event_date"], "%Y-%m-%d") for e in detected_events]
    except Exception:
        return 0.0, 0, len(true_events) if true_events else 0
    hits = 0
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
