# forge-canary: FORGE-CANARY-C3A4D0A724B2C1B4ABB13DD5F51313F5
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C1_construction_size_value"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    state = verifier_lib.recompute(workspace)
    if not state.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, state.get("error") or "recompute_failed", state.get("error_detail")
        )

    measurement = state["measurement"]
    if measurement["violation_count"] > 0:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "property_violation_detected",
            {
                "quadruple_collisions": measurement["quadruple_collisions"],
                "degenerate_collision_count": measurement["degenerate_collision_count"],
                "predicate_id": state["predicate"]["predicate_id"],
            },
        )

    ambient = state["ambient"]
    verified = state["verified_size"]
    score = registry.size_to_score(verified, ambient)
    return verifier_lib.result(
        CHECKER_ID,
        score > 0.0,
        score,
        "verified_size_recomputed" if score > 0.0 else "size_at_or_below_floor",
        {
            "verified_size": verified,
            "claimed_point_count": state["bundle"].get("point_count"),
            "size_floor": ambient["size_floor"],
            "size_target": ambient["size_target"],
            "ambient_params_id": ambient["ambient_params_id"],
        },
    )
