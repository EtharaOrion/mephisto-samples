# forge-canary: FORGE-CANARY-8881AD83FBBDBD62B88DCA22928690C5
from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C3_budget_invariant"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    manifest = verifier_lib.live_manifest()
    per_instance = manifest["per_instance_budget_seconds"]
    sweep_budget = manifest["sweep_budget_seconds"]
    expected_records = manifest["public_instance_count"]

    declared = verifier_lib.declared_recompute(workspace)
    if not declared.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, declared.get("error") or "declared_recompute_failed",
            declared.get("detail") or {},
        )
    if len(declared["rows"]) != expected_records:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "placement_bundle_record_count_diverges_from_live_sweep_size",
            {"records": len(declared["rows"]), "live_sweep_instance_count": expected_records},
        )

    declared_total = 0.0
    for entry in declared["rows"]:
        seconds = entry["row"].get("solve_seconds")
        if not isinstance(seconds, (int, float)):
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "solve_seconds_missing",
                {"instance_id": entry["instance"]["instance_id"]},
            )
        if float(seconds) > per_instance:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "per_instance_time_budget_exceeded",
                {
                    "instance_id": entry["instance"]["instance_id"],
                    "solve_seconds": float(seconds),
                    "per_instance_budget_seconds": per_instance,
                },
            )
        declared_total += float(seconds)
    if declared_total > sweep_budget:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "sweep_wall_clock_budget_exceeded",
            {"total_seconds": declared_total, "sweep_budget_seconds": sweep_budget},
        )

    hidden = verifier_lib.hidden_sweep(workspace)
    if not hidden.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, hidden.get("error") or "hidden_sweep_failed")
    for record in hidden["records"]:
        if record["solve_seconds"] > per_instance:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "per_instance_time_budget_exceeded",
                {
                    "instance_id": record["instance_id"],
                    "solve_seconds": record["solve_seconds"],
                    "per_instance_budget_seconds": per_instance,
                },
            )
    if hidden["total_seconds"] > sweep_budget:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "sweep_wall_clock_budget_exceeded",
            {"total_seconds": hidden["total_seconds"], "sweep_budget_seconds": sweep_budget},
        )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "budget_invariant_held",
        {
            "declared_total_seconds": declared_total,
            "hidden_total_seconds": hidden["total_seconds"],
            "per_instance_budget_seconds": per_instance,
            "sweep_budget_seconds": sweep_budget,
            "records": len(declared["rows"]),
        },
    )
