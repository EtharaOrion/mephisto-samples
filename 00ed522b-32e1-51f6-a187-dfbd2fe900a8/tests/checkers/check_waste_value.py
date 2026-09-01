# forge-canary: FORGE-CANARY-8881AD83FBBDBD62B88DCA22928690C5
from __future__ import annotations

import pathlib

import registry
import verifier_lib

CHECKER_ID = "C1_waste_value"

GEOMETRIC_CATEGORIES = ("containment", "overlap")


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    declared = verifier_lib.declared_recompute(workspace)
    if not declared.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, declared.get("error") or "declared_recompute_failed", declared.get("detail") or {}
        )

    for entry in declared["rows"]:
        verdict = entry["verdict"]
        if not verdict["feasible"] and verdict["category"] in GEOMETRIC_CATEGORIES:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                verdict["reason"],
                {"instance_id": entry["instance"]["instance_id"], **verdict["detail"]},
            )
        claimed = entry["row"].get("claimed_waste_fraction")
        if not isinstance(claimed, (int, float)):
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "claimed_waste_fraction_missing",
                {"instance_id": entry["instance"]["instance_id"]},
            )
        if verdict["feasible"] and abs(float(claimed) - verdict["waste_fraction"]) > verifier_lib.WASTE_TOLERANCE:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "claimed_waste_diverges_from_recompute",
                {
                    "instance_id": entry["instance"]["instance_id"],
                    "claimed": float(claimed),
                    "recomputed": verdict["waste_fraction"],
                },
            )

    hidden = verifier_lib.hidden_sweep(workspace)
    if not hidden.get("ok"):
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, hidden.get("error") or "hidden_sweep_failed",
            {"detail": hidden.get("detail")},
        )
    for record in hidden["records"]:
        verdict = record["verdict"]
        if not verdict["feasible"] and verdict["category"] in GEOMETRIC_CATEGORIES:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, verdict["reason"], {"instance_id": record["instance_id"], **verdict["detail"]}
            )
    if hidden["infeasible"]:
        first = hidden["infeasible"][0]
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            first["verdict"]["reason"],
            {"instance_id": first["instance_id"], **first["verdict"]["detail"]},
        )

    profile_id = verifier_lib.live_manifest()["sheet_stock_profile_id"]
    mean_waste = hidden["mean_waste_fraction"]
    score = registry.waste_to_score(mean_waste, profile_id)
    return verifier_lib.result(
        CHECKER_ID,
        score > 0.0,
        score,
        "waste_recomputed" if score > 0.0 else "waste_at_or_above_floor",
        {
            "mean_waste_fraction": mean_waste,
            "sheet_stock_profile_id": profile_id,
            "instances_graded": len(hidden["records"]),
            "waste_anchors": registry.WASTE_ANCHORS[profile_id],
        },
    )
