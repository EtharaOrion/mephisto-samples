# forge-canary: FORGE-CANARY-837861982023138C90B2C0024F036FE0
"""Binds the executed instruction census to the reference machine replay of the emitted image.

Verifier private. M6 is silent, so the attempt at which the census authority repins is never
readable in advance. The pre mutation digest is retained here only so a submission that kept
the aggregate self measured authority can be named as stale rather than merely wrong.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import verifier_lib

CHECKER_ID = "C_M6_instruction_census_binding"

M6_TURN = 46

CENSUS_SUBMITTED_AGGREGATE = "submitted_total_instructions"
CENSUS_REPLAYED_TRIPLES = "reference_replayed_program_triples"

REPORT_FIELD = "instruction_census_digest"


def graded_attempt_index() -> int:
    return verifier_lib.graded_attempt_index()


def live_census_authority(attempt_index: int) -> str:
    return CENSUS_REPLAYED_TRIPLES if attempt_index >= M6_TURN else CENSUS_SUBMITTED_AGGREGATE


def replayed_census_digest(rows: list) -> str:
    triples = [
        [str(row["name"]), int(row["instructions"]), str(row["verdict"])]
        for row in sorted(rows, key=lambda row: str(row["name"]))
    ]
    return hashlib.sha256(json.dumps(triples, sort_keys=True).encode("utf-8")).hexdigest()


def submitted_total_census_digest(rows: list) -> str:
    counts = {"total_instructions": sum(int(row["instructions"]) for row in rows if row["passed"])}
    return hashlib.sha256(json.dumps(counts, sort_keys=True).encode("utf-8")).hexdigest()


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    authority = live_census_authority(graded_attempt_index())
    if authority != CENSUS_REPLAYED_TRIPLES:
        return verifier_lib.result(
            CHECKER_ID, True, 1.0, "instruction_census_authority_not_yet_pinned", {"census_authority": authority}
        )
    report = verifier_lib.report_of(workspace)
    if not report:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "report_unparseable")
    public = verifier_lib.public_measure(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_recompute_failed")
    rows = public["graded"]["rows"]
    live_digest = replayed_census_digest(rows)
    stale_digest = submitted_total_census_digest(rows)
    claimed = report.get(REPORT_FIELD)
    if claimed is None:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "instruction_census_digest_absent_under_pre_mutation_aggregate_authority",
            {"live": live_digest},
        )
    if claimed == stale_digest:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "instruction_census_digest_computed_under_pre_mutation_submitted_total_authority",
            {"claimed": claimed, "live": live_digest},
        )
    if claimed != live_digest:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reported_instruction_census_digest_diverges_from_live_replay",
            {"claimed": claimed, "live": live_digest},
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "instruction_census_bound_to_live_reference_replay",
        {"live": live_digest, "programs": len(rows)},
    )
