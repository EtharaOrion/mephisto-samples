# forge-canary: FORGE-CANARY-1254CEC55E3E94C4E944B7B7CCD8B8F1
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M1_geometry_parameter_identity"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    state = verifier_lib.recompute(workspace)
    if not state.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, state.get("error") or "recompute_failed", state.get("error_detail")
        )

    geometry = state["geometry"]
    live_id = geometry["ambient_params_id"]
    claimed = state["bundle"].get("ambient_params_id")
    if claimed != live_id:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "declared_ambient_identity_stale",
            {"claimed": claimed, "live": live_id, "transition": geometry.get("transition")},
        )

    try:
        emitted = verifier_lib.run_constructor(verifier_lib.find_deliverable(workspace, "D1"))
    except verifier_lib.VerifierError as exc:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "constructor_raised", {"error": str(exc)})
    if emitted.get("ambient_params_id") != live_id:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "constructor_ambient_constant_stale",
            {"declared": emitted.get("ambient_params_id"), "live": live_id},
        )

    baseline = verifier_lib.baseline_size()
    required = baseline * registry.EFFECT_MARGIN
    verified = state["verified_size"]
    if verified < required:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "no_measurable_effect_on_rotated_ambient",
            {"verified_size": verified, "baseline_size": baseline, "required_size": required},
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "effect_measured_on_rotated_ambient",
        {
            "verified_size": verified,
            "baseline_size": baseline,
            "ambient_params_id": live_id,
            "transition": geometry.get("transition"),
        },
    )
