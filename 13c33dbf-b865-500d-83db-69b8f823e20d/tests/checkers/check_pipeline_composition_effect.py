# forge-canary: FORGE-CANARY-837861982023138C90B2C0024F036FE0
from __future__ import annotations

import json
import pathlib

import verifier_lib

CHECKER_ID = "C7_pipeline_composition_effect"

INITIAL_FACTS: set = set()


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    manifest_path = verifier_lib.find_deliverable(workspace, "D4")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (ValueError, OSError):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "pass_pipeline_unparseable")
    for key in ("passes", "pass_preconditions", "pass_invariants"):
        if key not in manifest:
            return verifier_lib.result(CHECKER_ID, False, 0.0, "pass_pipeline_key_absent", {"key": key})
    passes = manifest["passes"]
    if not isinstance(passes, list) or not passes:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "pass_pipeline_empty")

    public = verifier_lib.public_measure(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_recompute_failed")
    declared = public["compiled"].get("pipeline")
    if declared is None:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "pipeline_description_unavailable_from_submitted_module",
            {"error": public["compiled"].get("pipeline_error")},
        )
    if declared != manifest:
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, "pass_pipeline_diverges_from_submitted_module_description"
        )

    facts = set(INITIAL_FACTS)
    for name in passes:
        preconditions = manifest["pass_preconditions"].get(name)
        invariants = manifest["pass_invariants"].get(name)
        if preconditions is None or invariants is None:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "pass_declaration_incomplete", {"pass": name}
            )
        unknown = [f for f in list(preconditions) + list(invariants.get("establishes", [])) + list(invariants.get("invalidates", [])) if f not in verifier_lib.IR_CONTRACT_FACTS]
        if unknown:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "pass_fact_outside_intermediate_representation_contract",
                {"pass": name, "facts": unknown},
            )
        missing = [f for f in preconditions if f not in facts]
        if missing:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "pass_precondition_invalidated_by_earlier_pass",
                {"pass": name, "missing": missing, "available": sorted(facts)},
            )
        facts.difference_update(invariants.get("invalidates", []))
        facts.update(invariants.get("establishes", []))
    absent = [f for f in verifier_lib.IR_CONTRACT_REQUIRED_OUTPUT if f not in facts]
    if absent:
        return verifier_lib.result(
            CHECKER_ID, False, 0.0, "pipeline_does_not_establish_required_output_facts", {"missing": absent}
        )

    baseline_total = public["baseline_total_instructions"]
    submitted_total = public["total_instructions"]
    achieved = baseline_total / submitted_total if submitted_total else 0.0
    if achieved < verifier_lib.PIPELINE_EFFECT_MARGIN:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "pipeline_composition_effect_below_declared_margin",
            {"achieved": round(achieved, 6), "required": verifier_lib.PIPELINE_EFFECT_MARGIN},
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "pass_pipeline_composes_and_effect_measured",
        {"passes": len(passes), "achieved": round(achieved, 6)},
    )
