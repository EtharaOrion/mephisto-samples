# forge-canary: FORGE-CANARY-1254CEC55E3E94C4E944B7B7CCD8B8F1
from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "checkers"))

import verifier_lib

CHECKER_MODULES = (
    "check_construction_size_value",
    "check_reference_construction_absence",
    "check_geometry_parameter_identity",
    "check_property_predicate_binding",
    "check_certificate_invariant",
    "check_attempt_ordering",
    "check_injection_absence",
    "check_silent_degeneracy_divergence",
    "check_translation_anchor_binding",
    "check_digest_join_binding",
    "check_pair_sum_order_binding",
)

SCORING_CHECKER = "C1_construction_size_value"
GATE_CHECKERS = (
    "C5_injection_absence",
    "C2_reference_construction_absence",
    "C_M2_property_predicate_binding",
    "C_M5_digest_join_binding",
    "C_M4_translation_anchor_binding",
    "C_M6_pair_sum_order_binding",
    "C3_certificate_invariant",
    "C6_silent_degeneracy_divergence",
)
PENALTY_CHECKERS = {"C4_attempt_ordering": 0.5, "C_M1_geometry_parameter_identity": 0.5}


def run(workspace: pathlib.Path) -> dict:
    try:
        verifier_lib.ensure_live_state(workspace)
    except Exception as exc:
        print(f"live state bootstrap failed: {exc!r}", file=sys.stderr)
    results = []
    for name in CHECKER_MODULES:
        module = importlib.import_module(name)
        try:
            results.append(module.check(workspace))
        except Exception as exc:
            results.append(
                verifier_lib.result(module.CHECKER_ID, False, 0.0, "checker_raised", {"error": repr(exc)})
            )
    by_id = {entry["checker_id"]: entry for entry in results}

    zero_reason = None
    for checker_id in GATE_CHECKERS:
        entry = by_id[checker_id]
        if not entry["passed"]:
            zero_reason = {"checker_id": checker_id, "reason": entry["reason"], "detail": entry["detail"]}
            break

    scoring = by_id[SCORING_CHECKER]
    if zero_reason is not None:
        score = 0.0
    elif not scoring["passed"]:
        score = 0.0
        zero_reason = {
            "checker_id": SCORING_CHECKER,
            "reason": scoring["reason"],
            "detail": scoring["detail"],
        }
    else:
        score = scoring["contribution"]
        for checker_id, multiplier in PENALTY_CHECKERS.items():
            if not by_id[checker_id]["passed"]:
                score *= multiplier

    score = max(0.0, min(1.0, score))
    return {
        "schema_version": 1,
        "task_id": "cap_set_extremal_construction",
        "metric": "score",
        "score": score,
        "reward": score,
        "range": [0.0, 1.0],
        "zero_reason": zero_reason,
        "checkers": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=str(verifier_lib.WORKSPACE))
    parser.add_argument("--reward-path", default="/logs/verifier/reward.json")
    args = parser.parse_args()

    workspace = pathlib.Path(args.workspace).resolve()
    document = run(workspace)
    reward_path = pathlib.Path(args.reward_path)
    reward_path.parent.mkdir(parents=True, exist_ok=True)
    reward_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"score": document["score"], "zero_reason": document["zero_reason"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
