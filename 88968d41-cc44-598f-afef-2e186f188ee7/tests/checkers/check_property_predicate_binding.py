# forge-canary: FORGE-CANARY-4AE0EDE26D579A1BF7C543EA855A0482
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M2_property_predicate_binding"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    live = verifier_lib.live_predicate()
    live_digest = live["predicate_digest"]
    if registry.predicate_digest(live) != live_digest:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "live_predicate_record_self_inconsistent")

    state = verifier_lib.recompute(workspace)
    if not state.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, state.get("error") or "recompute_failed", state.get("error_detail")
        )

    claimed = state["bundle"].get("predicate_digest")
    if claimed != live_digest:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "declared_predicate_digest_diverges_from_live_registry",
            {"claimed": claimed, "live": live_digest, "live_predicate_id": live["predicate_id"]},
        )

    try:
        emitted = verifier_lib.run_constructor(verifier_lib.find_deliverable(workspace, "D1"))
    except verifier_lib.VerifierError as exc:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "constructor_raised", {"error": str(exc)})
    if emitted.get("predicate_digest") != live_digest:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "constructor_predicate_digest_diverges_from_live_registry",
            {"declared": emitted.get("predicate_digest"), "live": live_digest},
        )

    if state["measurement"]["quadruple_collisions"] > 0:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "property_violation_detected",
            {"quadruple_collisions": state["measurement"]["quadruple_collisions"]},
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "predicate_bound_to_live_registry",
        {"predicate_id": live["predicate_id"], "predicate_digest": live_digest},
    )
