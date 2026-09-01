# forge-canary: FORGE-CANARY-1BB2B264DB7B36163B3AD778A3401A39
"""Binds the suite report reconciliation surface to the live per category breakdown.

Verifier private. The attempt at which the reconciliation surface repins, and the surface it
repins to, are never mirrored into any mount the solver namespace can read, because M3 is
silent. A submission that resolves the reconciliation surface from live state on every
attempt absorbs the repin, while a submission that cached the aggregate only surface it saw
earlier in the run goes stale here.
"""

from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C_M3_category_breakdown_binding"

M3_TURN = 7

BREAKDOWN_AGGREGATE_ONLY = "aggregate_counts_only"
BREAKDOWN_PER_CATEGORY = "per_category_pass_breakdown"

REPORT_FIELD = "passed_by_category"


def graded_attempt_index() -> int:
    attempts = verifier_lib.harness_attempts()
    if not attempts:
        return 0
    return max(int(record.get("attempt_index", 0)) for record in attempts)


def live_breakdown_mode(attempt_index: int) -> str:
    return BREAKDOWN_PER_CATEGORY if attempt_index >= M3_TURN else BREAKDOWN_AGGREGATE_ONLY


def recompute(rows: list) -> dict:
    breakdown: dict = {}
    for row in rows:
        category = str(row["category"])
        breakdown.setdefault(category, 0)
        if row["passed"]:
            breakdown[category] += 1
    return breakdown


def normalise(claimed: object) -> dict | None:
    if not isinstance(claimed, dict):
        return None
    out: dict = {}
    for key, value in claimed.items():
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        out[str(key)] = int(value)
    return out


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    mode = live_breakdown_mode(graded_attempt_index())
    if mode != BREAKDOWN_PER_CATEGORY:
        return verifier_lib.result(
            CHECKER_ID, True, 1.0, "category_breakdown_not_yet_pinned", {"breakdown_mode": mode}
        )
    report = verifier_lib.report_of(workspace)
    if not report:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "report_unparseable")
    public = verifier_lib.public_measure(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_recompute_failed")
    live = recompute(public["graded"]["rows"])
    if REPORT_FIELD not in report:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "category_breakdown_absent_under_pre_mutation_aggregate_counts_only_surface",
            {"live": live},
        )
    claimed = normalise(report.get(REPORT_FIELD))
    if claimed is None:
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, "category_breakdown_malformed", {"claimed": repr(report.get(REPORT_FIELD))[:200]}
        )
    if claimed != live:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reported_category_breakdown_diverges_from_recompute",
            {"claimed": claimed, "live": live},
        )
    return verifier_lib.result(
        CHECKER_ID, True, 1.0, "category_breakdown_bound_to_live_recompute", {"live": live}
    )
