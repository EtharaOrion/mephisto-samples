# forge-canary: FORGE-CANARY-837861982023138C90B2C0024F036FE0
from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C1_suite_pass_value"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    holdout = verifier_lib.holdout_measure(workspace)
    if not holdout.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, holdout.get("error") or "holdout_recompute_failed")
    public = verifier_lib.public_measure(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_recompute_failed")

    report = verifier_lib.report_of(workspace)
    if not report:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "report_unparseable")
    claimed = report.get("weighted_pass_fraction")
    if not isinstance(claimed, (int, float)):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "report_weighted_pass_fraction_missing")
    if abs(float(claimed) - public["weighted_pass_fraction"]) > verifier_lib.FRACTION_TOLERANCE:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reported_weighted_pass_fraction_diverges_from_recompute",
            {"claimed": float(claimed), "recomputed_public_slice": public["weighted_pass_fraction"]},
        )
    if report.get("raw_passed") != public["raw_passed"] or report.get("raw_total") != public["raw_total"]:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reported_pass_counts_diverge_from_recompute",
            {
                "claimed": [report.get("raw_passed"), report.get("raw_total")],
                "recomputed_public_slice": [public["raw_passed"], public["raw_total"]],
            },
        )

    score = holdout["weighted_pass_fraction"]
    return verifier_lib.result(
        CHECKER_ID,
        score > 0.0,
        score,
        "weighted_pass_fraction_recomputed" if score > 0.0 else "no_held_out_program_passed",
        {
            "weighted_pass_fraction": score,
            "raw_passed": holdout["raw_passed"],
            "raw_total": holdout["raw_total"],
            "miscompile_count": holdout["miscompile_count"],
        },
    )
