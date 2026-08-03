#!/usr/bin/env python3
"""
eval_script.py - judge-side scoring runner for fed_funds_regime_positioning_book.

Invokes the agent's --backtest against the hidden 2025Q1-2026H1 rates panel,
parses positioning_results.json, per-window recomputes regime accuracy + yield
MAE + duration/slope PnL Sharpe + carry PnL sum, computes 6-month bucket
cross-cadence stability lane, adds FOMC-decision bonus.

Emits: TOTAL_SCORE <N> on stdout for the Harbor scorer_manifest parser.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import (
    score_regime_accuracy, score_yield_2y_mae, score_yield_10y_mae,
    score_duration_sharpe, score_slope_sharpe, score_carry_pnl,
    score_anti_fabrication, score_cross_cadence_stability, fomc_decision_bonus,
    LANE_WEIGHTS, LANE_TOTAL,
)

WORKSPACE = Path("/home/workspace")
SCORING = WORKSPACE / "scoring"
AGENT_SCRIPT = WORKSPACE / "fed_funds_positioning.py"
STATE_JSON = WORKSPACE / "reference_state.json"

BACKTEST_TIMEOUT_SEC = 2700


def _find(name: str) -> Path:
    for base in (WORKSPACE, SCORING):
        p = base / name
        if p.exists():
            return p
    return WORKSPACE / name


def _prepare_agent_input_dir() -> Path:
    agent_input = WORKSPACE / "input"
    agent_input.mkdir(parents=True, exist_ok=True)
    for f in ["fed_funds_test.csv", "rates_test.csv", "macro_test.csv",
              "fomc_meetings_test_2025_2026.csv", "test_windows_schedule.json"]:
        src = _find(f)
        if src.exists():
            (agent_input / f).write_bytes(src.read_bytes())
    return agent_input


def _invoke_agent_backtest() -> tuple[bool, str, dict | None]:
    output_path = WORKSPACE / "positioning_results.json"
    if not AGENT_SCRIPT.exists():
        return False, f"agent script not found at {AGENT_SCRIPT}", None
    agent_input = _prepare_agent_input_dir()
    cmd = [sys.executable, str(AGENT_SCRIPT), "--backtest",
           str(agent_input), str(STATE_JSON), str(output_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=BACKTEST_TIMEOUT_SEC)
        if r.returncode != 0:
            return False, f"agent returncode={r.returncode}: {r.stderr[-1500:]}", None
        if not output_path.exists():
            return False, "positioning_results.json not produced", None
        d = json.loads(output_path.read_text())
        return True, "ok", d
    except subprocess.TimeoutExpired:
        return False, "agent timeout", None
    except Exception as e:
        return False, f"agent invocation failed: {e}", None


def _load_truth() -> tuple[list[dict], list[dict]]:
    tw = _find("test_windows_truth.json")
    te = _find("test_fomc_events.json")
    windows = json.loads(tw.read_text()).get("windows", []) if tw.exists() else []
    events = json.loads(te.read_text()).get("events", []) if te.exists() else []
    return windows, events


def _bucket_month(date_str: str) -> str:
    d = pd.to_datetime(date_str)
    return f"{d.year}H{'1' if d.month <= 6 else '2'}"


def _score_bucket(pred_by_date: dict, truth: list[dict]) -> dict[str, float]:
    correct = 0
    mae_2y = []
    mae_10y = []
    dur_pnls = []
    slope_pnls = []
    carry_pnls = []
    for w in truth:
        wd = w["window_date"]
        p = pred_by_date.get(wd)
        if p is None:
            continue
        realized_regime = w.get("realized_regime")
        if realized_regime and p.get("predicted_regime") == realized_regime:
            correct += 1
        pred_2y = p.get("predicted_2y_bps_next_wk")
        pred_10y = p.get("predicted_10y_bps_next_wk")
        real_2y_next = w.get("realized_2y_bps_next_wk")
        real_10y_next = w.get("realized_10y_bps_next_wk")
        if all(v is not None for v in [pred_2y, pred_10y, real_2y_next, real_10y_next]):
            mae_2y.append(abs(float(pred_2y) - float(real_2y_next)))
            mae_10y.append(abs(float(pred_10y) - float(real_10y_next)))
        rd2 = w.get("realized_2y_delta_next_wk_bps")
        rd10 = w.get("realized_10y_delta_next_wk_bps")
        book = p.get("positioning_book") or {}
        if rd2 is not None and rd10 is not None:
            d2 = float(book.get("duration_2y", 0.0))
            d10 = float(book.get("duration_10y", 0.0))
            sl = float(book.get("slope_2s10s", 0.0))
            ca = float(book.get("carry_front_end", 0.0))
            dur_pnls.append(d2 * (-float(rd2)) * 0.02 + d10 * (-float(rd10)) * 0.08)
            slope_pnls.append(sl * (float(rd10) - float(rd2)) * 0.03)
            carry_pnls.append(ca * (-float(rd2)) * 0.015)
    n = len(truth)
    accuracy = correct / n if n else 0.0
    return {
        "L1_regime_classification": score_regime_accuracy(accuracy),
        "L2_yield_2y_forecast": score_yield_2y_mae(float(np.mean(mae_2y)) if mae_2y else 0.0),
        "L3_yield_10y_forecast": score_yield_10y_mae(float(np.mean(mae_10y)) if mae_10y else 0.0),
        "L4_duration_positioning_pnl": score_duration_sharpe(dur_pnls),
        "L5_slope_positioning_pnl": score_slope_sharpe(slope_pnls),
        "L6_carry_position_pnl": score_carry_pnl(float(sum(carry_pnls))),
    }


_REQUIRED_TOP_KEYS = (
    "generated_at", "weekly_window_count", "weekly_windows",
    "fomc_event_count", "fomc_events", "self_reported_metrics",
)
_REQUIRED_SRM_KEYS = (
    "regime_accuracy", "yield_2y_mae_bps", "yield_10y_mae_bps",
    "duration_pnl_sum", "slope_pnl_sum", "carry_pnl_sum", "fomc_hit_count",
)


def _schema_precheck(res: dict) -> str | None:
    if not isinstance(res, dict):
        return f"root_not_object: got {type(res).__name__}"
    missing = [k for k in _REQUIRED_TOP_KEYS if k not in res]
    if missing:
        return f"missing_top_keys: {missing}"
    if not isinstance(res.get("weekly_windows"), list):
        return "weekly_windows_not_list"
    if not isinstance(res.get("fomc_events"), list):
        return "fomc_events_not_list"
    srm = res.get("self_reported_metrics")
    if not isinstance(srm, dict):
        return f"self_reported_metrics_not_object: got {type(srm).__name__}"
    srm_missing = [k for k in _REQUIRED_SRM_KEYS if k not in srm]
    if srm_missing:
        return f"missing_self_reported_metrics_keys: {srm_missing}"
    return None


def main() -> None:
    print("=" * 70)
    print(f"eval_script.py started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    truth_windows, truth_events = _load_truth()
    print(f"Loaded {len(truth_windows)} truth windows, {len(truth_events)} FOMC events")

    ok, msg, res = _invoke_agent_backtest()
    if not ok:
        print(f"FAIL: {msg}")
        print(f"TOTAL_SCORE 0.00")
        try:
            (WORKSPACE / "score_report.json").write_text(json.dumps(
                {"error": msg, "final_total": 0.0}, indent=2))
        except Exception:
            pass
        sys.exit(1)
    assert res is not None

    schema_error = _schema_precheck(res)
    if schema_error is not None:
        reason = f"schema_error: {schema_error}"
        print(f"FAIL: {reason}")
        print(f"TOTAL_SCORE 0.00")
        print(f"reason: {reason}")
        try:
            (WORKSPACE / "score_report.json").write_text(json.dumps(
                {"error": reason, "final_total": 0.0}, indent=2))
        except Exception:
            pass
        sys.exit(1)

    pred_by_date = {w["window_date"]: w for w in res.get("weekly_windows", [])}
    detected_events = res.get("fomc_events", [])
    self_reported = res.get("self_reported_metrics", {})

    correct = 0
    all_mae_2y = []
    all_mae_10y = []
    all_dur_pnls = []
    all_slope_pnls = []
    all_carry_pnls = []
    per_bucket: dict[str, list[dict]] = {}
    for w in truth_windows:
        wd = w["window_date"]
        p = pred_by_date.get(wd)
        bucket = _bucket_month(wd)
        per_bucket.setdefault(bucket, []).append(w)
        if p is None:
            continue
        if p.get("predicted_regime") == w.get("realized_regime"):
            correct += 1
        pred_2y = p.get("predicted_2y_bps_next_wk")
        pred_10y = p.get("predicted_10y_bps_next_wk")
        real_2y = w.get("realized_2y_bps_next_wk")
        real_10y = w.get("realized_10y_bps_next_wk")
        if all(v is not None for v in [pred_2y, pred_10y, real_2y, real_10y]):
            all_mae_2y.append(abs(float(pred_2y) - float(real_2y)))
            all_mae_10y.append(abs(float(pred_10y) - float(real_10y)))
        rd2 = w.get("realized_2y_delta_next_wk_bps")
        rd10 = w.get("realized_10y_delta_next_wk_bps")
        book = p.get("positioning_book") or {}
        if rd2 is not None and rd10 is not None:
            d2 = float(book.get("duration_2y", 0.0))
            d10 = float(book.get("duration_10y", 0.0))
            sl = float(book.get("slope_2s10s", 0.0))
            ca = float(book.get("carry_front_end", 0.0))
            all_dur_pnls.append(d2 * (-float(rd2)) * 0.02 + d10 * (-float(rd10)) * 0.08)
            all_slope_pnls.append(sl * (float(rd10) - float(rd2)) * 0.03)
            all_carry_pnls.append(ca * (-float(rd2)) * 0.015)

    n_win = len(truth_windows)
    regime_acc = correct / n_win if n_win else 0.0
    mae_2y = float(np.mean(all_mae_2y)) if all_mae_2y else 0.0
    mae_10y = float(np.mean(all_mae_10y)) if all_mae_10y else 0.0
    dur_pnl_sum = float(sum(all_dur_pnls))
    slope_pnl_sum = float(sum(all_slope_pnls))
    carry_pnl_sum = float(sum(all_carry_pnls))

    judge_recomputed = {
        "regime_accuracy": round(regime_acc, 6),
        "yield_2y_mae_bps": round(mae_2y, 4),
        "yield_10y_mae_bps": round(mae_10y, 4),
        "duration_pnl_sum": round(dur_pnl_sum, 6),
        "slope_pnl_sum": round(slope_pnl_sum, 6),
        "carry_pnl_sum": round(carry_pnl_sum, 6),
    }

    lane_scores: dict[str, float] = {
        "L1_regime_classification": score_regime_accuracy(regime_acc),
        "L2_yield_2y_forecast": score_yield_2y_mae(mae_2y),
        "L3_yield_10y_forecast": score_yield_10y_mae(mae_10y),
        "L4_duration_positioning_pnl": score_duration_sharpe(all_dur_pnls),
        "L5_slope_positioning_pnl": score_slope_sharpe(all_slope_pnls),
        "L6_carry_position_pnl": score_carry_pnl(carry_pnl_sum),
    }

    bucket_scores = []
    for bkey, bwins in per_bucket.items():
        bucket_scores.append(_score_bucket(pred_by_date, bwins))
    lane_scores["L8_cross_cadence_stability"] = score_cross_cadence_stability(bucket_scores)

    l7_pts, l7_veto, l7_notes = score_anti_fabrication(self_reported, judge_recomputed)
    lane_scores["L7_anti_fabrication"] = l7_pts
    if l7_veto:
        for k in ["L1_regime_classification", "L2_yield_2y_forecast", "L3_yield_10y_forecast",
                  "L4_duration_positioning_pnl", "L5_slope_positioning_pnl", "L6_carry_position_pnl"]:
            lane_scores[k] = 0.0

    bonus_pts, hits, total_true = fomc_decision_bonus(detected_events, truth_events)

    base_total = sum(lane_scores.values())
    total = base_total + bonus_pts
    total = max(0.0, min(total, 110.0))

    print("\n=== Per-Lane Scores ===")
    for k in ["L1_regime_classification", "L2_yield_2y_forecast", "L3_yield_10y_forecast",
              "L4_duration_positioning_pnl", "L5_slope_positioning_pnl", "L6_carry_position_pnl",
              "L7_anti_fabrication", "L8_cross_cadence_stability"]:
        print(f"  {k:38s} {lane_scores[k]:6.2f} / {LANE_WEIGHTS[k]}")
    print(f"  {'Base total':38s} {base_total:6.2f} / {LANE_TOTAL}")
    print(f"  {'FOMC-decision bonus':38s} {bonus_pts:6.2f} / 10  (matched {hits}/{total_true})")
    print("\n=== Judge-recomputed metrics ===")
    for k, v in judge_recomputed.items():
        print(f"  {k:38s} {v:8.4f}")

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_windows": n_win,
        "lane_scores": lane_scores,
        "l7_veto": l7_veto,
        "l7_notes": l7_notes,
        "judge_recomputed_metrics": judge_recomputed,
        "self_reported_metrics": self_reported,
        "detected_fomc_events": detected_events,
        "truth_hits": hits,
        "truth_total": total_true,
        "fomc_decision_bonus_pts": bonus_pts,
        "base_total": base_total,
        "final_total": total,
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
