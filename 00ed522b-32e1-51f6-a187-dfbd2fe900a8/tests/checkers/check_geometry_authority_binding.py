# forge-canary: FORGE-CANARY-BC70212BA9429764BED89FCADB1574A6
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M2_geometry_authority_binding"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    authority = verifier_lib.live_authority()
    live_digest = registry.authority_digest(authority)

    declared = verifier_lib.declared_recompute(workspace)
    if not declared.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, declared.get("error") or "declared_recompute_failed",
            declared.get("detail") or {},
        )

    for entry in declared["rows"]:
        stated = entry["row"].get("carrier_authority_digest")
        if stated != live_digest:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_carrier_authority_digest_diverges_from_live_registry",
                {
                    "instance_id": entry["instance"]["instance_id"],
                    "declared": stated,
                    "live_digest": live_digest,
                    "live_revision": authority["authority_revision_id"],
                },
            )
        verdict = entry["verdict"]
        if not verdict["feasible"] and verdict["category"] == "authority":
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                verdict["reason"],
                {"instance_id": entry["instance"]["instance_id"], **verdict["detail"]},
            )

    hidden = verifier_lib.hidden_sweep(workspace)
    if not hidden.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, hidden.get("error") or "hidden_sweep_failed")
    for record in hidden["records"]:
        if record["declared_authority_digest"] != live_digest:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "emitted_carrier_authority_digest_diverges_from_live_registry",
                {
                    "instance_id": record["instance_id"],
                    "declared": record["declared_authority_digest"],
                    "live_digest": live_digest,
                },
            )
        verdict = record["verdict"]
        if not verdict["feasible"] and verdict["category"] == "authority":
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, verdict["reason"], {"instance_id": record["instance_id"], **verdict["detail"]}
            )

    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "authority_binding_resolved_against_live_registry",
        {
            "live_revision": authority["authority_revision_id"],
            "bindings": authority["bindings"],
            "instances_checked": len(declared["rows"]) + len(hidden["records"]),
        },
    )
