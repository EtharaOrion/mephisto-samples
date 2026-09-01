# forge-canary: FORGE-CANARY-5E66977EB92CE4DFF49566BA6EF73BDC
from __future__ import annotations

import pathlib

import machine
import verifier_lib

CHECKER_ID = "C1_cycle_count_value"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    sweep = verifier_lib.graded_sweep(workspace)
    if not sweep.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, sweep.get("error") or "graded_sweep_failed")

    for record in sweep["kernels"]:
        if record["semantic_ok"] is not True:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "semantic_divergence",
                {"kernel_id": record["kernel_id"], "detail": record["semantic_detail"]},
            )

    submitted = verifier_lib.submitted_records(workspace)
    if not submitted.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, submitted.get("error") or "schedule_bundle_unreadable")
    public = verifier_lib.public_sweep(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_sweep_failed")

    for record in submitted["records"]:
        kernel_id = record.get("kernel_id")
        mirror = public["by_kernel"].get(kernel_id)
        if mirror is None:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "declared_kernel_absent_from_public_family", {"kernel_id": kernel_id}
            )
        claimed = record.get("claimed_cycles")
        if not isinstance(claimed, int):
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "claimed_cycles_missing", {"kernel_id": kernel_id}
            )
        replayed = replay_cycles(record)
        if replayed is None:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "hazard_violation", {"kernel_id": kernel_id}
            )
        if claimed != replayed:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "claimed_cycle_count_diverges_from_replay",
                {"kernel_id": kernel_id, "claimed": claimed, "replayed": replayed},
            )

    ratio = sweep["mean_normalised_cycles"]
    score = verifier_lib.ratio_to_score(ratio)
    return verifier_lib.result(
        CHECKER_ID,
        score > 0.0,
        score,
        "mean_normalised_cycles_recomputed" if score > 0.0 else "mean_normalised_cycles_at_or_above_floor",
        {
            "mean_normalised_cycles": ratio,
            "graded_kernels": len(sweep["kernels"]),
            "machine_model_id": verifier_lib.live_registry()["machine_model_id"],
            "latency_table_digest": verifier_lib.live_registry()["latency_table_digest"],
        },
    )


def replay_cycles(record: dict):
    outcome = machine.replay(
        _kernel_of(record["kernel_id"]), verifier_lib.live_registry(), record.get("bundles")
    )
    if not outcome["structural_ok"] or outcome["violations"] or outcome["waw_violations"]:
        return None
    return outcome["cycles"]


def _kernel_of(kernel_id: str) -> dict:
    for kernel in verifier_lib.public_kernels():
        if kernel["kernel_id"] == kernel_id:
            return kernel
    raise KeyError(kernel_id)
