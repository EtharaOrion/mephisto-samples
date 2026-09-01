# forge-canary: FORGE-CANARY-CB5DCD73188C60E84FADF07F58F31424
from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C4_bundle_ordering"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    sweep = verifier_lib.graded_sweep(workspace)
    if not sweep.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, sweep.get("error") or "graded_sweep_failed")

    for record in sweep["kernels"]:
        if not record["structural_ok"]:
            first = record["violations"][0] if record["violations"] else {"reason": "schedule_not_structural"}
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "hazard_violation",
                {"kernel_id": record["kernel_id"], "violation": first},
            )
        if record["violations"]:
            first = record["violations"][0]
            reason = "port_oversubscription" if first["violation_class"] in ("port", "issue_width") else "latency_violation"
            if first["violation_class"] in ("war", "mem_war", "unit_occupancy"):
                reason = "hazard_violation"
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                reason,
                {"kernel_id": record["kernel_id"], "violation": first},
            )
        if record["semantic_ok"] is False:
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
    if submitted["duplicates"]:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "multiple_schedules_offered_for_one_kernel",
            {"kernel_ids": sorted(set(submitted["duplicates"]))[:8]},
        )
    expected = {kernel["kernel_id"] for kernel in verifier_lib.public_kernels()}
    offered = {record.get("kernel_id") for record in submitted["records"]}
    if offered != expected:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "schedule_bundle_does_not_cover_the_public_kernel_family",
            {"missing": sorted(expected - offered)[:8], "unexpected": sorted(offered - expected)[:8]},
        )

    public = verifier_lib.public_sweep(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_sweep_failed")
    for record in submitted["records"]:
        mirror = public["by_kernel"][record["kernel_id"]]
        if mirror["violations"] or not mirror["structural_ok"]:
            first = mirror["violations"][0] if mirror["violations"] else {"reason": "schedule_not_structural"}
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "hazard_violation",
                {"kernel_id": record["kernel_id"], "violation": first},
            )
        if record.get("bundle_count") != len(record.get("bundles") or []):
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_bundle_count_diverges_from_emitted_bundles",
                {"kernel_id": record["kernel_id"], "declared": record.get("bundle_count")},
            )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "bundle_issue_order_replays_legally",
        {"graded_kernels": len(sweep["kernels"]), "declared_kernels": len(submitted["records"])},
    )
