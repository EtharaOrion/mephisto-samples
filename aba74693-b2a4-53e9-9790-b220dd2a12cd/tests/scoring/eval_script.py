#!/usr/bin/env python3
"""
eval_script.py — judge-side per-cycle scoring runner for auction bidding.

Loads test_auctions.json, invokes /home/workspace/auction_bidding.py --backtest
against the full held-out 2025 auction cycle, parses bidding_results.json,
per-auction recomputes bidToCover / tail / indirect-share / allocation-share /
reference-dislocation from raw ladder + predictions, calls score.py per
auction, aggregates with cross-product-mix stability and rate-regime-shift
bonus.

Emits: TOTAL_SCORE <N> on stdout for the Harbor scorer_manifest parser.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import (
    score_auction, score_L7_anti_fabrication, cross_product_mix_stability_score,
    regime_shift_bonus, LANE_WEIGHTS, LANE_TOTAL,
)

WORKSPACE = Path("/home/workspace")
SCORING = WORKSPACE / "scoring"
AGENT_SCRIPT = WORKSPACE / "auction_bidding.py"
STATE_JSON = WORKSPACE / "reference_state.json"

BACKTEST_TIMEOUT_SEC = 2700


def _find(*rel: str) -> Path:
    for base in (WORKSPACE, SCORING):
        p = base / rel[0]
        if p.exists():
            return p
    return WORKSPACE / rel[0]


def _load_test_auctions() -> list[dict]:
    p = _find("test_auctions.json")
    return json.loads(p.read_text()).get("auctions", [])


def _load_true_regime_events() -> list[dict]:
    p = _find("true_rate_regime_events.json")
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("events", [])


def _load_test_auction_history() -> pd.DataFrame:
    p = _find("auction_history_test.csv")
    df = pd.read_csv(p)
    df["auctionDate"] = pd.to_datetime(df["auctionDate"])
    return df.sort_values(["auctionDate", "cusip"]).reset_index(drop=True)


def _load_test_macro() -> pd.DataFrame:
    p = _find("macro_indicators_test.csv")
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _reference_yield_for_tenor(macro_row: dict[str, float], tenor_years: float) -> float:
    if tenor_years <= 0.15:
        return float(macro_row.get("DGS1MO", 2.0))
    if tenor_years <= 0.30:
        return float(macro_row.get("DGS3MO", 2.5))
    if tenor_years <= 3.0:
        return float(macro_row.get("DGS2", 2.5))
    if tenor_years <= 12.0:
        return float(macro_row.get("DGS10", 3.0))
    return 0.5 * (float(macro_row.get("DGS10", 3.0)) + float(macro_row.get("DGS30", 4.0)))


def _macro_lookup(macro_df: pd.DataFrame, target_date: pd.Timestamp) -> dict[str, float]:
    m = macro_df[macro_df["date"] <= target_date]
    if len(m) == 0:
        return {"DFF": 2.0, "DGS10": 3.0, "T10Y2Y": 0.5, "DGS2": 2.5,
                "DGS30": 4.0, "DGS1MO": 2.0, "DGS3MO": 2.5}
    r = m.iloc[-1]
    return {c: float(r.get(c) if pd.notna(r.get(c)) else 2.0)
            for c in ["DFF", "DGS10", "T10Y2Y", "DGS2", "DGS30", "DGS1MO", "DGS3MO"]}


def _tenor_years(term: str, security_type: str) -> float:
    lookup = {
        "4-Week": 4/52, "8-Week": 8/52, "13-Week": 0.25, "17-Week": 17/52,
        "26-Week": 0.5, "52-Week": 1.0,
        "2-Year": 2.0, "3-Year": 3.0, "5-Year": 5.0, "7-Year": 7.0,
        "10-Year": 10.0, "20-Year": 20.0, "30-Year": 30.0,
        "9-Year 10-Month": 9.833, "9-Year 8-Month": 9.667,
        "19-Year 10-Month": 19.833, "19-Year 11-Month": 19.917,
        "29-Year 10-Month": 29.833, "29-Year 11-Month": 29.917,
        "29-Year 8-Month": 29.667, "9-Year 11-Month": 9.917,
    }
    s = str(term or "").strip()
    if s in lookup:
        return lookup[s]
    for k, v in lookup.items():
        if k in s:
            return v
    return {"Bill": 0.25, "Note": 5.0, "Bond": 20.0}.get(str(security_type), 5.0)


def _invoke_agent_backtest() -> tuple[bool, str, dict | None]:
    output_path = WORKSPACE / "bidding_results.json"
    if not AGENT_SCRIPT.exists():
        return False, f"agent script not found at {AGENT_SCRIPT}", None
    data_p = _find("auction_history_test.csv")
    macro_p = _find("macro_indicators_test.csv")
    auctions_p = _find("test_auctions.json")
    cmd = [
        sys.executable, str(AGENT_SCRIPT),
        "--backtest",
        f"--data={data_p}",
        f"--macro={macro_p}",
        f"--auctions={auctions_p}",
        f"--state={STATE_JSON}",
        f"--output={output_path}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=BACKTEST_TIMEOUT_SEC)
        if r.returncode != 0:
            return False, f"agent returncode={r.returncode}: {r.stderr[-1000:]}", None
        if not output_path.exists():
            return False, "bidding_results.json not produced", None
        d = json.loads(output_path.read_text())
        return True, "ok", d
    except subprocess.TimeoutExpired:
        return False, "agent timeout", None
    except Exception as e:
        return False, f"agent invocation failed: {e}", None


def _synthesize_realized_curve(hy: float, my: float, security_type: str) -> list[dict]:
    if not (np.isfinite(hy) and np.isfinite(my)):
        return []
    hy_bps = int(round(hy * 100))
    my_bps = int(round(my * 100))
    if my_bps > hy_bps:
        my_bps, hy_bps = hy_bps, my_bps
    span = max(hy_bps - my_bps, 1)
    q = [0.05, 0.15, 0.30, 0.42, 0.50, 0.58, 0.70, 0.85, 0.95]
    points = []
    for i, qq in enumerate(q):
        pos = (qq - 0.50)
        y_bps = int(round(my_bps + pos * 2.5 * span))
        points.append({"yield_bps": y_bps, "quantity_pct": round((i + 1) / len(q) * 100.0, 2)})
    points[-1]["quantity_pct"] = 100.0
    return points


def _clearing_yield(row: pd.Series) -> float:
    for k in ["highYield", "highInvestmentRate", "highDiscountRate"]:
        v = row.get(k)
        if v is not None and pd.notna(v) and float(v) > 0:
            return float(v)
    return float("nan")


def _median_yield(row: pd.Series) -> float:
    for k in ["averageMedianYield", "averageMedianInvestmentRate", "averageMedianDiscountRate"]:
        v = row.get(k)
        if v is not None and pd.notna(v) and float(v) > 0:
            return float(v)
    return float("nan")


def main() -> None:
    print("=" * 70)
    print(f"eval_script.py started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    manifest = _load_test_auctions()
    true_events = _load_true_regime_events()
    hist = _load_test_auction_history()
    macro = _load_test_macro()
    print(f"Loaded {len(manifest)} test auctions, {len(true_events)} true regime events, "
          f"{len(hist)} realized rows, {len(macro)} macro rows")

    ok, msg, br = _invoke_agent_backtest()
    if not ok:
        print(f"FAIL: {msg}")
        print(f"TOTAL_SCORE 0.00")
        report = {"error": msg, "final_total": 0.0}
        try:
            (WORKSPACE / "score_report.json").write_text(json.dumps(report, indent=2))
        except Exception:
            pass
        sys.exit(1)
    assert br is not None
    pred_auctions = {p.get("cusip"): p for p in br.get("auctions", [])}
    detected_events = br.get("detected_regime_events", [])
    self_reported = br.get("self_reported_metrics", {})

    per_auction_scores: list[dict] = []
    judge_metric_bucket = {
        "mean_bidToCover_mape": [],
        "mean_tail_rmse_bps_sq": [],
        "mean_indirect_share_mae": [],
        "mean_allocation_share_mae": [],
        "mean_reference_dislocation_mae_bps": [],
    }

    for _, r in hist.iterrows():
        cusip = str(r.get("cusip"))
        pred = pred_auctions.get(cusip)
        if pred is None:
            per_auction_scores.append({
                "cusip": cusip,
                "securityType": r.get("securityType"),
                "lanes": {k: 0.0 for k in LANE_WEIGHTS if k not in ("L7_anti_fabrication", "L8_cross_product_mix_stability")},
                "sub_total": 0.0,
                "missing_prediction": True,
            })
            continue

        hy = _clearing_yield(r)
        my = _median_yield(r)
        realized_curve = _synthesize_realized_curve(hy, my, r.get("securityType"))
        tenor = _tenor_years(r.get("securityTerm"), r.get("securityType"))
        macro_row = _macro_lookup(macro, r["auctionDate"] - pd.Timedelta(days=1))
        ref_yield_pct = _reference_yield_for_tenor(macro_row, tenor)
        ref_dis_bps = (hy - ref_yield_pct) * 100.0 if np.isfinite(hy) else float("nan")

        row_ext = dict(r)
        row_ext["highYield_effective"] = hy
        row_ext["averageMedianYield_effective"] = my
        row_ext["reference_dislocation_bps"] = ref_dis_bps

        s = score_auction(pred, row_ext, realized_curve, {})
        per_auction_scores.append(s)

        real_btc = float(r.get("bidToCoverRatio") or 0)
        pred_btc = float(pred.get("predicted_bidToCover") or 0)
        if real_btc > 0:
            judge_metric_bucket["mean_bidToCover_mape"].append(abs(pred_btc - real_btc) / real_btc)
        real_tail_bps = (hy - my) * 100.0 if (np.isfinite(hy) and np.isfinite(my)) else float("nan")
        pred_tail_bps = float(pred.get("predicted_tail_bps") or 0)
        if np.isfinite(real_tail_bps):
            judge_metric_bucket["mean_tail_rmse_bps_sq"].append((pred_tail_bps - real_tail_bps) ** 2)
        real_total = float(r.get("totalAccepted") or 0)
        real_ind = (float(r.get("indirectBidderAccepted") or 0) / real_total) if real_total > 0 else float("nan")
        pred_ind = float(pred.get("predicted_indirect_share") or 0)
        if np.isfinite(real_ind):
            judge_metric_bucket["mean_indirect_share_mae"].append(abs(pred_ind - real_ind))
        real_alloc = float(r.get("allocationPercentage") or 0) / 100.0
        pred_alloc = float(pred.get("predicted_allocation_share") or 0)
        judge_metric_bucket["mean_allocation_share_mae"].append(abs(pred_alloc - real_alloc))
        pred_ref_dis_bps = float(pred.get("predicted_reference_dislocation_bps") or 0)
        if np.isfinite(ref_dis_bps):
            judge_metric_bucket["mean_reference_dislocation_mae_bps"].append(abs(pred_ref_dis_bps - ref_dis_bps))

    judge_metrics = {
        "mean_bidToCover_mape": float(np.mean(judge_metric_bucket["mean_bidToCover_mape"])) if judge_metric_bucket["mean_bidToCover_mape"] else 0.0,
        "mean_tail_rmse_bps": float(np.sqrt(np.mean(judge_metric_bucket["mean_tail_rmse_bps_sq"]))) if judge_metric_bucket["mean_tail_rmse_bps_sq"] else 0.0,
        "mean_indirect_share_mae": float(np.mean(judge_metric_bucket["mean_indirect_share_mae"])) if judge_metric_bucket["mean_indirect_share_mae"] else 0.0,
        "mean_allocation_share_mae": float(np.mean(judge_metric_bucket["mean_allocation_share_mae"])) if judge_metric_bucket["mean_allocation_share_mae"] else 0.0,
        "mean_reference_dislocation_mae_bps": float(np.mean(judge_metric_bucket["mean_reference_dislocation_mae_bps"])) if judge_metric_bucket["mean_reference_dislocation_mae_bps"] else 0.0,
    }

    l7_pts, l7_veto, l7_notes = score_L7_anti_fabrication(self_reported, judge_metrics)
    if l7_veto:
        for row in per_auction_scores:
            row["lanes"]["L1_bid_ladder_accuracy"] = 0.0
            row["lanes"]["L2_bidToCover_prediction"] = 0.0
            row["sub_total"] = sum(row["lanes"].values())

    n = max(len(per_auction_scores), 1)
    lane_avg: dict[str, float] = {}
    for k in ["L1_bid_ladder_accuracy", "L2_bidToCover_prediction", "L3_tail_control",
              "L4_allocation_share_calibration", "L5_indirect_direct_share",
              "L6_reference_yield_dislocation"]:
        vals = [row["lanes"].get(k, 0.0) for row in per_auction_scores]
        lane_avg[k] = float(np.mean(vals)) if vals else 0.0
    lane_avg["L7_anti_fabrication"] = l7_pts
    lane_avg["L8_cross_product_mix_stability"] = cross_product_mix_stability_score(per_auction_scores)

    bonus, hits, total_evts = regime_shift_bonus(detected_events, true_events, tolerance_days=3)
    print(f"detected regime events: {len(detected_events)}; matched {hits}/{total_evts} true events; bonus={bonus:.2f}")

    base_total = sum(lane_avg.values())

    print(f"\n=== Per-Lane Averages Across {n} Auctions ===")
    for k, v in lane_avg.items():
        print(f"  {k:36s} {v:6.2f} / {LANE_WEIGHTS[k]}")
    print(f"  {'Base total':36s} {base_total:6.2f} / {LANE_TOTAL}")
    print(f"  {'Regime-shift bonus':36s} {bonus:6.2f} / 10")

    total = base_total + bonus
    total = max(0.0, min(total, 110.0))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_auctions": n,
        "lane_averages": lane_avg,
        "l7_veto": l7_veto,
        "l7_notes": l7_notes,
        "judge_metrics": judge_metrics,
        "self_reported_metrics": self_reported,
        "regime_shift_bonus": bonus,
        "detected_regime_events": len(detected_events),
        "true_regime_events_matched": hits,
        "true_regime_events_total": total_evts,
        "base_total": base_total,
        "final_total": total,
        "per_auction_scores": per_auction_scores,
    }
    try:
        (WORKSPACE / "score_report.json").write_text(json.dumps(report, indent=2, default=float))
        print(f"\nScore report written to {WORKSPACE / 'score_report.json'}")
    except Exception as e:
        print(f"WARN could not write score_report.json: {e}")

    print(f"\nFinal total score: {total:.2f} / 110")
    print(f"TOTAL_SCORE {total:.2f}")


if __name__ == "__main__":
    main()
