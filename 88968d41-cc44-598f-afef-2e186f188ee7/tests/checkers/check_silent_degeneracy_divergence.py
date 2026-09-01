# forge-canary: FORGE-CANARY-66179744CBBE6D40F17E52FC11A7BD50
from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C6_silent_degeneracy_divergence"

DEGENERATE_CLASS = "repeated_point_triple"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    state = verifier_lib.recompute(workspace)
    if not state.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, state.get("error") or "recompute_failed", state.get("error_detail")
        )

    predicate = state["predicate"]
    measurement = state["measurement"]
    declared = state["bundle"]["certificate"] if isinstance(state["bundle"].get("certificate"), dict) else {}
    claimed_count = declared.get("degenerate_collision_count")
    if claimed_count != measurement["degenerate_collision_count"]:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "degenerate_collision_count_diverges_from_recompute",
            {"claimed": claimed_count, "recomputed": measurement["degenerate_collision_count"]},
        )

    forbidden = DEGENERATE_CLASS in predicate.get("forbidden_tuple_classes", [])
    if forbidden and measurement["degenerate_collision_count"] > 0:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "degenerate_tuple_pattern_violation",
            {
                "degenerate_collision_count": measurement["degenerate_collision_count"],
                "predicate_id": predicate["predicate_id"],
            },
        )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "degenerate_tuple_pattern_absent_under_live_predicate",
        {
            "degenerate_collision_count": measurement["degenerate_collision_count"],
            "predicate_id": predicate["predicate_id"],
            "class_forbidden": forbidden,
        },
    )
