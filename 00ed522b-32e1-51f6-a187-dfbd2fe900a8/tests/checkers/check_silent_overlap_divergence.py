# forge-canary: FORGE-CANARY-8C9E0B8D2FBCC6E24B34F86E4C4C76B9
from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C6_silent_overlap_divergence"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    manifest = verifier_lib.live_manifest()
    graded = verifier_lib.graded_clearance()
    preview = manifest["preview_clearance_units"]

    declared = verifier_lib.declared_recompute(workspace)
    if not declared.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, declared.get("error") or "declared_recompute_failed",
            declared.get("detail") or {},
        )
    for entry in declared["rows"]:
        verdict = entry["verdict"]
        if not verdict["feasible"] and verdict["category"] == "clearance":
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                verdict["reason"],
                {
                    "instance_id": entry["instance"]["instance_id"],
                    "preview_clearance_units": preview,
                    **verdict["detail"],
                },
            )

    hidden = verifier_lib.hidden_sweep(workspace)
    if not hidden.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, hidden.get("error") or "hidden_sweep_failed")
    for record in hidden["records"]:
        verdict = record["verdict"]
        if not verdict["feasible"] and verdict["category"] == "clearance":
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                verdict["reason"],
                {
                    "instance_id": record["instance_id"],
                    "preview_clearance_units": preview,
                    **verdict["detail"],
                },
            )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "graded_clearance_satisfied",
        {
            "graded_clearance_units": graded,
            "preview_clearance_units": preview,
            "instances_checked": len(declared["rows"]) + len(hidden["records"]),
        },
    )
