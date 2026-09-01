# forge-canary: FORGE-CANARY-C4CDF9EBB33965998B2D609A6897A25C
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C3_budget_invariant"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    policy = verifier_lib.live_kernel_policy()
    per_kernel = float(policy["per_kernel_budget_seconds"])
    sweep_budget = float(policy["sweep_budget_seconds"])

    sweep = verifier_lib.graded_sweep(workspace)
    if not sweep.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, sweep.get("error") or "graded_sweep_failed")

    for record in sweep["kernels"]:
        if record["schedule_seconds"] > per_kernel:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "budget_overrun",
                {
                    "kernel_id": record["kernel_id"],
                    "modelled_seconds": record["schedule_seconds"],
                    "per_kernel_budget_seconds": per_kernel,
                    "scope": "per_kernel",
                },
            )
    if sweep["total_schedule_seconds"] > sweep_budget:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "budget_overrun",
            {
                "modelled_seconds": sweep["total_schedule_seconds"],
                "sweep_budget_seconds": sweep_budget,
                "scope": "sweep",
            },
        )

    public = verifier_lib.public_sweep(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_sweep_failed")
    submitted = verifier_lib.submitted_records(workspace)
    if not submitted.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, submitted.get("error") or "schedule_bundle_unreadable")

    for record in submitted["records"]:
        mirror = public["by_kernel"].get(record.get("kernel_id"))
        if mirror is None:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_kernel_absent_from_public_family",
                {"kernel_id": record.get("kernel_id")},
            )
        declared = record.get("schedule_seconds")
        if not isinstance(declared, (int, float)):
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "declared_schedule_seconds_missing", {"kernel_id": record.get("kernel_id")}
            )
        if float(declared) > per_kernel:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "budget_overrun",
                {
                    "kernel_id": record.get("kernel_id"),
                    "declared_seconds": float(declared),
                    "per_kernel_budget_seconds": per_kernel,
                    "scope": "declared",
                },
            )
        if abs(float(declared) - mirror["schedule_seconds"]) > registry.SECONDS_TOLERANCE:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_schedule_seconds_diverges_from_the_cost_model",
                {
                    "kernel_id": record.get("kernel_id"),
                    "declared": float(declared),
                    "modelled": mirror["schedule_seconds"],
                },
            )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "per_kernel_and_sweep_budgets_hold",
        {
            "per_kernel_budget_seconds": per_kernel,
            "sweep_budget_seconds": sweep_budget,
            "worst_kernel_seconds": max(record["schedule_seconds"] for record in sweep["kernels"]),
            "total_sweep_seconds": sweep["total_schedule_seconds"],
        },
    )
