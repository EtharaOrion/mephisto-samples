# forge-canary: FORGE-CANARY-1BB2B264DB7B36163B3AD778A3401A39
from __future__ import annotations

import pathlib

import verifier_lib

CHECKER_ID = "C2_semantics_invariant"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    probes = verifier_lib.boundary_programs()
    compiled = verifier_lib.compile_batch(workspace, probes, "boundary")
    if not compiled.get("ok"):
        return verifier_lib.result(CHECKER_ID, False, 0.0, compiled.get("error") or "compile_failed")
    graded = verifier_lib.grade(probes, compiled)
    for row in graded["rows"]:
        if not row["passed"]:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "semantics_boundary_violated",
                {
                    "probe": row["name"],
                    "verdict": row["verdict"],
                    "exit_status": row.get("exit_status"),
                    "expected_exit_status": row.get("expected_exit_status"),
                    "first_divergence": row.get("first_divergence"),
                },
            )
    return verifier_lib.result(
        CHECKER_ID, True, 1.0, "semantics_boundaries_exact", {"probes": len(graded["rows"])}
    )
