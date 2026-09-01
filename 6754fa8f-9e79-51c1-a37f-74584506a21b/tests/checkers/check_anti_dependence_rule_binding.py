# forge-canary: FORGE-CANARY-5E66977EB92CE4DFF49566BA6EF73BDC
"""Binds every submitted schedule to the live anti dependence hazard rule.

Under the pre repin rule ``late_landing_relaxed`` an overwriting operation only has
to land after the pending reader has read, which lets a scheduler hoist the overwrite
above the reader by the consumer latency minus one. Under ``issue_ordered_strict``
the write port commits in issue order, so the overwriting operation must issue
strictly after every pending reader issues. The required issue cycle is recomputed
here from the program order anti dependence edges and the emitted bundles alone, and
each finding records whether the same placement was legal under the relaxed rule so
the staleness is attributable. No clock and no random source is consulted.
"""

from __future__ import annotations

import pathlib

import machine
import verifier_lib

CHECKER_ID = "C_M6_anti_dependence_rule_binding"

RELAXED_RULE = "late_landing_relaxed"
STRICT_RULE = "issue_ordered_strict"
WAR_CLASSES = ("war", "mem_war")


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    live = verifier_lib.live_registry()
    rule = live.get("war_rule", RELAXED_RULE)
    if rule != STRICT_RULE:
        return verifier_lib.result(
            CHECKER_ID,
            True,
            1.0,
            "anti_dependence_rule_still_late_landing_relaxed",
            {"war_rule": rule, "machine_model_id": live.get("machine_model_id")},
        )

    submitted = verifier_lib.submitted_records(workspace)
    if not submitted.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, submitted.get("error") or "schedule_bundle_unreadable"
        )

    for record in submitted["records"]:
        declared = record.get("war_rule")
        if declared != rule:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "war_rule_not_declared_from_the_live_registry",
                {"kernel_id": record.get("kernel_id"), "declared": declared, "live": rule},
            )

    edges_checked = 0
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
        if not outcome["structural_ok"]:
            first = outcome["violations"][0] if outcome["violations"] else {"reason": "schedule_not_structural"}
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "schedule_not_structural",
                {"kernel_id": kernel["kernel_id"], "violation": first},
            )

        issue = outcome["issue"]
        op_by_id = {op["id"]: op for op in kernel["ops"]}
        dependences = machine.dependences(kernel)
        for edge_class in WAR_CLASSES:
            for reader, writer, resource in dependences[edge_class]:
                if reader not in issue or writer not in issue:
                    continue
                edges_checked += 1
                strict_required = issue[reader] + 1
                if issue[writer] >= strict_required:
                    continue
                relaxed_required = machine.earliest_after(
                    edge_class,
                    issue[reader],
                    machine.latency_of(model=live, op=op_by_id[reader]),
                    machine.latency_of(model=live, op=op_by_id[writer]),
                )
                return verifier_lib.result(
                    CHECKER_ID,
                    False,
                    0.0,
                    "schedule_bound_to_the_stale_anti_dependence_rule",
                    {
                        "kernel_id": kernel["kernel_id"],
                        "violation_class": edge_class,
                        "reader": reader,
                        "writer": writer,
                        "resource": resource,
                        "reader_cycle": issue[reader],
                        "writer_cycle": issue[writer],
                        "required_cycle_under_live_rule": strict_required,
                        "legal_under_relaxed_rule": issue[writer] >= relaxed_required,
                        "live_war_rule": rule,
                    },
                )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "every_schedule_respects_the_live_anti_dependence_rule",
        {
            "war_rule": rule,
            "kernels_checked": len(submitted["records"]),
            "anti_dependence_edges_checked": edges_checked,
        },
    )


def _kernel_of(kernel_id):
    for kernel in verifier_lib.public_kernels():
        if kernel["kernel_id"] == kernel_id:
            return kernel
    return None
