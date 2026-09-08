"""Judge-side scorer for edgebench.p3gamma_sec_opmargin_expansion_book.

Byte-identical copy lives in the judge image at /home/workspace/scoring/score.py.

VERIFIER OPACITY (PKW-FAMILIES.md F-A M5):

STRUCTURED_RESULT_JSON on stderr CARRIES:
  task_id, graded_window, submission_valid, structural_reasons, n_eligible_universe,
  submission_rows_parsed, parse_problems, per-lane {score, max} scalars L1..L5,
  total_score, published lane_point_constants + k_constants, submitted_rank_stats
  (min, max, mean, stddev) FROM SUBMITTED VECTOR ALONE only if L1 passed.

STRUCTURED_RESULT_JSON DOES NOT CARRY:
  per-cik hit list, ground-truth cik, realized sector_relative_delta_opmargin_pp
  for any cik, realized_opmargin_change_rank for any cik, per-cik sibling ranks,
  top-K numerator per lane, decile bin values, spearman rho scalar, mean-per-decile
  array, per-cik partial-correlation contribution, or any per-cik bit of any kind.

Env gate P3GAMMASOM_JUDGE_AUDIT='1' enables an 'audit' block in the emitted JSON
for CONFORMANCE TESTS ONLY. Production Harbor eval_cmd MUST NOT set this variable.

Grep verification (Phase 2 conformance):
  grep -E "(hidden_opmargin|sector_relative_delta_opmargin|realized_opmargin_change_rank|hidden_sibling_ranks)" score.py
should show ZERO occurrences OUTSIDE the audit-block conditional or the HIDDEN_*_PATH
constants and load calls guarded by that conditional.

STDOUT emits a single line 'TOTAL_SCORE <val>' for test.sh to parse into reward.txt.
"""
from __future__ import annotations

import csv
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import p3gamma_lib as PB  # noqa: E402

TASK_ID = "p3gamma_sec_opmargin_expansion_book"
GRADED_WINDOW = "sec_xbrl_opincomeloss_usd_cy2026q1_frame_snapshot_2026_08_08"

JUDGE_ROOT = os.environ.get("JUDGE_ROOT", str(HERE))
CANDIDATE_ROOT = os.environ.get("CANDIDATE_ROOT", "/home/workspace")
P3GAMMASOM_JUDGE_AUDIT = os.environ.get("P3GAMMASOM_JUDGE_AUDIT", "") == "1"

HIDDEN_REALIZED_PATH = os.path.join(JUDGE_ROOT, "data", "hidden_opmargin_change_realized.csv")
HIDDEN_SIBLING_PATH = os.path.join(JUDGE_ROOT, "data", "hidden_sibling_ranks.csv")
SUBMISSION_PATH = os.path.join(CANDIDATE_ROOT, "submission", "opmargin_change_ranks.csv")


def _base_result(reject_reason: str = "") -> Dict[str, Any]:
    return {
        "task_id": TASK_ID,
        "graded_window": GRADED_WINDOW,
        "n_eligible_universe": PB.N_UNIVERSE,
        "submission_rows_parsed": 0,
        "parse_problems": [],
        "submission_valid": False,
        "reject_reason": reject_reason,
        "structural_reasons": [],
        "lanes": PB.zero_lanes(),
        "lane_max": PB.lane_max_dict(),
        "total_score": 0.0,
        "lane_point_constants": {
            "L1": PB.LANE_L1_POINTS,
            "L2": PB.LANE_L2_POINTS,
            "L3": PB.LANE_L3_POINTS,
            "L4": PB.LANE_L4_POINTS,
            "L5": PB.LANE_L5_POINTS,
            "total_max": PB.TOTAL_POINTS,
        },
        "k_constants": {
            "top_k": PB.TOP_K,
            "n_deciles": PB.N_DECILES,
            "n_sibling_measures": PB.N_SIBLING_MEASURES,
        },
    }


def reject(reason: str, parse_problems: List[str], structural_reasons: List[str], rows_parsed: int) -> Dict[str, Any]:
    result = _base_result(reject_reason=reason)
    result["parse_problems"] = parse_problems
    result["structural_reasons"] = structural_reasons
    result["submission_rows_parsed"] = rows_parsed
    return result


def emit(result: Dict[str, Any], code: int = 0) -> int:
    sys.stderr.write("STRUCTURED_RESULT_JSON " + json.dumps(result, separators=(",", ":")) + "\n")
    sys.stderr.flush()
    sys.stdout.write(f"TOTAL_SCORE {result['total_score']:.6f}\n")
    sys.stdout.flush()
    return code


def _read_submission_text() -> str:
    try:
        with open(SUBMISSION_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def _submitted_rank_stats(rows: List) -> Dict[str, float]:
    if not rows:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "stddev": 0.0}
    ranks = [float(r) for _, r in rows]
    return {
        "min": min(ranks),
        "max": max(ranks),
        "mean": statistics.fmean(ranks),
        "stddev": statistics.pstdev(ranks) if len(ranks) > 1 else 0.0,
    }


def main() -> int:
    try:
        realized = PB.load_realized_ranks(HIDDEN_REALIZED_PATH)
    except (FileNotFoundError, OSError, csv.Error, ValueError) as e:
        return emit(reject(f"judge_hidden_realized_load_failed:{type(e).__name__}", [], [], 0), code=2)

    if len(realized) != PB.N_UNIVERSE:
        return emit(reject(
            f"judge_hidden_realized_row_count_mismatch:{len(realized)}!={PB.N_UNIVERSE}",
            [], [], 0,
        ), code=2)

    try:
        sibling = PB.load_sibling_ranks(HIDDEN_SIBLING_PATH)
    except (FileNotFoundError, OSError, csv.Error, ValueError) as e:
        return emit(reject(f"judge_hidden_sibling_load_failed:{type(e).__name__}", [], [], 0), code=2)

    if len(sibling) != PB.N_UNIVERSE:
        return emit(reject(
            f"judge_hidden_sibling_row_count_mismatch:{len(sibling)}!={PB.N_UNIVERSE}",
            [], [], 0,
        ), code=2)

    text = _read_submission_text()
    if not text:
        return emit(reject("submission_missing_or_empty", [], [], 0))

    rows, header_problems = PB.parse_submission_csv(text)
    parse_problems = list(header_problems)
    universe = set(realized.keys())
    passed, structural_reasons = PB.structural_check(rows, header_problems, universe)
    if not passed:
        return emit(reject("structural_failure", parse_problems, structural_reasons, len(rows)))

    lane_scores = PB.score_all(rows, realized, sibling)
    result = _base_result()
    result["submission_valid"] = True
    result["submission_rows_parsed"] = len(rows)
    result["parse_problems"] = parse_problems
    result["lanes"] = {k: v for k, v in lane_scores.items() if k != "total"}
    result["total_score"] = lane_scores["total"]
    result["submitted_rank_stats"] = _submitted_rank_stats(rows)

    if P3GAMMASOM_JUDGE_AUDIT:
        aligned = [(realized[c], r) for c, r in rows if c in realized]
        if len(aligned) >= 2:
            xs = [a for a, _ in aligned]
            ys = [b for _, b in aligned]
            rho = PB.spearman(xs, ys)
        else:
            rho = 0.0
        agent_top_k = set(PB.top_k_ids(rows, PB.TOP_K))
        realized_pairs = [(c, r) for c, r in realized.items()]
        realized_top_k = set(PB.top_k_ids(realized_pairs, PB.TOP_K))
        top_k_hit = len(agent_top_k & realized_top_k)
        per_sibling: Dict[str, float] = {}
        first_entry = next(iter(sibling.values())) if sibling else {}
        sibling_cols = sorted(k for k in first_entry.keys() if k != PB.L5_CONTROL_COLUMN)
        for col in sibling_cols:
            per_sibling[col] = PB._score_one_sibling_partial(rows, col, sibling)
        result["audit"] = {
            "spearman_rho": rho,
            "top_k_numerator": top_k_hit,
            "top_k_denominator": PB.TOP_K,
            "per_sibling_partial_spearman": per_sibling,
        }

    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
