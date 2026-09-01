# forge-canary: FORGE-CANARY-4AE0EDE26D579A1BF7C543EA855A0482
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M5_digest_join_binding"

CERTIFICATE_FIELD = "canonical_point_digest"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    live_join = verifier_lib.live_geometry().get("digest_join")
    if live_join not in registry.DIGEST_JOINS:
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, "live_digest_join_record_malformed", {"live": live_join}
        )

    state = verifier_lib.recompute(workspace)
    if not state.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, state.get("error") or "recompute_failed", state.get("error_detail")
        )

    declared = state["bundle"].get("certificate") if isinstance(state["bundle"].get("certificate"), dict) else {}
    claimed = declared.get(CERTIFICATE_FIELD)
    recomputed = state["certificate"][CERTIFICATE_FIELD]
    if claimed != recomputed:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "declared_canonical_point_digest_diverges_from_live_join_token",
            {"claimed": claimed, "recomputed": recomputed, "live_digest_join": live_join},
        )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "certificate_digests_bound_to_live_join_token",
        {"live_digest_join": live_join},
    )
