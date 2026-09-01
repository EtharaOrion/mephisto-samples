# forge-canary: FORGE-CANARY-C3A4D0A724B2C1B4ABB13DD5F51313F5
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M6_pair_sum_order_binding"

CERTIFICATE_FIELD = "pair_sum_digest"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    live_order = verifier_lib.live_geometry().get("pair_sum_order")
    if live_order not in registry.PAIR_SUM_ORDERS:
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, "live_pair_sum_order_record_malformed", {"live": live_order}
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
            "declared_pair_sum_digest_diverges_from_live_order",
            {"claimed": claimed, "recomputed": recomputed, "live_pair_sum_order": live_order},
        )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "pair_sum_digest_bound_to_live_order",
        {"live_pair_sum_order": live_order},
    )
