#!/usr/bin/env python3
"""Judge for cftc_futures_positioning_book.

Reads:
    --submission-dir  /home/workspace   (agent's cftc_positioning.py + positioning_results.json)
    --truth-csv       /workspace/scoring/cot_graded_truth.csv (judge-private)
    --output          /logs/verifier/reward.json

Writes:
    reward.json with per-lane breakdown + total + violations

Uses cftc_book_lib for scoring (identical to agent copy).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import cftc_book_lib as CL


def load_truth(csv_path):
    truth = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            key = (row["market_id"], row["week_ending"])
            truth[key] = {
                "direction": row["direction"],
                "magnitude_bucket": row["magnitude_bucket"],
                "crowding_regime": row["crowding_regime"],
                "extreme_positioning_flag": row["extreme_positioning_flag"].lower() == "true",
            }
    return truth


def load_submission(sub_dir):
    p = Path(sub_dir) / "positioning_results.json"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def score(submission, truth, fomc_cpi_dates):
    violations = []
    if not submission:
        return {
            "score": 0.0,
            "violations": ["missing_positioning_results_json"],
            "per_lane": {},
        }

    # Flatten submission
    pred_dir_by_key = {}
    pred_mag_by_key = {}
    pred_reg_by_key = {}
    pred_flag_by_key = {}
    prob_by_week = {}

    for wk_block in submission.get("per_week", []):
        week = wk_block.get("week_ending")
        if not week:
            continue
        for mk in wk_block.get("per_market", []):
            mid = mk.get("market_id")
            if mid not in CL.MARKET_IDS:
                violations.append(f"unknown_market_id:{mid}")
                continue
            d = mk.get("commercial_net_direction")
            if d not in CL.VALID_DIRECTIONS:
                violations.append(f"invalid_direction:{mid}:{week}:{d}")
                continue
            m = mk.get("magnitude_bucket")
            r = mk.get("crowding_regime")
            f = bool(mk.get("extreme_positioning_flag", False))
            p = float(mk.get("direction_probability", 0.5))
            key = (mid, week)
            pred_dir_by_key[key] = d
            pred_mag_by_key[key] = m if m in CL.VALID_MAGNITUDES else None
            pred_reg_by_key[key] = r if r in CL.VALID_REGIMES else None
            pred_flag_by_key[key] = f
            prob_by_week.setdefault(week, {})[mid] = p

    # Align predictions to truth
    aligned_keys = [k for k in pred_dir_by_key if k in truth]

    # Empty-submission gate per FORGE.md Invariant 25 / RL2:
    # A submission with zero aligned predictions MUST score exactly 0.
    if len(aligned_keys) == 0:
        return {
            "score": 0.0,
            "violations": violations + ["empty_submission"],
            "aligned_items": 0,
            "truth_items": len(truth),
            "per_lane": {"gate": "empty_submission_zero"},
            "self_reported": submission.get("self_reported_metrics", {}),
        }

    pred_dir = [pred_dir_by_key[k] for k in aligned_keys]
    true_dir = [truth[k]["direction"] for k in aligned_keys]
    pred_mag = [pred_mag_by_key[k] for k in aligned_keys]
    true_mag = [truth[k]["magnitude_bucket"] for k in aligned_keys]
    pred_reg = [pred_reg_by_key[k] for k in aligned_keys]
    true_reg = [truth[k]["crowding_regime"] for k in aligned_keys]
    pred_flags = [pred_flag_by_key[k] for k in aligned_keys]
    true_flags = [truth[k]["extreme_positioning_flag"] for k in aligned_keys]

    # true_dir_by_week for L5
    true_dir_by_week = {}
    for k, t in truth.items():
        true_dir_by_week.setdefault(k[1], {})[k[0]] = t["direction"]

    # Scores
    l1_acc, l1_pts = CL.score_L1(pred_dir, true_dir)
    l2_acc, l2_pts = CL.score_L2(pred_mag, true_mag)
    l3_acc, l3_pts = CL.score_L3(pred_reg, true_reg)
    l4_f1,  l4_pts = CL.score_L4(pred_flags, true_flags)
    l5_rho, l5_pts = CL.score_L5(prob_by_week, true_dir_by_week)
    l6_acc, l6_pts = CL.score_L6(pred_dir_by_key,
                                 {k: truth[k]["direction"] for k in truth},
                                 set(fomc_cpi_dates))
    l8_var, l8_pts = CL.score_L8(pred_dir_by_key,
                                 {k: truth[k]["direction"] for k in truth})

    # L7 confidence calibration (Brier)
    per_item_conf = submission.get("per_item_confidence", {})
    l7_brier, l7_pts = CL.score_L7(per_item_conf, pred_dir_by_key,
                                    {k: truth[k]["direction"] for k in truth})

    total = l1_pts + l2_pts + l3_pts + l4_pts + l5_pts + l6_pts + l7_pts + l8_pts

    return {
        "score": round(total, 4),
        "violations": violations,
        "aligned_items": len(aligned_keys),
        "truth_items": len(truth),
        "per_lane": {
            "L1_commercial_direction": {"acc": round(l1_acc, 4), "pts": round(l1_pts, 4)},
            "L2_magnitude_bucket":     {"acc": round(l2_acc, 4), "pts": round(l2_pts, 4)},
            "L3_crowding_regime":      {"acc": round(l3_acc, 4), "pts": round(l3_pts, 4)},
            "L4_extreme_flag":         {"f1":  round(l4_f1,  4), "pts": round(l4_pts, 4)},
            "L5_rank_correlation":     {"rho": round(l5_rho, 4), "pts": round(l5_pts, 4)},
            "L6_rate_regime_adaptive": {"acc": round(l6_acc, 4) if l6_acc else None, "pts": round(l6_pts, 4)},
            "L7_confidence_calibration": {"brier": round(l7_brier, 6) if l7_brier is not None else None, "pts": round(l7_pts, 4)},
            "L8_cross_quarter_stability": {"variance": round(l8_var, 6), "pts": round(l8_pts, 4)},
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission-dir", required=True)
    ap.add_argument("--truth-csv", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--calendar-csv", default=None,
                    help="optional; if omitted, tries submission-dir/attachments/macro_calendar.csv")
    args = ap.parse_args()

    truth = load_truth(args.truth_csv)
    submission = load_submission(args.submission_dir)

    # FOMC + CPI dates
    cal_path = args.calendar_csv or (Path(args.submission_dir) / "attachments" / "macro_calendar.csv")
    fomc_cpi = []
    if Path(cal_path).exists():
        with open(cal_path) as f:
            for row in csv.DictReader(f):
                fomc_cpi.append(row["date"])
    # Expand to nearby COT Tuesdays (within 5 business days = within 7 calendar days)
    # For simplicity: match to any week_ending within 3 days of an event date.
    from datetime import date, timedelta
    fomc_cpi_dates = set()
    for k in truth:
        wk = k[1]
        try:
            y, m, d = int(wk[:4]), int(wk[5:7]), int(wk[8:10])
            wk_date = date(y, m, d)
            for ev in fomc_cpi:
                y2, m2, d2 = int(ev[:4]), int(ev[5:7]), int(ev[8:10])
                ev_date = date(y2, m2, d2)
                if abs((wk_date - ev_date).days) <= 5:
                    fomc_cpi_dates.add(wk)
                    break
        except Exception:
            pass

    result = score(submission, truth, fomc_cpi_dates)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Score: {result['score']} / 100")
    print(json.dumps(result["per_lane"], indent=2))


if __name__ == "__main__":
    main()
