# forge-canary: FORGE-CANARY-CB5DCD73188C60E84FADF07F58F31424
from __future__ import annotations

import pathlib

import machine
import verifier_lib

CHECKER_ID = "C_M2_latency_table_binding"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    live = verifier_lib.live_registry()
    live_digest = live["latency_table_digest"]
    manifest = verifier_lib.live_manifest()

    submitted = verifier_lib.submitted_records(workspace)
    if not submitted.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, submitted.get("error") or "schedule_bundle_unreadable")

    for record in submitted["records"]:
        declared = record.get("latency_table_digest")
        if declared != live_digest:
            reason = "latency_table_digest_diverges_from_live_registry"
            if declared == manifest["latency_table_digest"]:
                reason = "shipped_manifest_digest_declared_instead_of_live_registry_digest"
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                reason,
                {
                    "kernel_id": record.get("kernel_id"),
                    "declared": declared,
                    "live": live_digest,
                    "shipped_manifest": manifest["latency_table_digest"],
                },
            )

    stale_model = dict(live)
    stale_model["latencies"] = manifest["latencies"]
    public = verifier_lib.public_sweep(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_sweep_failed")

    for record in submitted["records"]:
        kernel = _kernel_of(record.get("kernel_id"))
        if kernel is None:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_kernel_absent_from_public_family",
                {"kernel_id": record.get("kernel_id")},
            )
        outcome = machine.replay(kernel, live, record.get("bundles"))
        if not outcome["structural_ok"] or outcome["violations"] or outcome["waw_violations"]:
            findings = outcome["violations"] + outcome["waw_violations"]
            first = findings[0] if findings else {"reason": "schedule_not_structural"}
            stale_outcome = machine.replay(kernel, stale_model, record.get("bundles"))
            stale_clean = (
                stale_outcome["structural_ok"]
                and not stale_outcome["violations"]
                and not stale_outcome["waw_violations"]
            )
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "schedule_bound_to_the_stale_latency_table" if stale_clean else "latency_violation",
                {
                    "kernel_id": kernel["kernel_id"],
                    "violation": first,
                    "legal_under_shipped_manifest": stale_clean,
                    "live_latency_table_id": live["latency_table_id"],
                },
            )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "schedules_bound_to_the_live_latency_table",
        {
            "latency_table_id": live["latency_table_id"],
            "latency_table_digest": live_digest,
            "kernels_declared": len(submitted["records"]),
        },
    )


def _kernel_of(kernel_id):
    for kernel in verifier_lib.public_kernels():
        if kernel["kernel_id"] == kernel_id:
            return kernel
    return None
