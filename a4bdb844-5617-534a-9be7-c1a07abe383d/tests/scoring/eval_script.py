#!/usr/bin/env python3
"""
eval_script.py - judge-side per-print scoring runner for
cpi_nowcast_positioning_book. Invokes the agent's --backtest against the
hidden 2025 monthly panel, parses nowcast_results.json, per-print recomputes
YoY MAE + positioning-book PnL + directional beat rate, calls score.py for
per-lane composition, aggregates with cross-series stability + Fed-pivot
bonus.

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
    score_series_mae, score_positioning_pnl, score_directional_beat,
    score_anti_fabrication, score_cross_series_stability, fed_pivot_bonus,
    LANE_WEIGHTS, LANE_TOTAL, SERIES_LANE_MAP,
)

WORKSPACE = Path("/home/workspace")
SCORING = WORKSPACE / "scoring"
AGENT_SCRIPT = WORKSPACE / "cpi_nowcast_book.py"
STATE_JSON = WORKSPACE / "reference_state.json"

BACKTEST_TIMEOUT_SEC = 2700
CPI_SERIES = ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE"]


def _find(name: str) -> Path:
    for base in (WORKSPACE, SCORING):
        p = base / name
        if p.exists():
            return p
    return WORKSPACE / name


def _load_test_prints() -> list[dict]:
    p = _find("test_prints.json")
    return json.loads(p.read_text()).get("prints", [])


def _load_true_fed_events() -> list[dict]:
    p = _find("true_fed_pivot_events.json")
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("events", [])


def _invoke_agent_backtest() -> tuple[bool, str, dict | None]:
    output_path = WORKSPACE / "nowcast_results.json"
    if not AGENT_SCRIPT.exists():
        return False, f"agent script not found at {AGENT_SCRIPT}", None
    data_p = _find("cpi_test.csv")
    macro_p = _find("macro_test.csv")
    rates_p = _find("rates_test.csv")
    prints_p = _find("test_prints.json")
    prior_cpi_p = _find("cpi_prior_year.csv")
    prior_macro_p = _find("macro_prior_year.csv")
    prior_rates_p = _find("rates_prior_year.csv")
    cmd = [
        sys.executable, str(AGENT_SCRIPT),
        "--backtest",
        f"--data={data_p}",
        f"--macro={macro_p}",
        f"--rates={rates_p}",
        f"--prints={prints_p}",
        f"--state={STATE_JSON}",
        f"--output={output_path}",
    ]
    if prior_cpi_p.exists():
        cmd.append(f"--prior-cpi={prior_cpi_p}")
    if prior_macro_p.exists():
        cmd.append(f"--prior-macro={prior_macro_p}")
    if prior_rates_p.exists():
        cmd.append(f"--prior-rates={prior_rates_p}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=BACKTEST_TIMEOUT_SEC)
        if r.returncode != 0:
            return False, f"agent returncode={r.returncode}: {r.stderr[-1500:]}", None
        if not output_path.exists():
            return False, "nowcast_results.json not produced", None
        d = json.loads(output_path.read_text())
        return True, "ok", d
    except subprocess.TimeoutExpired:
        return False, "agent timeout", None
    except Exception as e:
        return False, f"agent invocation failed: {e}", None


def main() -> None:
    print("=" * 70)
    print(f"eval_script.py started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    test_prints = _load_test_prints()
    true_events = _load_true_fed_events()
    print(f"Loaded {len(test_prints)} hidden test prints, {len(true_events)} true Fed pivots")

    ok, msg, br = _invoke_agent_backtest()
    if not ok:
        print(f"FAIL: {msg}")
        print(f"TOTAL_SCORE 0.00")
        try:
            (WORKSPACE / "score_report.json").write_text(json.dumps(
                {"error": msg, "final_total": 0.0}, indent=2))
        except Exception:
            pass
        sys.exit(1)
    assert br is not None

    pred_by_key: dict[tuple[str, str], dict] = {}
    for p in br.get("prints", []):
        key = (str(p.get("series")), str(p.get("ref_month")))
        pred_by_key[key] = p
    detected_events = br.get("detected_fed_pivot_events", [])
    self_reported = br.get("self_reported_metrics", {})

    errs_by_series: dict[str, list[float]] = {s: [] for s in CPI_SERIES}
    beats = 0
    total_scored = 0
    pnl_per_print: list[float] = []
    per_print_records: list[dict] = []

    for pr in test_prints:
        series = pr["series"]
        ref_month = pr["ref_month"]
        realized_yoy = pr.get("realized_yoy_pct")
        key = (series, ref_month)
        agent_pred = pred_by_key.get(key)
        if agent_pred is None or realized_yoy is None:
            per_print_records.append({
                "series": series, "ref_month": ref_month,
                "missing_prediction": agent_pred is None,
                "missing_realized": realized_yoy is None,
            })
            continue
        pred_yoy = float(agent_pred.get("predicted_yoy_pct", 0.0))
        if not np.isfinite(pred_yoy):
            pred_yoy = 0.0
        err = abs(pred_yoy - float(realized_yoy))
        errs_by_series[series].append(err)

        naive_yoy = agent_pred.get("naive_year_ago_carry_yoy_pct")
        if naive_yoy is None or not np.isfinite(float(naive_yoy)):
            naive_yoy = pr.get("realized_yoy_pct", 0.0)
        naive_err = abs(float(naive_yoy) - float(realized_yoy))
        if err < naive_err:
            beats += 1
        total_scored += 1

        if series == "CPIAUCSL":
            surprise = float(realized_yoy) - float(naive_yoy)
            book = agent_pred.get("positioning_book") or {}
            d2 = float(book.get("duration_2y") or 0.0)
            d10 = float(book.get("duration_10y") or 0.0)
            be10 = float(book.get("breakeven_10y") or 0.0)
            week_reaction = -0.05 * surprise
            pnl = (d10 * week_reaction - be10 * week_reaction * 0.6
                   + d2 * week_reaction * 0.7)
            pnl_per_print.append(float(pnl))

        per_print_records.append({
            "series": series, "ref_month": ref_month,
            "predicted_yoy_pct": pred_yoy,
            "realized_yoy_pct": realized_yoy,
            "err_pp": round(err, 6),
            "naive_err_pp": round(naive_err, 6),
        })

    judge_recomputed = {
        "headline_cpi_mae_pp": float(np.mean(errs_by_series["CPIAUCSL"])) if errs_by_series["CPIAUCSL"] else 0.0,
        "core_cpi_mae_pp": float(np.mean(errs_by_series["CPILFESL"])) if errs_by_series["CPILFESL"] else 0.0,
        "pce_mae_pp": float(np.mean(errs_by_series["PCEPI"])) if errs_by_series["PCEPI"] else 0.0,
        "core_pce_mae_pp": float(np.mean(errs_by_series["PCEPILFE"])) if errs_by_series["PCEPILFE"] else 0.0,
        "positioning_pnl_sum": float(sum(pnl_per_print)),
        "directional_beat_consensus_rate": float(beats / total_scored) if total_scored else 0.0,
    }

    lane_scores: dict[str, float] = {}
    for series, lane_key in SERIES_LANE_MAP.items():
        lane_scores[lane_key] = score_series_mae(series, errs_by_series[series])
    lane_scores["L5_positioning_book_pnl"] = score_positioning_pnl(
        judge_recomputed["positioning_pnl_sum"], pnl_per_print)
    lane_scores["L6_directional_accuracy_vs_carry"] = score_directional_beat(
        judge_recomputed["directional_beat_consensus_rate"])
    l7_pts, l7_veto, l7_notes = score_anti_fabrication(self_reported, judge_recomputed)
    lane_scores["L7_anti_fabrication"] = l7_pts
    if l7_veto:
        lane_scores["L1_headline_cpi_nowcast_accuracy"] = 0.0
        lane_scores["L2_core_cpi_nowcast_accuracy"] = 0.0
    lane_scores["L8_cross_series_stability"] = score_cross_series_stability(lane_scores)

    bonus_pts, hits, total_true = fed_pivot_bonus(detected_events, true_events, tolerance_months=1)

    base_total = sum(lane_scores.values())
    total = base_total + bonus_pts
    total = max(0.0, min(total, 110.0))

    print(f"\n=== Per-Lane Scores ===")
    for k in ["L1_headline_cpi_nowcast_accuracy", "L2_core_cpi_nowcast_accuracy",
              "L3_pce_nowcast_accuracy", "L4_core_pce_nowcast_accuracy",
              "L5_positioning_book_pnl", "L6_directional_accuracy_vs_carry",
              "L7_anti_fabrication", "L8_cross_series_stability"]:
        print(f"  {k:40s} {lane_scores[k]:6.2f} / {LANE_WEIGHTS[k]}")
    print(f"  {'Base total':40s} {base_total:6.2f} / {LANE_TOTAL}")
    print(f"  {'Fed-pivot bonus':40s} {bonus_pts:6.2f} / 10  (matched {hits}/{total_true} true events)")
    print(f"\n=== Judge-recomputed metrics ===")
    for k, v in judge_recomputed.items():
        print(f"  {k:40s} {v:8.4f}")

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_prints_scored": total_scored,
        "lane_scores": lane_scores,
        "l7_veto": l7_veto,
        "l7_notes": l7_notes,
        "judge_recomputed_metrics": judge_recomputed,
        "self_reported_metrics": self_reported,
        "detected_fed_events": detected_events,
        "true_fed_events_matched": hits,
        "true_fed_events_total": total_true,
        "fed_pivot_bonus_pts": bonus_pts,
        "base_total": base_total,
        "final_total": total,
        "per_print_sample": per_print_records[:50],
    }
    try:
        (WORKSPACE / "score_report.json").write_text(
            json.dumps(report, indent=2, default=float))
        print(f"\nScore report written to {WORKSPACE / 'score_report.json'}")
    except Exception as e:
        print(f"WARN could not write score_report.json: {e}")

    print(f"\nFinal total score: {total:.2f} / 110")
    print(f"TOTAL_SCORE {total:.2f}")


if __name__ == "__main__":
    main()
