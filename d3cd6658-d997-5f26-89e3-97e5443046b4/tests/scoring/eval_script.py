#!/usr/bin/env python3
"""
eval_script.py — judge-side scoring runner for sec_leverage_trajectory_projection_book.

Contract SHA: cb68e81c405253bb6aa8642eb0aad9d3b7e063f049bc5f9c45876b131793e3e5
Framework:    B (reference-anchored projector, PKW-FAMILIES §3)
Boundary:     JUDGE-ONLY orchestrator. Reads scorer_manifest.json, loads the
              submitted trajectory_results.json from --submission-dir, invokes
              leverage_trajectory_reference (imported from ../../solution/) on
              --input-dir to compute the ground truth, runs score.py per-lane
              functions, emits a JSON report + TOTAL_SCORE <N> on stdout for
              the Harbor scorer_manifest regex parser.

CLI:
  python3 eval_script.py \
      --submission-dir <dir containing trajectory_results.json> \
      --input-dir      <bundle dir containing train/ and test/> \
      --output         <path to per-lane score report JSON>
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import (
    LANE_WEIGHTS, BONUS_MAX, GRAND_MAX,
    aggregate,
    score_l1_composite_ic,
    score_l2_refi_direction,
    score_l3_extreme_f1,
    score_l4_delta_liab_ic,
    score_l5_coverage_direction,
    score_l6_positioning_sharpe,
    score_l7_anti_fabrication,
    score_l8_cross_quarter_stability,
    score_leverage_cycle_bonus,
)

# ============================================================================
# JUDGE-ONLY GRADER SALT + PERTURBATION LAYER (T6 Phase 2b Hybrid Option D)
# ============================================================================
# GRADER_SALT + derive_realized_truth() live ONLY in this file. Never shipped
# into the agent's work image. Never referenced from train/, test/, README.md,
# solution/*, or scorer_manifest.json. Purpose: preempt T6's Phase 2 identity-
# scoring MISCALIBRATED HIGH (91.00/110 out-of-band) by breaking L2/L3/L6
# identity artifacts.
#
# All perturbation is deterministic per (cik, period) via sha256(cik|period|
# GRADER_SALT). No wall-clock, no os.urandom, no dict ordering assumptions.
# Two independent runs produce byte-identical score reports.
# ============================================================================
GRADER_SALT = "SLT_2026_07_31_GRADER_CALIBRATION_SALT"
PERTURBATION_P_FLIP = 0.28
PERTURBATION_JITTER_SCALE = 0.045
PERTURBATION_SIGMA_PRICE = 0.11
PERTURBATION_SIGMA_PRICE_L1 = 0.05


def _perturb_seed(cik: int, period: str) -> int:
    payload = f"{cik}|{period}|{GRADER_SALT}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def derive_realized_truth(
    reference_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Judge-side hybrid perturbation on the reference-solver output.

    Returns (truth_general, truth_pnl):
      - truth_general (L1/L2/L3/L4/L5/L8): refi_direction flipped with prob
        PERTURBATION_P_FLIP; extreme-decile flags jittered by PERTURBATION_
        JITTER_SCALE; price_response_20d_proxy gets MODERATE Gaussian shock
        N(0, PERTURBATION_SIGMA_PRICE_L1) to break the composite-to-proxy
        identity that exists in T7 (composite drives proxy directly; T6 had
        no such coupling because its composite and proxy were computed from
        different signals). Distinct from T6 which left truth_general price
        untouched.
      - truth_pnl (L6): price_response_20d_proxy shocked more strongly by
        Gaussian noise N(0, PERTURBATION_SIGMA_PRICE), compressing unrealistic
        reference Sharpe into the Baker-Wurgler 2002 JF realistic 2-5 range.

    Determinism: one random.Random per (cik, period), seeded from
    sha256(cik|period|GRADER_SALT). Draw order fixed within the loop.
    """
    general: list[dict[str, Any]] = []
    pnl: list[dict[str, Any]] = []
    for r in reference_rows:
        cik = int(r["cik"])
        period = r["period"]
        rng = random.Random(_perturb_seed(cik, period))
        row_g = dict(r)
        row_p = dict(r)
        d = row_g.get("refi_direction")
        if d in ("risk_up", "neutral", "risk_down") and rng.random() < PERTURBATION_P_FLIP:
            others = [x for x in ("risk_up", "neutral", "risk_down") if x != d]
            row_g["refi_direction"] = others[0] if rng.random() < 0.5 else others[1]
        if bool(row_g.get("in_top_decile")):
            if rng.random() < PERTURBATION_JITTER_SCALE * 8.0:
                row_g["in_top_decile"] = False
        else:
            if rng.random() < PERTURBATION_JITTER_SCALE * 0.9:
                row_g["in_top_decile"] = True
        if bool(row_g.get("in_bottom_decile")):
            if rng.random() < PERTURBATION_JITTER_SCALE * 8.0:
                row_g["in_bottom_decile"] = False
        else:
            if rng.random() < PERTURBATION_JITTER_SCALE * 0.9:
                row_g["in_bottom_decile"] = True
        pr = row_g.get("price_response_20d_proxy")
        if pr is not None and isinstance(pr, (int, float)) and math.isfinite(pr):
            row_g["price_response_20d_proxy"] = float(pr) + rng.gauss(0.0, PERTURBATION_SIGMA_PRICE_L1)
        general.append(row_g)
        pr_p = row_p.get("price_response_20d_proxy")
        if pr_p is not None and isinstance(pr_p, (int, float)) and math.isfinite(pr_p):
            row_p["price_response_20d_proxy"] = float(pr_p) + rng.gauss(0.0, PERTURBATION_SIGMA_PRICE)
        pnl.append(row_p)
    return general, pnl


def _load_reference_module(here: Path) -> Any:
    candidates = [
        here.parent.parent / "solution" / "leverage_trajectory_reference.py",
        here / "leverage_trajectory_reference.py",
    ]
    for path in candidates:
        if path.exists():
            spec = importlib.util.spec_from_file_location(
                "leverage_trajectory_reference", str(path)
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError(
        f"leverage_trajectory_reference.py not found in any of: {[str(p) for p in candidates]}"
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _q_offset(pk: str, n: int) -> str:
    y = int(pk[:4])
    q = int(pk[-1])
    idx = y * 4 + (q - 1) - n
    return f"{idx // 4}Q{(idx % 4) + 1}"


def _compute_delta_liab_yoy(all_xbrl: list[dict[str, Any]],
                            test_periods: set[str]) -> dict[tuple[str, int], float]:
    per_cik: dict[int, dict[str, dict[str, Any]]] = {}
    for r in all_xbrl:
        per_cik.setdefault(int(r["cik"]), {})[r["period"]] = r
    result: dict[tuple[str, int], float] = {}
    for cik, periods in per_cik.items():
        for pk, r in periods.items():
            if pk not in test_periods:
                continue
            r_lag4 = periods.get(_q_offset(pk, 4))
            if r_lag4 is None:
                continue
            liab_now = r.get("Liabilities"); assets_now = r.get("Assets")
            liab_prev = r_lag4.get("Liabilities"); assets_prev = r_lag4.get("Assets")
            if liab_now is None or assets_now is None or liab_prev is None or assets_prev is None:
                continue
            if assets_now == 0 or assets_prev == 0:
                continue
            la_now = float(liab_now) / float(assets_now)
            la_prev = float(liab_prev) / float(assets_prev)
            result[(pk, cik)] = la_now - la_prev
    return result


def _compute_coverage_direction_truth(all_xbrl: list[dict[str, Any]],
                                      test_periods: set[str],
                                      up_delta: float = 0.10,
                                      down_delta: float = -0.10) -> dict[tuple[str, int], str]:
    per_cik: dict[int, dict[str, dict[str, Any]]] = {}
    for r in all_xbrl:
        per_cik.setdefault(int(r["cik"]), {})[r["period"]] = r
    result: dict[tuple[str, int], str] = {}
    for cik, periods in per_cik.items():
        for pk, r in periods.items():
            if pk not in test_periods:
                continue
            r_lag4 = periods.get(_q_offset(pk, 4))
            if r_lag4 is None:
                continue
            op_now = r.get("OperatingIncomeLoss"); ie_now = r.get("InterestExpense")
            op_prev = r_lag4.get("OperatingIncomeLoss"); ie_prev = r_lag4.get("InterestExpense")
            if op_now is None or ie_now is None or op_prev is None or ie_prev is None:
                continue
            if ie_now == 0 or ie_prev == 0:
                continue
            cov_now = float(op_now) / float(ie_now)
            cov_prev = float(op_prev) / float(ie_prev)
            delta = cov_now - cov_prev
            if delta > up_delta:
                result[(pk, cik)] = "up"
            elif delta < down_delta:
                result[(pk, cik)] = "down"
            else:
                result[(pk, cik)] = "flat"
    return result


def _compute_refi_cycle_turn_truth(all_xbrl: list[dict[str, Any]],
                                   test_periods: set[str]) -> dict[tuple[str, int], bool]:
    """Filers whose Liabilities/Assets peaked in CY2024Q4-CY2025Q2 and receded
    CY2025Q3-CY2026Q1 (post-rate-hike refi-cycle-turn beneficiaries)."""
    per_cik: dict[int, dict[str, dict[str, Any]]] = {}
    for r in all_xbrl:
        per_cik.setdefault(int(r["cik"]), {})[r["period"]] = r
    peak_periods = {"2024Q4", "2025Q1", "2025Q2"}
    recede_periods = {"2025Q3", "2025Q4", "2026Q1"}
    result: dict[tuple[str, int], bool] = {}
    for cik, periods in per_cik.items():
        ratios: dict[str, float] = {}
        for pk, r in periods.items():
            liab = r.get("Liabilities"); assets = r.get("Assets")
            if liab is None or assets is None or assets == 0:
                continue
            ratios[pk] = float(liab) / float(assets)
        if not ratios:
            continue
        peaks = [ratios[pk] for pk in peak_periods if pk in ratios]
        receds = [ratios[pk] for pk in recede_periods if pk in ratios]
        if not peaks or not receds:
            continue
        max_peak = max(peaks)
        min_recede = min(receds)
        is_turn = max_peak - min_recede > 0.02
        for pk in ("2025Q3", "2025Q4", "2026Q1"):
            if pk in ratios and pk in test_periods:
                result[(pk, cik)] = is_turn
    return result


def _judge_recomputed_metrics(l1: dict, l2: dict, l3: dict, l4: dict, l5: dict) -> dict[str, float]:
    def _reason_num(reason: str, marker: str) -> float:
        try:
            idx = reason.find(marker)
            if idx < 0:
                return 0.0
            rest = reason[idx + len(marker):]
            n = 0
            while n < len(rest) and rest[n] in "-.0123456789":
                n += 1
            return float(rest[:n]) if n else 0.0
        except (ValueError, IndexError):
            return 0.0

    ic1 = _reason_num(l1["reason"], "IC = ")
    acc2 = _reason_num(l2["reason"], "accuracy = ")
    f1_3 = _reason_num(l3["reason"], "F1 = ")
    ic4 = _reason_num(l4["reason"], "IC = ")
    acc5 = _reason_num(l5["reason"], "accuracy = ")
    return {
        "L1_composite_trajectory_rank_correlation_est": round(ic1, 6),
        "L2_refinancing_risk_direction_accuracy_est": round(acc2, 6),
        "L3_extreme_mover_detection_f1_est": round(f1_3, 6),
        "L4_delta_liabilities_growth_ranking_ic_est": round(ic4, 6),
        "L5_interest_coverage_direction_accuracy_est": round(acc5, 6),
    }


def run(submission_dir: Path, input_dir: Path, output: Path) -> dict[str, Any]:
    t0 = time.time()
    here = Path(__file__).resolve().parent

    sub_path = submission_dir / "trajectory_results.json"
    if not sub_path.exists():
        report = {
            "error": f"missing submission at {sub_path}",
            "grand_total": 0.0,
            "grand_max": GRAND_MAX,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(f"FAIL: missing submission at {sub_path}")
        print(f"TOTAL_SCORE 0.00")
        return report
    submission = json.loads(sub_path.read_text())
    sub_rows: list[dict[str, Any]] = submission.get("per_filer_quarter", [])
    self_reported = submission.get("self_reported_metrics", {})

    ref_module = _load_reference_module(here)
    truth = ref_module.run_reference(input_dir)
    truth_rows: list[dict[str, Any]] = truth["per_filer_quarter"]
    truth_general, truth_pnl = derive_realized_truth(truth_rows)

    train_xbrl = _read_jsonl(input_dir / "train" / "xbrl.jsonl")
    test_xbrl = _read_jsonl(input_dir / "test" / "xbrl.jsonl")
    all_xbrl = train_xbrl + test_xbrl
    test_periods = {r["period"] for r in test_xbrl}

    delta_liab_yoy = _compute_delta_liab_yoy(all_xbrl, test_periods)
    coverage_dir = _compute_coverage_direction_truth(all_xbrl, test_periods)
    refi_cycle_turn = _compute_refi_cycle_turn_truth(all_xbrl, test_periods)

    l1 = score_l1_composite_ic(sub_rows, truth_general)
    l2 = score_l2_refi_direction(sub_rows, truth_general)
    l3 = score_l3_extreme_f1(sub_rows, truth_general)
    l4 = score_l4_delta_liab_ic(sub_rows, delta_liab_yoy)
    l5 = score_l5_coverage_direction(sub_rows, coverage_dir)
    l6 = score_l6_positioning_sharpe(sub_rows, truth_pnl)
    l2_raw = score_l2_refi_direction(sub_rows, truth_rows)
    l3_raw = score_l3_extreme_f1(sub_rows, truth_rows)
    judge_recomp = _judge_recomputed_metrics(l1, l2_raw, l3_raw, l4, l5)
    l7 = score_l7_anti_fabrication(self_reported, judge_recomp)
    l8 = score_l8_cross_quarter_stability(sub_rows, truth_general,
                                          delta_liab_yoy, coverage_dir)
    bonus = score_leverage_cycle_bonus(sub_rows, truth_general, refi_cycle_turn)

    lane_scores = [l1, l2, l3, l4, l5, l6, l7, l8]
    agg = aggregate(lane_scores, bonus)
    agg["judge_recomputed_metrics"] = judge_recomp
    agg["self_reported_metrics"] = self_reported
    agg["submission_size"] = len(sub_rows)
    agg["truth_size"] = len(truth_rows)
    agg["elapsed_sec"] = round(time.time() - t0, 3)
    agg["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(agg, sort_keys=True, indent=2, default=float) + "\n")

    print("=" * 70)
    print(f"eval_script.py (sec_leverage_trajectory_projection_book) elapsed {agg['elapsed_sec']}s")
    print("=" * 70)
    print(f"submission_rows={agg['submission_size']}  truth_rows={agg['truth_size']}")
    print("\n=== Per-lane scores ===")
    for lane in lane_scores:
        print(f"  {lane['lane']:42s}  {lane['sub_score']:7.3f} / {lane['max']:>5}   {lane['reason']}")
    print(f"  {'free_padding':42s}  {agg['free_padding']:7.3f} / {agg['free_padding']:>5}")
    print(f"  {'BASE_TOTAL':42s}  {agg['base_total']:7.3f} / 100")
    print(f"  {bonus['lane']:42s}  {bonus['sub_score']:7.3f} / {bonus['max']:>5}   {bonus['reason']}")
    print(f"\nFinal total score: {agg['grand_total']:.2f} / {GRAND_MAX}")
    print(f"TOTAL_SCORE {agg['grand_total']:.2f}")
    return agg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FORGE Phase 2 scoring orchestrator (sec_leverage_trajectory_projection_book)",
    )
    parser.add_argument("--submission-dir", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.submission_dir, args.input_dir, args.output)


if __name__ == "__main__":
    main()
