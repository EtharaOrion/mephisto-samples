#!/usr/bin/env python3
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import (
    LANE_WEIGHTS, BONUS_MAX, GRAND_MAX,
    aggregate,
    score_l1_timing_rmse,
    score_l2_circuit_regime,
    score_l3_stall_detection,
    score_l4_case_type_ordering,
    score_l5_motion_count_regression,
    score_l6_disposition_timing_pnl,
    score_l7_anti_fabrication,
    score_l8_cross_month_stability,
    score_timing_calibration_bonus,
)

GRADER_SALT = "CAT_2026_08_01_GRADER_CALIBRATION_SALT"
PERTURBATION_SIGMA_DAYS = 120.0
PERTURBATION_P_FLIP_REGIME = 0.30
PERTURBATION_P_FLIP_STALL = 0.15
PERTURBATION_MOTION_SIGMA = 1.5


def _perturb_seed(case_id: str, cell: str) -> int:
    payload = f"{case_id}|{cell}|{GRADER_SALT}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _derive_perturbed_truth(base_true_days: dict[str, int],
                             base_true_regimes: dict[str, str],
                             base_true_stall: dict[str, bool],
                             base_true_motion: dict[str, float]
                             ) -> tuple[dict, dict, dict, dict]:
    perturbed_days: dict[str, int] = {}
    for cid, d in base_true_days.items():
        rng = random.Random(_perturb_seed(cid, "days"))
        perturbed_days[cid] = max(1, int(round(float(d) + rng.gauss(0.0, PERTURBATION_SIGMA_DAYS))))

    regime_options = ["low_complexity", "moderate_complexity", "elevated_complexity", "backlog_pressure"]
    perturbed_regimes: dict[str, str] = {}
    for k, r in base_true_regimes.items():
        rng = random.Random(_perturb_seed(k, "regime"))
        if rng.random() < PERTURBATION_P_FLIP_REGIME:
            others = [x for x in regime_options if x != r]
            perturbed_regimes[k] = others[rng.randrange(len(others))]
        else:
            perturbed_regimes[k] = r

    perturbed_stall: dict[str, bool] = {}
    for cid, s in base_true_stall.items():
        rng = random.Random(_perturb_seed(cid, "stall"))
        if rng.random() < PERTURBATION_P_FLIP_STALL:
            perturbed_stall[cid] = not s
        else:
            perturbed_stall[cid] = s

    perturbed_motion: dict[str, float] = {}
    for cid, m in base_true_motion.items():
        rng = random.Random(_perturb_seed(cid, "motion"))
        perturbed_motion[cid] = max(0.0, float(m) + rng.gauss(0.0, PERTURBATION_MOTION_SIGMA))

    return perturbed_days, perturbed_regimes, perturbed_stall, perturbed_motion


def _load_reference_module(here: Path):
    candidates = [
        here / "appellate_timing_reference.py",
        here.parent.parent / "solution" / "appellate_timing_reference.py",
    ]
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location("appellate_timing_reference", str(p))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise FileNotFoundError(f"appellate_timing_reference.py missing; searched: {[str(p) for p in candidates]}")


def _derive_base_truth(reference_output: dict, hidden_dir: Path) -> tuple[dict, dict, dict, dict, dict, set]:
    true_days_path = hidden_dir / "true_disposition_days.json"
    true_stall_path = hidden_dir / "true_stall_flags.json"
    true_regime_path = hidden_dir / "true_circuit_month_regime.json"
    true_motion_path = hidden_dir / "true_motion_counts.json"
    q2_ids_path = hidden_dir / "q2_2025_case_ids.json"

    if true_days_path.exists():
        base_true_days = {k: int(v) for k, v in json.loads(true_days_path.read_text()).items()}
    else:
        base_true_days = {p["case_id"]: int(p["predicted_days_to_disposition"])
                          for p in reference_output.get("per_case", [])}
    if true_stall_path.exists():
        base_true_stall = {k: bool(v) for k, v in json.loads(true_stall_path.read_text()).items()}
    else:
        base_true_stall = {p["case_id"]: bool(p["stall_flag"])
                           for p in reference_output.get("per_case", [])}
    if true_regime_path.exists():
        base_true_regimes = json.loads(true_regime_path.read_text())
    else:
        base_true_regimes = dict(reference_output.get("circuit_month_regime") or {})
    if true_motion_path.exists():
        base_true_motion = {k: float(v) for k, v in json.loads(true_motion_path.read_text()).items()}
    else:
        base_true_motion = {p["case_id"]: float(p["predicted_motion_count"])
                            for p in reference_output.get("per_case", [])}
    if q2_ids_path.exists():
        q2_ids = set(json.loads(q2_ids_path.read_text()))
    else:
        q2_ids = set()
        for p in reference_output.get("per_case", []):
            d = p.get("predicted_disposition_date") or ""
            if d.startswith("2025-04") or d.startswith("2025-05") or d.startswith("2025-06"):
                q2_ids.add(p["case_id"])
    return base_true_days, base_true_regimes, base_true_stall, base_true_motion, {}, q2_ids


def _judge_recomputed_metrics(l1, l2, l3, l4, l5, l6, l8) -> dict[str, float]:
    def _num(reason: str, marker: str) -> float:
        try:
            i = reason.find(marker)
            if i < 0:
                return 0.0
            rest = reason[i + len(marker):]
            n = 0
            while n < len(rest) and rest[n] in "-.0123456789":
                n += 1
            return float(rest[:n]) if n else 0.0
        except (ValueError, IndexError):
            return 0.0

    l1_ratio = _num(l1["reason"], "ratio = ")
    l1_est = max(0.0, min(1.0, 1.0 - (l1_ratio - 0.30) / 0.70))
    l6_sharpe = _num(l6["reason"], "Sharpe = ")
    return {
        "L1_timing_rmse_lane_est": round(l1_est, 6),
        "L2_circuit_regime_classification_est": round(_num(l2["reason"], "accuracy = "), 6),
        "L3_stall_detection_est": round(_num(l3["reason"], "F1 = "), 6),
        "L4_case_type_ordering_est": round(_num(l4["reason"], "mean_rho = "), 6),
        "L5_motion_count_regression_est": round(_num(l5["reason"], "R2 = "), 6),
        "L6_disposition_timing_pnl_est": round(l6_sharpe / 1.5, 6),
        "L8_cross_month_stability_est": round(_num(l8["reason"], "mean_norm="), 6),
    }


def run(submission_dir: Path, input_dir: Path, output: Path) -> dict:
    t0 = time.time()
    here = Path(__file__).resolve().parent
    hidden_dir = here

    sub_path = submission_dir / "timing_results.json"
    if not sub_path.exists():
        report = {"error": f"missing {sub_path}", "grand_total": 0.0, "grand_max": GRAND_MAX}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(f"FAIL: missing submission at {sub_path}")
        print("TOTAL_SCORE 0.00")
        return report
    submission = json.loads(sub_path.read_text())
    sub_rows = submission.get("per_case", [])
    sub_circuit_month = submission.get("circuit_month_regime", {}) or {}
    self_reported = submission.get("self_reported_metrics", {})

    ref_module = _load_reference_module(here)
    ref_output = ref_module.run_reference(input_dir)

    truth_dir_candidates = [input_dir, hidden_dir]
    truth_dir = next((d for d in truth_dir_candidates
                      if (d / "true_disposition_days.json").exists()), hidden_dir)
    base_days, base_regimes, base_stall, base_motion, _, q2_ids = _derive_base_truth(ref_output, truth_dir)
    p_days, p_regimes, p_stall, p_motion = _derive_perturbed_truth(
        base_days, base_regimes, base_stall, base_motion)

    l1 = score_l1_timing_rmse(sub_rows, p_days)
    l2 = score_l2_circuit_regime(sub_rows, sub_circuit_month, p_regimes)
    l3 = score_l3_stall_detection(sub_rows, p_stall)
    l4 = score_l4_case_type_ordering(sub_rows, p_days)
    l5 = score_l5_motion_count_regression(sub_rows, p_motion)
    l6 = score_l6_disposition_timing_pnl(sub_rows, p_days)
    l8 = score_l8_cross_month_stability(sub_rows, p_days)
    judge_recomp = _judge_recomputed_metrics(l1, l2, l3, l4, l5, l6, l8)
    l7 = score_l7_anti_fabrication(self_reported, judge_recomp)
    bonus = score_timing_calibration_bonus(sub_rows, p_days, q2_ids)

    lane_scores = [l1, l2, l3, l4, l5, l6, l7, l8]
    agg = aggregate(lane_scores, bonus)
    agg["judge_recomputed_metrics"] = judge_recomp
    agg["self_reported_metrics"] = self_reported
    agg["submission_size"] = len(sub_rows)
    agg["reference_size"] = len(ref_output.get("per_case", []))
    agg["elapsed_sec"] = round(time.time() - t0, 3)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(agg, sort_keys=True, indent=2, default=float) + "\n")

    print("=" * 70)
    print(f"eval_script.py (courtlistener_appellate_disposition_timing_calibration) elapsed {agg['elapsed_sec']}s")
    print("=" * 70)
    print(f"submission_rows={agg['submission_size']}  reference_rows={agg['reference_size']}")
    print("\n=== Per-lane scores ===")
    for lane in lane_scores:
        print(f"  {lane['lane']:40s}  {lane['sub_score']:7.3f} / {lane['max']:>5}   {lane['reason']}")
    print(f"  {'free_padding':40s}  {agg['free_padding']:7.3f} / {agg['free_padding']:>5}")
    print(f"  {'BASE_TOTAL':40s}  {agg['base_total']:7.3f} / 100")
    print(f"  {bonus['lane']:40s}  {bonus['sub_score']:7.3f} / {bonus['max']:>5}   {bonus['reason']}")
    print(f"\nFinal total score: {agg['grand_total']:.2f} / {GRAND_MAX}")
    print(f"TOTAL_SCORE {agg['grand_total']:.2f}")
    return agg


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--submission-dir", type=Path, required=True)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    run(args.submission_dir, args.input_dir, args.output)


if __name__ == "__main__":
    main()
