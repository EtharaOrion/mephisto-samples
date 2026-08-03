#!/usr/bin/env python3
"""
eval_script.py — judge-side scoring runner for sec_fundamental_momentum_calibration.

======================================================================
task_id:      sec_fundamental_momentum_calibration
bundle_uuid:  5cb28005-2b9a-5520-b4f8-de58beb5640d
authored:     2026-07-31 (FORGE Phase 2)
framework:    B (reference-anchored projector, PKW-FAMILIES §3)
contract SHA: 103f591fb359bcbba17d91ec4c2bf702cd88d83c67dacffc3de99670a9e5ac6f
boundary:     JUDGE-ONLY orchestrator. Reads scorer_manifest.json, loads the
              submitted momentum_results.json from --submission-dir, invokes
              fundamental_momentum_reference (imported from ../../solution/)
              on --input-dir to compute the ground truth, runs score.py per-
              lane functions, emits a JSON report + TOTAL_SCORE <N> on stdout
              for the Harbor scorer_manifest regex parser.

CLI:
  python3 eval_script.py \
      --submission-dir <dir containing momentum_results.json> \
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
    score_l2_surprise_direction,
    score_l3_extreme_f1,
    score_l4_revenue_ic,
    score_l5_margin_direction,
    score_l6_positioning_sharpe,
    score_l7_anti_fabrication,
    score_l8_cross_quarter_stability,
    score_earnings_cycle_bonus,
)

# ============================================================================
# JUDGE-ONLY GRADER SALT + PERTURBATION LAYER (Phase 2b Hybrid Option D)
# ============================================================================
# The constant GRADER_SALT and the derive_realized_truth() layer below live
# ONLY inside this file (the judge orchestrator). They are NEVER shipped into
# the agent's work image and NEVER referenced from any agent-visible surface
# (train/, test/, README.md, solution/*, scorer_manifest.json). Their purpose
# is Phase 2b calibration: they break the L2 / L3 / L6 identity artifacts
# that surfaced in the Phase 2 emulation (reference-solver-graded-against-
# itself scored MISCALIBRATED HIGH at 91.00/110 vs target band [65, 78]).
#
# All perturbation is deterministic per (cik, period) via sha256(cik|period|
# GRADER_SALT). No wall-clock, no os.urandom, no process-id, no dict ordering
# assumptions — two independent runs produce byte-identical score reports
# (verified in seed/build/sec_fundamental_momentum_calibration/
# phase2_emulation_report.md § Phase 2b Recalibration).
# ============================================================================
GRADER_SALT = "SFM_2026_07_31_GRADER_CALIBRATION_SALT"
PERTURBATION_P_FLIP = 0.22
PERTURBATION_JITTER_SCALE = 0.025
PERTURBATION_SIGMA_PRICE = 0.055


def _perturb_seed(cik: int, period: str) -> int:
    payload = f"{cik}|{period}|{GRADER_SALT}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def derive_realized_truth(
    reference_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Judge-side hybrid perturbation on the reference-solver output.

    Returns (truth_general, truth_pnl):
      - truth_general (L1/L2/L3/L4/L5/L8): surprise_direction flipped to a
        random other label with probability PERTURBATION_P_FLIP; in_top_decile
        and in_bottom_decile flags jittered per-row (drop-true and add-false
        Bernoullis calibrated so extreme-set membership shifts by ~PERTURBATION_
        JITTER_SCALE, breaking the identity match). price_response_20d_proxy is
        LEFT UNTOUCHED here because L1 already scores realistically (IC 0.228,
        45.6% of max) with no identity artifact to break.
      - truth_pnl (L6): price_response_20d_proxy shocked by Gaussian noise
        N(0, PERTURBATION_SIGMA_PRICE), compressing the reference's
        unrealistic Phase-2 annualized Sharpe of 12.7 into a Novy-Marx-2013 /
        Fama-French-2015 realistic pro-Sharpe range.

    Determinism: one random.Random per (cik, period), seeded from a stable
    sha256 of `f"{cik}|{period}|{GRADER_SALT}"`. Draw order fixed within the
    loop, so identical inputs produce byte-identical outputs.
    """
    general: list[dict[str, Any]] = []
    pnl: list[dict[str, Any]] = []
    for r in reference_rows:
        cik = int(r["cik"])
        period = r["period"]
        rng = random.Random(_perturb_seed(cik, period))
        row_g = dict(r)
        row_p = dict(r)
        d = row_g.get("surprise_direction")
        if d in ("beat", "in_line", "miss") and rng.random() < PERTURBATION_P_FLIP:
            others = [x for x in ("beat", "in_line", "miss") if x != d]
            row_g["surprise_direction"] = others[0] if rng.random() < 0.5 else others[1]
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
        general.append(row_g)
        pr = row_p.get("price_response_20d_proxy")
        if pr is not None and isinstance(pr, (int, float)) and math.isfinite(pr):
            row_p["price_response_20d_proxy"] = float(pr) + rng.gauss(0.0, PERTURBATION_SIGMA_PRICE)
        pnl.append(row_p)
    return general, pnl


def _load_reference_module(here: Path) -> Any:
    candidates = [
        here.parent.parent / "solution" / "fundamental_momentum_reference.py",
        here / "fundamental_momentum_reference.py",
    ]
    for path in candidates:
        if path.exists():
            spec = importlib.util.spec_from_file_location(
                "fundamental_momentum_reference", str(path)
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError(
        f"fundamental_momentum_reference.py not found in any of: {[str(p) for p in candidates]}"
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


def _compute_revenues_yoy(all_fundamentals: list[dict[str, Any]],
                          test_periods: set[str]) -> dict[tuple[str, int], float]:
    per_cik: dict[int, dict[str, dict[str, Any]]] = {}
    for r in all_fundamentals:
        per_cik.setdefault(int(r["cik"]), {})[r["period"]] = r
    result: dict[tuple[str, int], float] = {}
    for cik, periods in per_cik.items():
        for pk, r in periods.items():
            if pk not in test_periods:
                continue
            r_lag4 = periods.get(_q_offset(pk, 4))
            if r_lag4 is None:
                continue
            rev_now = r.get("Revenues")
            rev_prev = r_lag4.get("Revenues")
            if rev_now is None or rev_prev is None:
                continue
            denom = max(abs(float(rev_prev)), 1.0)
            result[(pk, cik)] = (float(rev_now) - float(rev_prev)) / denom
    return result


def _compute_margin_direction(all_fundamentals: list[dict[str, Any]],
                              test_periods: set[str],
                              flat_threshold: float = 0.005) -> dict[tuple[str, int], str]:
    per_cik: dict[int, dict[str, dict[str, Any]]] = {}
    for r in all_fundamentals:
        per_cik.setdefault(int(r["cik"]), {})[r["period"]] = r
    result: dict[tuple[str, int], str] = {}
    for cik, periods in per_cik.items():
        for pk, r in periods.items():
            if pk not in test_periods:
                continue
            r_lag4 = periods.get(_q_offset(pk, 4))
            if r_lag4 is None:
                continue
            op_now = r.get("OperatingIncomeLoss")
            op_prev = r_lag4.get("OperatingIncomeLoss")
            rev_now = r.get("Revenues")
            rev_prev = r_lag4.get("Revenues")
            if op_now is None or op_prev is None or rev_now is None or rev_prev is None:
                continue
            if rev_now == 0 or rev_prev == 0:
                continue
            m_now = float(op_now) / float(rev_now)
            m_prev = float(op_prev) / float(rev_prev)
            delta = m_now - m_prev
            if delta > flat_threshold:
                result[(pk, cik)] = "up"
            elif delta < -flat_threshold:
                result[(pk, cik)] = "down"
            else:
                result[(pk, cik)] = "flat"
    return result


def _compute_margin_recovery(all_fundamentals: list[dict[str, Any]]
                             ) -> dict[tuple[str, int], bool]:
    per_cik: dict[int, dict[str, dict[str, Any]]] = {}
    for r in all_fundamentals:
        per_cik.setdefault(int(r["cik"]), {})[r["period"]] = r
    recovery_periods = {"2025Q3", "2025Q4", "2026Q1"}
    bottom_periods = {"2024Q4", "2025Q1", "2025Q2"}
    result: dict[tuple[str, int], bool] = {}
    for cik, periods in per_cik.items():
        margins: dict[str, float] = {}
        for pk, r in periods.items():
            op = r.get("OperatingIncomeLoss")
            rev = r.get("Revenues")
            if op is None or rev is None or rev == 0:
                continue
            margins[pk] = float(op) / float(rev)
        if not margins:
            continue
        bottoms = [margins[pk] for pk in bottom_periods if pk in margins]
        recoveries = [margins[pk] for pk in recovery_periods if pk in margins]
        if not bottoms or not recoveries:
            continue
        min_bottom = min(bottoms)
        max_recovery = max(recoveries)
        is_recovery = max_recovery - min_bottom > 0.02
        for pk in ("2025Q3", "2025Q4", "2026Q1"):
            if pk in margins:
                result[(pk, cik)] = is_recovery
    return result


def _judge_recomputed_metrics(
    l1: dict, l2: dict, l3: dict, l4: dict, l5: dict,
) -> dict[str, float]:
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
        "L1_composite_score_rank_correlation_est": round(ic1, 6),
        "L2_earnings_surprise_direction_accuracy_est": round(acc2, 6),
        "L3_extreme_filer_detection_f1_est": round(f1_3, 6),
        "L4_revenue_growth_ranking_ic_est": round(ic4, 6),
        "L5_margin_expansion_direction_accuracy_est": round(acc5, 6),
    }


def run(submission_dir: Path, input_dir: Path, output: Path) -> dict[str, Any]:
    t0 = time.time()
    here = Path(__file__).resolve().parent

    sub_path = submission_dir / "momentum_results.json"
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

    train_fund = _read_jsonl(input_dir / "train" / "fundamentals.jsonl")
    test_fund = _read_jsonl(input_dir / "test" / "fundamentals.jsonl")
    all_fund = train_fund + test_fund
    test_periods = {r["period"] for r in test_fund}

    revenues_yoy = _compute_revenues_yoy(all_fund, test_periods)
    margin_direction = _compute_margin_direction(all_fund, test_periods)
    margin_recovery = _compute_margin_recovery(all_fund)

    l1 = score_l1_composite_ic(sub_rows, truth_general)
    l2 = score_l2_surprise_direction(sub_rows, truth_general)
    l3 = score_l3_extreme_f1(sub_rows, truth_general)
    l4 = score_l4_revenue_ic(sub_rows, truth_general, revenues_yoy)
    l5 = score_l5_margin_direction(sub_rows, margin_direction)
    l6 = score_l6_positioning_sharpe(sub_rows, truth_pnl)
    l2_raw = score_l2_surprise_direction(sub_rows, truth_rows)
    l3_raw = score_l3_extreme_f1(sub_rows, truth_rows)
    judge_recomp = _judge_recomputed_metrics(l1, l2_raw, l3_raw, l4, l5)
    l7 = score_l7_anti_fabrication(self_reported, judge_recomp)
    l8 = score_l8_cross_quarter_stability(sub_rows, truth_general,
                                          revenues_yoy, margin_direction)
    bonus = score_earnings_cycle_bonus(sub_rows, truth_general, margin_recovery)

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
    print(
        f"eval_script.py (sec_fundamental_momentum_calibration) elapsed "
        f"{agg['elapsed_sec']}s"
    )
    print("=" * 70)
    print(f"submission_rows={agg['submission_size']}  truth_rows={agg['truth_size']}")
    print("\n=== Per-lane scores ===")
    for lane in lane_scores:
        print(f"  {lane['lane']:42s}  {lane['sub_score']:7.3f} / {lane['max']:>5}   "
              f"{lane['reason']}")
    print(f"  {'free_padding':42s}  {agg['free_padding']:7.3f} / {agg['free_padding']:>5}")
    print(f"  {'BASE_TOTAL':42s}  {agg['base_total']:7.3f} / 100")
    print(f"  {bonus['lane']:42s}  {bonus['sub_score']:7.3f} / {bonus['max']:>5}   "
          f"{bonus['reason']}")
    print(f"\nFinal total score: {agg['grand_total']:.2f} / {GRAND_MAX}")
    print(f"TOTAL_SCORE {agg['grand_total']:.2f}")
    return agg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FORGE Phase 2 scoring orchestrator (sec_fundamental_momentum_calibration)",
    )
    parser.add_argument("--submission-dir", type=Path, required=True,
                        help="Directory containing the agent's momentum_results.json")
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Bundle directory containing train/ and test/ subdirs")
    parser.add_argument("--output", type=Path, required=True,
                        help="Per-lane score report JSON path")
    args = parser.parse_args()
    run(args.submission_dir, args.input_dir, args.output)


if __name__ == "__main__":
    main()
