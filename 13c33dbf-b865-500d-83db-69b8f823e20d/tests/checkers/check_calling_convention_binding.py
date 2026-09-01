# forge-canary: FORGE-CANARY-837861982023138C90B2C0024F036FE0
from __future__ import annotations

import pathlib

import isa
import verifier_lib

CHECKER_ID = "C_M2_calling_convention_binding"

BUILTIN_CATEGORY = "calls"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    live = verifier_lib.live_abi()
    digest = live["calling_convention_digest"]
    report = verifier_lib.report_of(workspace)
    if not report:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "report_unparseable")
    if report.get("calling_convention_digest") != digest:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reported_calling_convention_digest_diverges_from_live_registry",
            {"claimed": report.get("calling_convention_digest"), "live": digest},
        )
    holdout = verifier_lib.holdout_measure(workspace)
    if not holdout.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, holdout.get("error") or "holdout_recompute_failed")

    if not any(row["passed"] for row in holdout["graded"]["rows"]):
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "compiler_produces_no_passing_program",
            {"raw_total": holdout["raw_total"]},
        )

    bodies = verifier_lib.live_intrinsics()["by_isa_revision"]
    linked = 0
    for program in verifier_lib.holdout_programs():
        if program["category"] != BUILTIN_CATEGORY:
            continue
        row = holdout["graded"]["by_name"][program["name"]]
        if not row["passed"]:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "linked_intrinsic_call_diverges_under_live_calling_convention",
                {
                    "program": program["name"],
                    "verdict": row["verdict"],
                    "first_divergence": row.get("first_divergence"),
                    "calling_convention_id": live["calling_convention_id"],
                },
            )
        image = holdout["compiled"]["images"][program["name"]]
        table = bodies[program["isa_revision_id"]]["intrinsics"]
        reached = False
        for entry in table:
            address = isa.contains_body(image, entry["body"])
            if address >= 0 and address in row.get("call_targets", []):
                reached = True
                break
        if not reached:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "linked_intrinsic_body_absent_or_never_called",
                {"program": program["name"], "calling_convention_id": live["calling_convention_id"]},
            )
        linked += 1
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "calling_convention_bound_to_live_registry",
        {"calling_convention_id": live["calling_convention_id"], "programs_linked": linked},
    )
