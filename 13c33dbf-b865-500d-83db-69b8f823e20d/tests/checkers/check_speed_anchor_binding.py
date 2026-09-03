# forge-canary: FORGE-CANARY-6CAA841C1ADA9B611F786DD993BFAE95
"""Binds the speed accounting surface to the live per program reference anchor.

Verifier private. M4 is silent, so neither the attempt at which the speed accounting surface
repins nor the surface it repins to is ever written into a mount the solver namespace can
read. The reference anchor itself moves whenever the instruction set or the calling
convention repins, so an enumeration cached from an earlier attempt is stale twice over.
"""

from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C_M4_speed_anchor_binding"

M4_TURN = 21

ANCHOR_SUBMITTED_AGGREGATE = "submitted_aggregate_speedup"
ANCHOR_REFERENCE_PER_PROGRAM = "reference_recomputed_per_program_anchor"

REPORT_FIELD = "unaccelerated_programs"


def graded_attempt_index() -> int:
    return verifier_lib.graded_attempt_index()


def live_anchor_authority(attempt_index: int) -> str:
    return ANCHOR_REFERENCE_PER_PROGRAM if attempt_index >= M4_TURN else ANCHOR_SUBMITTED_AGGREGATE


def recompute(graded: dict, baseline_graded: dict) -> list:
    unaccelerated = []
    for row in graded["rows"]:
        if not row["passed"]:
            continue
        anchor = baseline_graded["by_name"].get(row["name"])
        if anchor is None or not anchor["passed"]:
            unaccelerated.append(str(row["name"]))
            continue
        if int(row["instructions"]) >= int(anchor["instructions"]):
            unaccelerated.append(str(row["name"]))
    return sorted(unaccelerated)


def normalise(claimed: object) -> list | None:
    if not isinstance(claimed, list):
        return None
    for entry in claimed:
        if not isinstance(entry, str):
            return None
    return sorted(str(entry) for entry in claimed)


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    authority = live_anchor_authority(graded_attempt_index())
    if authority != ANCHOR_REFERENCE_PER_PROGRAM:
        return verifier_lib.result(
            CHECKER_ID, True, 1.0, "speed_anchor_authority_not_yet_pinned", {"anchor_authority": authority}
        )
    report = verifier_lib.report_of(workspace)
    if not report:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "report_unparseable")
    public = verifier_lib.public_measure(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_recompute_failed")
    live = recompute(public["graded"], public["baseline_graded"])
    if REPORT_FIELD not in report:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "speed_anchor_enumeration_absent_under_pre_mutation_aggregate_speedup_authority",
            {"live": live},
        )
    claimed = normalise(report.get(REPORT_FIELD))
    if claimed is None:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "speed_anchor_enumeration_malformed",
            {"claimed": repr(report.get(REPORT_FIELD))[:200]},
        )
    if claimed != live:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reported_speed_anchor_enumeration_diverges_from_recompute",
            {"claimed": claimed, "live": live},
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "speed_anchor_enumeration_bound_to_live_reference_recompute",
        {"unaccelerated": len(live)},
    )
