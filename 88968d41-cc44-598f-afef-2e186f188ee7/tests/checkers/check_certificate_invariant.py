# forge-canary: FORGE-CANARY-66179744CBBE6D40F17E52FC11A7BD50
from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C3_certificate_invariant"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    state = verifier_lib.recompute(workspace)
    if not state.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, state.get("error") or "recompute_failed", state.get("error_detail")
        )

    bundle = state["bundle"]
    geometry = state["geometry"]
    claimed = bundle.get("certificate")
    if not isinstance(claimed, dict):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "certificate_absent")

    recomputed = state["certificate"]
    for key in verifier_lib.CERTIFICATE_KEYS:
        if key not in claimed:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "certificate_field_absent", {"field": key}
            )
        if claimed[key] != recomputed[key]:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "certificate_irreconcilable_with_emitted_point_set",
                {"field": key, "claimed": claimed[key], "recomputed": recomputed[key]},
            )

    ceiling = geometry["emission_ceiling"]
    if len(state["indexed"]) > ceiling:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "budget_overrun",
            {"emitted": len(state["indexed"]), "emission_ceiling": ceiling},
        )

    search_seconds = bundle.get("search_seconds")
    if not isinstance(search_seconds, (int, float)) or isinstance(search_seconds, bool):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "search_seconds_absent")
    budget = geometry["search_budget_seconds"]
    if float(search_seconds) > budget + verifier_lib.SEARCH_SECONDS_TOLERANCE:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "budget_overrun",
            {"search_seconds": float(search_seconds), "search_budget_seconds": budget},
        )

    attempts = verifier_lib.harness_attempts()
    if attempts:
        recorded = attempts[-1].get("search_seconds")
        if isinstance(recorded, (int, float)) and float(recorded) > budget + verifier_lib.SEARCH_SECONDS_TOLERANCE:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "budget_overrun",
                {"harness_search_seconds": float(recorded), "search_budget_seconds": budget},
            )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "certificate_reconstructs_from_emitted_point_set",
        {
            "distinct_pair_sums": recomputed["distinct_pair_sums"],
            "emission_ceiling": ceiling,
            "search_budget_seconds": budget,
        },
    )
