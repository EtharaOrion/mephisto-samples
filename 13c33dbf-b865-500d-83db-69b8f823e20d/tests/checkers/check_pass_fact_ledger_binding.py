# forge-canary: FORGE-CANARY-22582D8CBA73BFC7E63DCE10B60DAC9D
"""Binds the pass pipeline surface to a per pass fact delta ledger.

Verifier private. M5 is silent, so the attempt at which the pipeline surface repins is never
readable in advance. The ledger must be carried by the submitted module itself as well as by
the manifest, so absorbing this repin forces the compiler archive to be rebuilt rather than a
single JSON deliverable to be patched.
"""

from __future__ import annotations

import json
import pathlib

import verifier_lib

CHECKER_ID = "C_M5_pass_fact_ledger_binding"

M5_TURN = 38

PIPELINE_DECLARED_LIST_ONLY = "declared_pass_list_only"
PIPELINE_FACT_DELTA_LEDGER = "per_pass_fact_delta_ledger"

MANIFEST_FIELD = "pass_fact_ledger"


def graded_attempt_index() -> int:
    attempts = verifier_lib.harness_attempts()
    if not attempts:
        return 0
    return max(int(record.get("attempt_index", 0)) for record in attempts)


def live_pipeline_surface(attempt_index: int) -> str:
    return PIPELINE_FACT_DELTA_LEDGER if attempt_index >= M5_TURN else PIPELINE_DECLARED_LIST_ONLY


def recompute(manifest: dict) -> dict | None:
    passes = manifest.get("passes")
    invariants_by_pass = manifest.get("pass_invariants")
    if not isinstance(passes, list) or not isinstance(invariants_by_pass, dict):
        return None
    facts: set = set()
    ledger: dict = {}
    for name in passes:
        invariants = invariants_by_pass.get(name)
        if not isinstance(invariants, dict):
            return None
        invalidates = invariants.get("invalidates", [])
        establishes = invariants.get("establishes", [])
        if not isinstance(invalidates, list) or not isinstance(establishes, list):
            return None
        facts.difference_update(str(fact) for fact in invalidates)
        facts.update(str(fact) for fact in establishes)
        ledger[str(name)] = sorted(facts)
    return ledger


def normalise(claimed: object) -> dict | None:
    if not isinstance(claimed, dict):
        return None
    out: dict = {}
    for key, value in claimed.items():
        if not isinstance(value, list):
            return None
        for entry in value:
            if not isinstance(entry, str):
                return None
        out[str(key)] = sorted(str(entry) for entry in value)
    return out


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    surface = live_pipeline_surface(graded_attempt_index())
    if surface != PIPELINE_FACT_DELTA_LEDGER:
        return verifier_lib.result(
            CHECKER_ID, True, 1.0, "pass_fact_ledger_not_yet_pinned", {"pipeline_surface": surface}
        )
    manifest_path = verifier_lib.find_deliverable(workspace, "D4")
    if manifest_path is None:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "missing_deliverable_D4")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (ValueError, OSError):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "pass_pipeline_unparseable")
    if not isinstance(manifest, dict):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "pass_pipeline_unparseable")
    live = recompute(manifest)
    if live is None:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "pass_declaration_incomplete")
    if MANIFEST_FIELD not in manifest:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "pass_fact_ledger_absent_under_pre_mutation_declared_pass_list_only_surface",
            {"passes": len(manifest.get("passes", []))},
        )
    claimed = normalise(manifest.get(MANIFEST_FIELD))
    if claimed is None:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "pass_fact_ledger_malformed")
    if claimed != live:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "declared_pass_fact_ledger_diverges_from_forward_simulation",
            {"claimed": claimed, "live": live},
        )
    public = verifier_lib.public_measure(workspace)
    if not public.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, public.get("error") or "public_recompute_failed")
    declared = public["compiled"].get("pipeline")
    if not isinstance(declared, dict):
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "pipeline_description_unavailable_from_submitted_module",
            {"error": public["compiled"].get("pipeline_error")},
        )
    module_ledger = normalise(declared.get(MANIFEST_FIELD))
    if module_ledger != live:
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "submitted_module_pass_fact_ledger_diverges_from_forward_simulation",
            {"claimed": module_ledger, "live": live},
        )
    return verifier_lib.result(
        CHECKER_ID, True, 1.0, "pass_fact_ledger_bound_to_live_forward_simulation", {"passes": len(live)}
    )
