#!/usr/bin/env python3
"""
score.py — per-observation 8-lane scoring for fdic_bank_capital_projection_book.

Lane anchors are capped at institutional-frontier values per PKW-FAMILIES
section 3 Framework B (Tier-1 leverage MAE floor 0.3pp, CET1 MAE floor 0.4pp,
earnings MAPE floor 8%, tail bound MAE floor 0.10pp). Anchors are set by
reality and never moved to hit a desired score band.

Lanes (total 100, plus +10 aggregated PCA-zone-transition detection bonus):
  L1 capital_ratio_projection    25 pts   MAE across IDT1CER + IDT1RWAJR + RBC1AAJ + RBCRWAJ (pp)
  L2 earnings_projection         15 pts   MAPE across NIMYQ + ROAQ + ROEQ
  L3 tail_risk_control           15 pts   MAE across NPERFV + NCLNLSR (pp)
  L4 pca_zone_classification     10 pts   categorical accuracy on 5-zone PCA classification
  L5 asset_growth_projection     10 pts   MAE on ASSET growth-rate
  L6 deposit_stability           10 pts   MAE on DEPDOM growth
  L7 anti_fabrication             5 pts   self-report vs judge-recompute agreement
  L8 cross_size_bucket_stability 10 pts   aggregated (returned 0 here)

PCA-zone-transition bonus (+10 pts, aggregated): detected transitions matching
true_pca_zone_events.json within 1-quarter tolerance, saturating at 3 hits.
"""
from __future__ import annotations

from typing import Any

import numpy as np


CAPITAL_MAE_FULL_PP = 0.40
CAPITAL_MAE_ZERO_PP = 3.50

EARNINGS_MAPE_FULL = 0.10
EARNINGS_MAPE_ZERO = 0.50

TAIL_MAE_FULL_PP = 0.10
TAIL_MAE_ZERO_PP = 1.00

ZONE_ACC_FULL = 0.80
ZONE_ACC_ZERO = 0.20

ASSET_GROWTH_MAE_FULL = 0.010
ASSET_GROWTH_MAE_ZERO = 0.080

DEPOSIT_GROWTH_MAE_FULL = 0.012
DEPOSIT_GROWTH_MAE_ZERO = 0.080

ANTI_FAB_CAPITAL_MAE_TOL_PP = 0.05
ANTI_FAB_EARNINGS_MAPE_TOL = 0.02
ANTI_FAB_TAIL_MAE_TOL_PP = 0.05
ANTI_FAB_ASSET_GROWTH_MAE_TOL = 0.010
ANTI_FAB_DEPOSIT_GROWTH_MAE_TOL = 0.010
ANTI_FAB_ZONE_ACC_TOL = 0.10

LANE_WEIGHTS = {
    "L1_capital_ratio_projection": 25,
    "L2_earnings_projection": 15,
    "L3_tail_risk_control": 15,
    "L4_pca_zone_classification": 10,
    "L5_asset_growth_projection": 10,
    "L6_deposit_stability": 10,
    "L7_anti_fabrication": 5,
    "L8_cross_size_bucket_stability": 10,
}
LANE_TOTAL = sum(LANE_WEIGHTS.values())

CAPITAL_METRICS_ANCHOR = ["IDT1CER", "IDT1RWAJR", "RBC1AAJ", "RBCRWAJ"]
EARNINGS_METRICS_ANCHOR = ["NIMYQ", "ROAQ", "ROEQ"]
TAIL_METRICS_ANCHOR = ["NPERFV", "NCLNLSR"]

PCA_ZONE_ORDER = [
    "well_capitalized", "adequately_capitalized",
    "undercapitalized", "significantly_under", "critically_under",
]


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


def _pca_zone(t1_rwa: float, total_rbc: float, t1_lev: float) -> str:
    if not (np.isfinite(t1_rwa) and np.isfinite(total_rbc) and np.isfinite(t1_lev)):
        return "adequately_capitalized"
    if total_rbc >= 10.0 and t1_rwa >= 6.0 and t1_lev >= 5.0:
        return "well_capitalized"
    if total_rbc >= 8.0 and t1_rwa >= 4.5 and t1_lev >= 4.0:
        return "adequately_capitalized"
    if total_rbc >= 6.0 and t1_rwa >= 4.0 and t1_lev >= 3.0:
        return "undercapitalized"
    if total_rbc >= 2.0:
        return "significantly_under"
    return "critically_under"


def score_L1_capital(predicted: dict[str, float], realized: dict[str, float]) -> float:
    errs = []
    for m in CAPITAL_METRICS_ANCHOR:
        p = predicted.get(m)
        r = realized.get(m)
        if p is not None and r is not None and np.isfinite(p) and np.isfinite(r):
            errs.append(abs(float(p) - float(r)))
    if not errs:
        return 0.0
    mae = float(np.mean(errs))
    return _linear_score(mae, CAPITAL_MAE_ZERO_PP, CAPITAL_MAE_FULL_PP,
                         LANE_WEIGHTS["L1_capital_ratio_projection"])


def score_L2_earnings(predicted: dict[str, float], realized: dict[str, float]) -> float:
    errs = []
    for m in EARNINGS_METRICS_ANCHOR:
        p = predicted.get(m)
        r = realized.get(m)
        if p is not None and r is not None and np.isfinite(p) and np.isfinite(r) and abs(r) > 0.01:
            errs.append(abs(float(p) - float(r)) / max(abs(float(r)), 0.1))
    if not errs:
        return 0.0
    mape = float(np.mean(errs))
    return _linear_score(mape, EARNINGS_MAPE_ZERO, EARNINGS_MAPE_FULL,
                         LANE_WEIGHTS["L2_earnings_projection"])


def score_L3_tail(predicted: dict[str, float], realized: dict[str, float]) -> float:
    errs = []
    for m in TAIL_METRICS_ANCHOR:
        p = predicted.get(m)
        r = realized.get(m)
        if p is not None and r is not None and np.isfinite(p) and np.isfinite(r):
            errs.append(abs(float(p) - float(r)))
    if not errs:
        return 0.0
    mae = float(np.mean(errs))
    return _linear_score(mae, TAIL_MAE_ZERO_PP, TAIL_MAE_FULL_PP,
                         LANE_WEIGHTS["L3_tail_risk_control"])


def score_L4_zone(predicted_zone: str, realized: dict[str, float]) -> tuple[float, bool]:
    rt1 = realized.get("IDT1RWAJR")
    rrb = realized.get("RBCRWAJ")
    rlev = realized.get("RBC1AAJ")
    if rt1 is None or rrb is None or rlev is None:
        return 0.0, False
    realized_zone = _pca_zone(float(rt1), float(rrb), float(rlev))
    matched = predicted_zone == realized_zone
    per_obs_pts = LANE_WEIGHTS["L4_pca_zone_classification"] if matched else 0.0
    return per_obs_pts, matched


def score_L5_asset_growth(predicted_rate: float, prior_asset: float, current_asset: float) -> float:
    if not (prior_asset > 0 and current_asset > 0):
        return 0.0
    realized_rate = (current_asset - prior_asset) / prior_asset
    err = abs(predicted_rate - realized_rate)
    return _linear_score(err, ASSET_GROWTH_MAE_ZERO, ASSET_GROWTH_MAE_FULL,
                         LANE_WEIGHTS["L5_asset_growth_projection"])


def score_L6_deposit(predicted_rate: float, prior_dep: float, current_dep: float) -> float:
    if not (prior_dep > 0 and current_dep > 0):
        return 0.0
    realized_rate = (current_dep - prior_dep) / prior_dep
    err = abs(predicted_rate - realized_rate)
    return _linear_score(err, DEPOSIT_GROWTH_MAE_ZERO, DEPOSIT_GROWTH_MAE_FULL,
                         LANE_WEIGHTS["L6_deposit_stability"])


def score_L7_anti_fabrication(self_reported: dict[str, float],
                              judge_metrics: dict[str, float]) -> tuple[float, bool, list[str]]:
    violations: list[str] = []
    if not self_reported or not judge_metrics:
        return 0.0, True, ["missing self_reported_metrics or judge_metrics"]
    checks = [
        ("mean_capital_ratio_mae_pp", ANTI_FAB_CAPITAL_MAE_TOL_PP),
        ("mean_earnings_mape", ANTI_FAB_EARNINGS_MAPE_TOL),
        ("mean_tail_bound_mae_pp", ANTI_FAB_TAIL_MAE_TOL_PP),
        ("mean_asset_growth_mae", ANTI_FAB_ASSET_GROWTH_MAE_TOL),
        ("mean_deposit_growth_mae", ANTI_FAB_DEPOSIT_GROWTH_MAE_TOL),
        ("pca_zone_accuracy", ANTI_FAB_ZONE_ACC_TOL),
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


def cross_size_bucket_stability_score(per_observation: list[dict]) -> float:
    if len(per_observation) < 4:
        return 0.0
    by_bucket: dict[str, list[float]] = {}
    for row in per_observation:
        b = row.get("size_bucket", "community")
        by_bucket.setdefault(b, []).append(row["lanes"].get("L1_capital_ratio_projection", 0.0))
    means = [float(np.mean(v)) for v in by_bucket.values() if v]
    if len(means) < 2:
        return LANE_WEIGHTS["L8_cross_size_bucket_stability"] * 0.5
    var = float(np.var(means))
    mean_over = float(np.mean(means))
    var_baseline = 25.0
    var_frac = max(0.0, min(1.0, 1.0 - var / max(var_baseline, 1e-9)))
    mean_frac = min(1.0, mean_over / 15.0)
    return LANE_WEIGHTS["L8_cross_size_bucket_stability"] * mean_frac * var_frac


def score_observation(pred_obs: dict[str, Any], realized_row: dict[str, Any],
                      prior_asset: float, prior_deposit: float) -> dict[str, Any]:
    pred_metrics = pred_obs.get("predicted_metrics") or {}
    pred_zone = str(pred_obs.get("predicted_pca_zone") or "adequately_capitalized")
    pred_asset_growth = float(pred_obs.get("predicted_asset_growth_rate") or 0.0)
    pred_deposit_growth = float(pred_obs.get("predicted_deposit_growth_rate") or 0.0)

    realized_metrics: dict[str, float] = {}
    for m in CAPITAL_METRICS_ANCHOR + EARNINGS_METRICS_ANCHOR + TAIL_METRICS_ANCHOR + ["IDT1RWAJR", "RBCRWAJ", "RBC1AAJ"]:
        v = realized_row.get(m)
        try:
            fv = float(v) if v is not None else None
            if fv is not None and np.isfinite(fv):
                realized_metrics[m] = fv
        except Exception:
            pass

    l1 = score_L1_capital(pred_metrics, realized_metrics)
    l2 = score_L2_earnings(pred_metrics, realized_metrics)
    l3 = score_L3_tail(pred_metrics, realized_metrics)
    l4_pts, l4_matched = score_L4_zone(pred_zone, realized_metrics)
    current_asset = float(realized_row.get("ASSET") or 0.0)
    current_dep = float(realized_row.get("DEPDOM") or 0.0)
    l5 = score_L5_asset_growth(pred_asset_growth, prior_asset, current_asset)
    l6 = score_L6_deposit(pred_deposit_growth, prior_deposit, current_dep)

    return {
        "cert": pred_obs.get("cert"),
        "repdte": pred_obs.get("repdte"),
        "size_bucket": pred_obs.get("size_bucket", "community"),
        "lanes": {
            "L1_capital_ratio_projection": round(l1, 3),
            "L2_earnings_projection": round(l2, 3),
            "L3_tail_risk_control": round(l3, 3),
            "L4_pca_zone_classification": round(l4_pts, 3),
            "L5_asset_growth_projection": round(l5, 3),
            "L6_deposit_stability": round(l6, 3),
        },
        "sub_total": round(l1 + l2 + l3 + l4_pts + l5 + l6, 3),
        "l4_matched": bool(l4_matched),
        "l7_pending_aggregate": True,
    }


def pca_zone_transition_bonus(detected_events: list[dict], true_events: list[dict],
                              tolerance_quarters: int = 1) -> tuple[float, int, int]:
    if not true_events or not detected_events:
        return 0.0, 0, len(true_events) if true_events else 0
    hits = 0
    from datetime import datetime as _dt

    def _q(dstr: str) -> int:
        try:
            d = _dt.strptime(str(dstr), "%Y%m%d")
        except Exception:
            return 0
        return d.year * 4 + (d.month - 1) // 3

    true_keys = [(int(e.get("cert", 0)), _q(e.get("event_date", "0"))) for e in true_events]
    det_keys = [(int(e.get("cert", 0)), _q(e.get("event_date", "0"))) for e in detected_events]
    for cert_t, q_t in true_keys:
        for cert_d, q_d in det_keys:
            if cert_d == cert_t and abs(q_d - q_t) <= tolerance_quarters:
                hits += 1
                break
    total = len(true_keys)
    saturation_threshold = 3
    bonus_frac = min(1.0, hits / saturation_threshold)
    return 10.0 * bonus_frac, hits, total
