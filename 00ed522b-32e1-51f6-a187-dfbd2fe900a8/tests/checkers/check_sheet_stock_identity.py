# forge-canary: FORGE-CANARY-BC70212BA9429764BED89FCADB1574A6
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C_M1_sheet_stock_identity"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    manifest = verifier_lib.live_manifest()
    declared = verifier_lib.declared_recompute(workspace)
    if not declared.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, declared.get("error") or "declared_recompute_failed",
            declared.get("detail") or {},
        )

    for entry in declared["rows"]:
        instance = entry["instance"]
        expected = registry.profile_for_instance(manifest, instance["instance_ordinal"])
        stated = entry["row"].get("sheet_stock_profile_id")
        if stated != expected:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_sheet_stock_profile_diverges_from_live_pin",
                {"instance_id": instance["instance_id"], "declared": stated, "live_pin": expected},
            )
        stated_sheet = entry["row"].get("sheet_id")
        if stated_sheet != instance["sheet_id"]:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "declared_sheet_identifier_diverges",
                {"instance_id": instance["instance_id"], "declared": stated_sheet, "live": instance["sheet_id"]},
            )

    hidden = verifier_lib.hidden_sweep(workspace)
    if not hidden.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, hidden.get("error") or "hidden_sweep_failed")
    if hidden["infeasible"]:
        first = hidden["infeasible"][0]
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, first["verdict"]["reason"], {"instance_id": first["instance_id"]}
        )

    baseline = verifier_lib.baseline_sweep()
    if not baseline.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, baseline.get("error") or "baseline_sweep_failed")

    submitted_utilisation = 1.0 - hidden["mean_waste_fraction"]
    baseline_utilisation = 1.0 - baseline["mean_waste_fraction"]
    gain = submitted_utilisation - baseline_utilisation
    passed = gain >= registry.STOCK_EFFECT_MARGIN
    return verifier_lib.result(
        CHECKER_ID,
        passed,
        1.0 if passed else 0.0,
        "stock_effect_present" if passed else "no_utilisation_effect_over_frozen_baseline_on_live_stock",
        {
            "submitted_utilisation": submitted_utilisation,
            "baseline_utilisation": baseline_utilisation,
            "gain": gain,
            "required_margin": registry.STOCK_EFFECT_MARGIN,
            "live_pin": manifest["sheet_stock_profile_id"],
        },
    )
