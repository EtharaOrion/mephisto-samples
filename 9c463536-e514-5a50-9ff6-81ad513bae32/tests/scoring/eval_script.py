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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import (
    LANE_WEIGHTS, BONUS_MAX, GRAND_MAX,
    aggregate,
    score_l1_ladder_return,
    score_l2_repo_regime,
    score_l3_extreme_stress,
    score_l4_bill_supply_direction,
    score_l5_pd_position,
    score_l6_money_market_pnl,
    score_l7_anti_fabrication,
    score_l8_cross_week_stability,
    score_liquidity_cycle_bonus,
    BINS,
)

GRADER_SALT = "TLP_2026_08_01_GRADER_CALIBRATION_SALT"
PERTURBATION_P_FLIP_REGIME = 0.22
PERTURBATION_P_FLIP_STRESS = 0.06
PERTURBATION_JITTER_SUPPLY_DIR = 0.18
PERTURBATION_SIGMA_RETURNS = 0.00055


def _perturb_seed(date_str: str, cell: str) -> int:
    payload = f"{date_str}|{cell}|{GRADER_SALT}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _derive_perturbed_truth(reference_output: dict, base_true_returns: dict[str, dict],
                             base_true_regimes: dict[str, str],
                             base_true_stress: dict[str, bool],
                             base_true_supply_dir: dict[str, str]
                             ) -> tuple[dict, dict, dict, dict]:
    perturbed_returns: dict[str, dict] = {}
    for d, rets in base_true_returns.items():
        rng = random.Random(_perturb_seed(d, "returns"))
        row = {}
        for b, r in rets.items():
            if r is None:
                row[b] = None
            else:
                row[b] = float(r) + rng.gauss(0.0, PERTURBATION_SIGMA_RETURNS)
        perturbed_returns[d] = row

    perturbed_regimes: dict[str, str] = {}
    regime_options = ["deep_qt", "normal", "elevated_stress", "extreme_stress"]
    for d, r in base_true_regimes.items():
        rng = random.Random(_perturb_seed(d, "regime"))
        if rng.random() < PERTURBATION_P_FLIP_REGIME:
            others = [x for x in regime_options if x != r]
            perturbed_regimes[d] = others[rng.randrange(len(others))]
        else:
            perturbed_regimes[d] = r

    perturbed_stress: dict[str, bool] = {}
    for d, s in base_true_stress.items():
        rng = random.Random(_perturb_seed(d, "stress"))
        if rng.random() < PERTURBATION_P_FLIP_STRESS:
            perturbed_stress[d] = not s
        else:
            perturbed_stress[d] = s

    perturbed_supply: dict[str, str] = {}
    supply_options = ["up", "flat", "down"]
    for d, sd in base_true_supply_dir.items():
        rng = random.Random(_perturb_seed(d, "supply"))
        if rng.random() < PERTURBATION_JITTER_SUPPLY_DIR:
            others = [x for x in supply_options if x != sd]
            perturbed_supply[d] = others[rng.randrange(len(others))]
        else:
            perturbed_supply[d] = sd

    return perturbed_returns, perturbed_regimes, perturbed_stress, perturbed_supply


def _load_reference_module(here: Path):
    candidates = [
        here / "treasury_liquidity_reference.py",
        here.parent.parent / "solution" / "treasury_liquidity_reference.py",
    ]
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location("treasury_liquidity_reference", str(p))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise FileNotFoundError(f"treasury_liquidity_reference.py missing; searched: {[str(p) for p in candidates]}")


def _derive_base_truth(reference_output: dict, hidden_dir: Path) -> tuple[dict, dict, dict, dict]:
    true_returns_path = hidden_dir / "true_ladder_returns.json"
    if true_returns_path.exists():
        base_true_returns = json.loads(true_returns_path.read_text())
    else:
        base_true_returns = {}
    base_true_regimes: dict[str, str] = {}
    base_true_stress: dict[str, bool] = {}
    base_true_supply_dir: dict[str, str] = {}
    for e in reference_output.get("per_date", []):
        d = e["date"]
        base_true_regimes[d] = e["regime_label"]
        base_true_stress[d] = bool(e["extreme_stress_flag"])
        base_true_supply_dir[d] = e["supply_direction"]
    return base_true_returns, base_true_regimes, base_true_stress, base_true_supply_dir


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

    return {
        "L1_ladder_return_lane_est": round(_num(l1["reason"], "Sharpe (annualized) = ") / 1.5, 6),
        "L2_regime_classification_est": round(_num(l2["reason"], "accuracy = "), 6),
        "L3_extreme_stress_detection_est": round(_num(l3["reason"], "F1 = "), 6),
        "L4_supply_direction_est": round(_num(l4["reason"], "accuracy = "), 6),
        "L5_ny_fed_pd_position_change_est": round(_num(l5["reason"], "accuracy = "), 6),
        "L6_money_market_pnl_proxy_est": round(_num(l6["reason"], "MM Sharpe = ") / 1.5, 6),
        "L8_cross_week_stability_est": round(_num(l8["reason"], "mean_norm="), 6),
    }


def run(submission_dir: Path, input_dir: Path, output: Path) -> dict:
    t0 = time.time()
    here = Path(__file__).resolve().parent
    hidden_dir = here

    sub_path = submission_dir / "positioning_results.json"
    if not sub_path.exists():
        report = {"error": f"missing {sub_path}", "grand_total": 0.0, "grand_max": GRAND_MAX}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(f"FAIL: missing submission at {sub_path}")
        print(f"TOTAL_SCORE 0.00")
        return report
    submission = json.loads(sub_path.read_text())
    sub_rows = submission.get("per_date", [])
    self_reported = submission.get("self_reported_metrics", {})

    ref_module = _load_reference_module(here)
    ref_output = ref_module.run_reference(input_dir)

    base_returns, base_regimes, base_stress, base_supply = _derive_base_truth(ref_output, hidden_dir)
    if not base_returns:
        base_returns = {}
        for e in ref_output.get("per_date", []):
            d = e["date"]
            alloc = e.get("allocation") or {}
            base_returns[d] = {b: alloc.get(b, 0.0) * 0.0001 for b in BINS}

    p_returns, p_regimes, p_stress, p_supply = _derive_perturbed_truth(
        ref_output, base_returns, base_regimes, base_stress, base_supply)

    l1 = score_l1_ladder_return(sub_rows, p_returns)
    l2 = score_l2_repo_regime(sub_rows, p_regimes)
    l3 = score_l3_extreme_stress(sub_rows, p_stress)
    l4 = score_l4_bill_supply_direction(sub_rows, p_supply)
    true_pd_path = hidden_dir / "true_pd_position_direction.json"
    if true_pd_path.exists():
        true_pd = json.loads(true_pd_path.read_text())
    else:
        true_pd = {}
    l5 = score_l5_pd_position(sub_rows, true_pd)
    l6 = score_l6_money_market_pnl(sub_rows, p_returns)
    l8 = score_l8_cross_week_stability(sub_rows, p_returns)
    judge_recomp = _judge_recomputed_metrics(l1, l2, l3, l4, l5, l6, l8)
    l7 = score_l7_anti_fabrication(self_reported, judge_recomp)
    bonus = score_liquidity_cycle_bonus(sub_rows, p_stress, p_regimes)

    lane_scores = [l1, l2, l3, l4, l5, l6, l7, l8]
    agg = aggregate(lane_scores, bonus)
    agg["judge_recomputed_metrics"] = judge_recomp
    agg["self_reported_metrics"] = self_reported
    agg["submission_size"] = len(sub_rows)
    agg["reference_size"] = len(ref_output.get("per_date", []))
    agg["elapsed_sec"] = round(time.time() - t0, 3)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(agg, sort_keys=True, indent=2, default=float) + "\n")

    print("=" * 70)
    print(f"eval_script.py (treasury_liquidity_provisioning_book) elapsed {agg['elapsed_sec']}s")
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
