# forge-canary: FORGE-CANARY-5E66977EB92CE4DFF49566BA6EF73BDC
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M1_machine_model_identity"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    live = verifier_lib.live_registry()
    live_id = live["machine_model_id"]

    submitted = verifier_lib.submitted_records(workspace)
    if not submitted.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, submitted.get("error") or "schedule_bundle_unreadable")
    for record in submitted["records"]:
        if record.get("machine_model_id") != live_id:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_machine_model_stale",
                {
                    "kernel_id": record.get("kernel_id"),
                    "declared": record.get("machine_model_id"),
                    "live": live_id,
                },
            )

    sweep = verifier_lib.graded_sweep(workspace)
    if not sweep.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, sweep.get("error") or "graded_sweep_failed")

    baseline = verifier_lib.baseline_mean_ratio()
    required = baseline / registry.EFFECT_MARGIN
    achieved = sweep["mean_normalised_cycles"]
    if achieved > required:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "no_measurable_effect_on_the_live_machine_model",
            {
                "achieved_mean_normalised_cycles": achieved,
                "baseline_mean_normalised_cycles": baseline,
                "required_at_or_below": required,
                "machine_model_id": live_id,
                "issue_width": live["issue_width"],
            },
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "effect_measured_on_the_live_machine_model",
        {
            "achieved_mean_normalised_cycles": achieved,
            "baseline_mean_normalised_cycles": baseline,
            "machine_model_id": live_id,
            "issue_width": live["issue_width"],
            "port_capacity": live["port_capacity"],
        },
    )
