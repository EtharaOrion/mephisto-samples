# forge-canary: FORGE-CANARY-1BB2B264DB7B36163B3AD778A3401A39
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M1_isa_extension_effect"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    live = verifier_lib.live_isa()
    live_id = live["isa_revision_id"]
    report = verifier_lib.report_of(workspace)
    if not report:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "report_unparseable")
    if report.get("isa_revision_id") != live_id:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reported_isa_revision_diverges_from_live_registry",
            {"claimed": report.get("isa_revision_id"), "live": live_id},
        )
    holdout = verifier_lib.holdout_measure(workspace)
    if not holdout.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, holdout.get("error") or "holdout_recompute_failed")

    carried = [
        row["name"]
        for row in holdout["graded"]["rows"]
        if row["category"] != "saturate" and row["isa_revision_id"] == registry.ISA_SAT and not row["passed"]
    ]
    if carried:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "existing_lowering_not_carried_to_extended_revision",
            {"programs": carried[:8], "isa_revision_id": live_id},
        )

    extended = [row for row in holdout["graded"]["rows"] if row["category"] == "saturate"]
    if not extended:
        return verifier_lib.result(
            CHECKER_ID, True, 1.0, "extension_not_yet_pinned", {"isa_revision_id": live_id}
        )
    failed = [row["name"] for row in extended if not row["passed"]]
    if failed:
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, "saturating_opcode_group_not_lowered", {"programs": failed[:8]}
        )
    submitted = sum(row["instructions"] for row in extended)
    baseline = sum(
        verifier_lib.holdout_measure(workspace)["baseline_graded"]["by_name"][row["name"]]["instructions"]
        for row in extended
    )
    achieved = baseline / submitted if submitted else 0.0
    if achieved < verifier_lib.M1_EFFECT_MARGIN:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "extension_effect_below_declared_margin",
            {"achieved": round(achieved, 6), "required": verifier_lib.M1_EFFECT_MARGIN},
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "extension_lowered_and_effect_measured",
        {"achieved": round(achieved, 6), "programs": len(extended), "isa_revision_id": live_id},
    )
