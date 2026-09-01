# forge-canary: FORGE-CANARY-C3A4D0A724B2C1B4ABB13DD5F51313F5
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M4_translation_anchor_binding"

CERTIFICATE_FIELD = "translation_normal_digest"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    live_anchor = verifier_lib.live_geometry().get("translation_anchor")
    if live_anchor not in registry.TRANSLATION_ANCHORS:
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, "live_translation_anchor_record_malformed", {"live": live_anchor}
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
            "declared_translation_normal_digest_diverges_from_live_anchor",
            {"claimed": claimed, "recomputed": recomputed, "live_translation_anchor": live_anchor},
        )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "translation_digest_bound_to_live_anchor",
        {"live_translation_anchor": live_anchor},
    )
