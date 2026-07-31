#!/usr/bin/env python3
"""
eval_script.py — judge-side per-window scoring runner.

Reads test_windows.json, invokes /home/workspace/curve_positioning.py --backtest
per window, loads that window's positioning_results.json, recomputes NAV / DV01
/ turnover from raw positions for anti-fabrication, calls score.py per window,
aggregates with cross-window stability penalty and regime-shift bonus.

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
from score import (score_window, cross_window_stability_score, regime_shift_bonus,
                   LANE_TOTAL, LANE_WEIGHTS)

WORKSPACE = Path("/home/workspace")
SCORING = WORKSPACE / "scoring"
AGENT_SCRIPT = WORKSPACE / "curve_positioning.py"
STATE_JSON = WORKSPACE / "reference_state.json"

PER_WINDOW_TIMEOUT_SEC = 300
DV01_BUDGET = 1000.0
COST_CAPITAL = 100_000.0


def _load_test_windows() -> list[dict[str, Any]]:
    p = WORKSPACE / "test_windows.json"
    if not p.exists():
        p = SCORING / "test_windows.json"
    return json.loads(p.read_text())["windows"]


def _load_true_regime_events() -> list[dict[str, Any]]:
    p = WORKSPACE / "true_regime_events.json"
    if not p.exists():
        p = SCORING / "true_regime_events.json"
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("events", [])


def _load_test_curve() -> pd.DataFrame:
    p = WORKSPACE / "treasury_curve_test.csv"
    if not p.exists():
        p = SCORING / "treasury_curve_test.csv"
    df = pd.read_csv(p)
    df["Date"] = pd.to_datetime(df["Date"])
    for c in ["1 Mo", "2 Mo", "3 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("Date").reset_index(drop=True)


def _invoke_agent_backtest(window_start: str, window_end: str,
                           window_id: int) -> tuple[bool, str, dict[str, Any] | None]:
    out_path = WORKSPACE / f"positioning_results_w{window_id}.json"
    if not AGENT_SCRIPT.exists():
        return False, f"agent script not found at {AGENT_SCRIPT}", None
    cmd = [
        sys.executable, str(AGENT_SCRIPT),
        "--backtest",
        f"--window-start={window_start}",
        f"--window-end={window_end}",
        f"--workspace={WORKSPACE}",
        f"--state-in={STATE_JSON}",
        f"--out={out_path}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=PER_WINDOW_TIMEOUT_SEC)
        if r.returncode != 0:
            fallback = WORKSPACE / "positioning_results.json"
            if fallback.exists() and not out_path.exists():
                out_path = fallback
            else:
                return False, f"agent returncode={r.returncode}: {r.stderr[-500:]}", None
        if not out_path.exists():
            fallback = WORKSPACE / "positioning_results.json"
            if fallback.exists():
                out_path = fallback
            else:
                return False, "positioning_results.json not produced", None
        d = json.loads(out_path.read_text())
        return True, "ok", d
    except subprocess.TimeoutExpired:
        return False, "agent timeout", None
    except Exception as e:
        return False, f"agent invocation failed: {e}", None


def _recompute_window_metrics(window_result: dict[str, Any],
                              curve_test: pd.DataFrame) -> tuple[dict[str, float], str | None]:
    positions = window_result.get("daily_positions", [])
    if not positions:
        return {}, "no positions"

    ws = window_result.get("window_start")
    we = window_result.get("window_end")
    curve_w = curve_test[(curve_test["Date"] >= pd.to_datetime(ws)) & (curve_test["Date"] <= pd.to_datetime(we))].sort_values("Date").reset_index(drop=True)
    if len(curve_w) < 2:
        return {}, "insufficient curve rows"

    dates_pos = [pd.to_datetime(p["date"]) for p in positions]
    dv01_by_day = {p["date"]: p.get("dv01_by_tenor", {}) for p in positions}

    curve_w = curve_w.set_index("Date")
    y2y = curve_w["2 Yr"].astype(float)
    y5y = curve_w["5 Yr"].astype(float)
    y10y = curve_w["10 Yr"].astype(float)
    y30y = curve_w["30 Yr"].astype(float)
    d2y = y2y.diff().dropna()
    d5y = y5y.diff().dropna()
    d10y = y10y.diff().dropna()
    d30y = y30y.diff().dropna()

    daily_pnl = []
    prev_dv01 = None
    turnover_sum = 0.0
    correct_direction = 0
    total_direction = 0
    dur_realized_vs_target = []
    convex_pnl_signs = []

    for i, date in enumerate(d10y.index):
        prev_pos_date = dates_pos[i].strftime("%Y-%m-%d") if i < len(dates_pos) else None
        if prev_pos_date is None or prev_pos_date not in dv01_by_day:
            continue
        dv01 = dv01_by_day[prev_pos_date]
        pnl = -(float(dv01.get("2Y", 0)) * float(d2y.get(date, 0)) * 100
                + float(dv01.get("5Y", 0)) * float(d5y.get(date, 0)) * 100
                + float(dv01.get("10Y", 0)) * float(d10y.get(date, 0)) * 100
                + float(dv01.get("30Y", 0)) * float(d30y.get(date, 0)) * 100)
        pnl += DV01_BUDGET * 0.02 / 252
        daily_pnl.append(pnl)

        realized_spread_change = float(d10y.get(date, 0)) - float(d2y.get(date, 0))
        curve_bet = float(dv01.get("10Y", 0)) - float(dv01.get("2Y", 0))
        if abs(realized_spread_change) > 0.005 and abs(curve_bet) > 5:
            total_direction += 1
            if realized_spread_change * curve_bet < 0:
                correct_direction += 1

        realized_dur = (float(dv01.get("2Y", 0)) * 2 + float(dv01.get("5Y", 0)) * 5
                        + float(dv01.get("10Y", 0)) * 10 + float(dv01.get("30Y", 0)) * 30) / max(DV01_BUDGET, 1e-9)
        target_dur = 5.5
        dur_realized_vs_target.append(realized_dur - target_dur)

        conv_pnl = float(dv01.get("5Y", 0)) * (float(d2y.get(date, 0)) + float(d10y.get(date, 0)) - 2 * float(d5y.get(date, 0)))
        convex_pnl_signs.append(np.sign(conv_pnl))

        if prev_dv01 is not None:
            turnover_sum += sum(abs(float(dv01.get(k, 0)) - float(prev_dv01.get(k, 0)))
                                for k in ["2Y", "5Y", "10Y", "30Y"])
        prev_dv01 = dv01

    if not daily_pnl:
        return {}, "no PnL"

    arr = np.array(daily_pnl)
    rets = arr / COST_CAPITAL
    mean_r = float(np.mean(rets))
    std_r = float(np.std(rets)) + 1e-9
    sharpe = mean_r / std_r * np.sqrt(252)
    nav = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(nav)
    dd = float(np.min((nav - peak) / peak)) if len(peak) else 0.0
    max_dd = float(-dd)
    hit_rate = correct_direction / total_direction if total_direction > 0 else 0.5
    dur_rmse = float(np.sqrt(np.mean(np.array(dur_realized_vs_target) ** 2))) if dur_realized_vs_target else 0.15
    convex_sign_mean = float(np.mean(convex_pnl_signs)) if convex_pnl_signs else 0.0

    n_days = len(daily_pnl)
    years = max(n_days / 252, 0.05)
    turnover_annualized = turnover_sum / max(DV01_BUDGET, 1e-9) / (2 * years)

    return {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "hit_rate_flatten_steepen": hit_rate,
        "duration_precision_rmse": dur_rmse,
        "convexity_capture_pnl": float(np.sum(convex_pnl_signs)),
        "convexity_capture_pnl_sign": convex_sign_mean,
        "turnover_annualized": turnover_annualized,
        "n_trading_days": n_days,
    }, None


def _detected_regime_events_from_windows(all_results: list[dict[str, Any]]) -> list[str]:
    detected = []
    for wr in all_results:
        for rh in wr.get("rebalance_history", []):
            if rh.get("trigger") == "regime_change":
                detected.append(rh.get("date"))
    return sorted(set([d for d in detected if d]))


def main():
    print("=" * 70)
    print(f"eval_script.py started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    windows = _load_test_windows()
    true_events = _load_true_regime_events()
    curve_test = _load_test_curve()
    print(f"Loaded {len(windows)} test windows, {len(true_events)} true regime events, {len(curve_test)} test curve rows")

    per_window_scoring = []
    per_window_l1_scores = []
    all_results = []
    infra_failures = 0

    for w in windows:
        wid = w["window_id"]
        ws = w["window_start"]
        we = w["window_end"]
        print(f"\n--- window {wid} [{ws} -> {we}] ---")
        ok, msg, wr = _invoke_agent_backtest(ws, we, wid)
        if not ok:
            print(f"  FAIL: {msg}")
            per_window_scoring.append({
                "window_start": ws, "window_end": we,
                "lanes": {k: 0.0 for k in LANE_WEIGHTS if k != "L8_cross_window_stability"},
                "sub_total": 0.0, "l7_veto": True,
                "l7_notes": [msg], "error": msg,
            })
            per_window_l1_scores.append(0.0)
            infra_failures += 1
            continue
        assert wr is not None
        recomputed, rerr = _recompute_window_metrics(wr, curve_test)
        if rerr:
            print(f"  recompute WARN: {rerr}")
            recomputed = {}
        ws_score = score_window(wr, recomputed)
        per_window_scoring.append(ws_score)
        per_window_l1_scores.append(ws_score["lanes"]["L1_risk_adjusted_return"])
        all_results.append(wr)
        print(f"  sharpe={recomputed.get('sharpe', 0):.3f}, dd={recomputed.get('max_drawdown', 0):.3f}, "
              f"hit={recomputed.get('hit_rate_flatten_steepen', 0):.2f}, sub_total={ws_score['sub_total']:.2f}, "
              f"L7_veto={ws_score['l7_veto']}")

    print("\n" + "=" * 70)
    print("Aggregating...")
    lane_totals = {k: 0.0 for k in LANE_WEIGHTS if k != "L8_cross_window_stability"}
    for pw in per_window_scoring:
        for k, v in pw["lanes"].items():
            lane_totals[k] += v
    n_windows = max(len(per_window_scoring), 1)
    lane_averages = {k: v / n_windows for k, v in lane_totals.items()}

    l8 = cross_window_stability_score(per_window_l1_scores)

    detected_regime_dates = _detected_regime_events_from_windows(all_results)
    bonus, hits, total_evts = regime_shift_bonus(detected_regime_dates, true_events, tolerance_days=3)
    print(f"detected regime events: {len(detected_regime_dates)}; matched {hits}/{total_evts} true events; bonus={bonus:.2f}")

    base_total = sum(lane_averages.values()) + l8

    print(f"\n=== Per-Lane Averages Across {n_windows} Windows ===")
    for k, v in lane_averages.items():
        print(f"  {k:35s} {v:6.2f} / {LANE_WEIGHTS[k]}")
    print(f"  {'L8_cross_window_stability':35s} {l8:6.2f} / {LANE_WEIGHTS['L8_cross_window_stability']}")
    print(f"  {'Base total':35s} {base_total:6.2f} / {LANE_TOTAL}")
    print(f"  {'Regime-shift bonus':35s} {bonus:6.2f} / 10")

    total = base_total + bonus
    total = max(0.0, min(total, 110.0))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_windows": n_windows,
        "n_infra_failures": infra_failures,
        "lane_averages": lane_averages,
        "l8_cross_window_stability": l8,
        "regime_shift_bonus": bonus,
        "detected_regime_events": len(detected_regime_dates),
        "true_regime_events_matched": hits,
        "true_regime_events_total": total_evts,
        "base_total": base_total,
        "final_total": total,
        "per_window_scoring": per_window_scoring,
    }
    report_path = WORKSPACE / "score_report.json"
    try:
        report_path.write_text(json.dumps(report, indent=2, default=float))
        print(f"\nScore report written to {report_path}")
    except Exception as e:
        print(f"WARN could not write score_report.json: {e}")

    print(f"\nFinal total score: {total:.2f} / 110")
    print(f"TOTAL_SCORE {total:.2f}")


if __name__ == "__main__":
    main()
