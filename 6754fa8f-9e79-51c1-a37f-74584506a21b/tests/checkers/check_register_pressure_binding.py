# forge-canary: FORGE-CANARY-F18CDD9D27957C9FD24743C43CBE6FEC
"""Binds every submitted schedule to the live architectural register file ceiling.

The registry record is the sole authority for how many architectural registers may
hold a simultaneously live value. Before the ceiling is pinned the obligation is not
in force and this checker reports the pre repin state. Once the registry carries
``architectural_register_ceiling`` the checker recomputes peak simultaneous register
liveness from the emitted bundles alone and fails any schedule whose peak exceeds the
ceiling, reporting whether the same schedule sat under the pre repin ceiling so the
staleness is attributable. No clock and no random source is consulted.
"""

from __future__ import annotations

import pathlib

import machine
import verifier_lib

CHECKER_ID = "C_M5_register_pressure_binding"

PRE_REPIN_CEILING_KEY = "architectural_register_ceiling_pre"
LIVE_CEILING_KEY = "architectural_register_ceiling"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    live = verifier_lib.live_registry()
    ceiling = live.get(LIVE_CEILING_KEY)
    if ceiling is None:
        return verifier_lib.result(
            CHECKER_ID,
            True,
            1.0,
            "architectural_register_ceiling_not_yet_pinned_in_the_live_registry",
            {"machine_model_id": live.get("machine_model_id")},
        )
    ceiling = int(ceiling)
    prior = live.get(PRE_REPIN_CEILING_KEY)
    prior = None if prior is None else int(prior)

    submitted = verifier_lib.submitted_records(workspace)
    if not submitted.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, submitted.get("error") or "schedule_bundle_unreadable"
        )

    for record in submitted["records"]:
        declared = record.get(LIVE_CEILING_KEY)
        if declared is None or int(declared) != ceiling:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "architectural_register_ceiling_not_declared_from_the_live_registry",
                {
                    "kernel_id": record.get("kernel_id"),
                    "declared": declared,
                    "live": ceiling,
                    "pre_repin": prior,
                },
            )

    peaks = {}
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

        peak, witness_cycle, witness_registers = _peak_liveness(kernel, live, outcome["issue"])
        peaks[kernel["kernel_id"]] = peak
        if peak > ceiling:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "register_pressure_bound_to_the_stale_register_file_ceiling",
                {
                    "kernel_id": kernel["kernel_id"],
                    "peak_live_registers": peak,
                    "live_ceiling": ceiling,
                    "pre_repin_ceiling": prior,
                    "legal_under_pre_repin_ceiling": prior is not None and peak <= prior,
                    "witness_cycle": witness_cycle,
                    "witness_registers": witness_registers,
                },
            )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "every_schedule_fits_the_live_architectural_register_ceiling",
        {
            "live_ceiling": ceiling,
            "pre_repin_ceiling": prior,
            "kernels_checked": len(peaks),
            "max_observed_peak": max(peaks.values()) if peaks else 0,
        },
    )


def _peak_liveness(kernel: dict, model: dict, issue: dict) -> tuple:
    """Peak count of distinct architectural registers holding a live value.

    A destination register is live from the cycle its producer issues through the
    later of the cycle the result lands and the cycle of the last program order
    consumer that reads it. The interval set is a pure function of the emitted
    bundles, the program order dependence edges and the live latency table.
    """
    op_by_id = {op["id"]: op for op in kernel["ops"]}
    last_use: dict = {}
    for producer, consumer, _register in machine.dependences(kernel)["raw"]:
        if producer not in issue or consumer not in issue:
            continue
        cycle = issue[consumer]
        if cycle > last_use.get(producer, -1):
            last_use[producer] = cycle

    intervals = []
    for op in kernel["ops"]:
        written = machine.reg_write(op)
        if written is None or op["id"] not in issue:
            continue
        start = issue[op["id"]]
        landing = start + machine.latency_of(model, op)
        end = max(landing, last_use.get(op["id"], landing))
        intervals.append((start, end, int(written)))

    if not intervals:
        return 0, 0, []

    horizon = max(end for _start, end, _register in intervals)
    peak = 0
    witness_cycle = 0
    witness_registers: list = []
    for cycle in range(0, horizon + 1):
        live_registers = sorted(
            {register for start, end, register in intervals if start <= cycle <= end}
        )
        if len(live_registers) > peak:
            peak = len(live_registers)
            witness_cycle = cycle
            witness_registers = live_registers
    return peak, witness_cycle, witness_registers[:16]


def _kernel_of(kernel_id):
    for kernel in verifier_lib.public_kernels():
        if kernel["kernel_id"] == kernel_id:
            return kernel
    return None
