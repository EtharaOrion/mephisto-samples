# forge-canary: FORGE-CANARY-C4CDF9EBB33965998B2D609A6897A25C
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
    "check_cycle_count_value",
    "check_hidden_kernel_absence",
    "check_machine_model_identity",
    "check_latency_table_binding",
    "check_budget_invariant",
    "check_bundle_ordering",
    "check_injection_absence",
    "check_silent_hazard_divergence",
    "check_attempt_ordering",
    "check_register_pressure_binding",
    "check_anti_dependence_rule_binding",
)

SCORING_CHECKER = "C1_cycle_count_value"
GATE_CHECKERS = (
    "C2_hidden_kernel_absence",
    "C4_bundle_ordering",
    "C6_silent_hazard_divergence",
    "C_M2_latency_table_binding",
    "C_M5_register_pressure_binding",
    "C_M6_anti_dependence_rule_binding",
    "C5_injection_absence",
    "C3_budget_invariant",
)
PENALTY_CHECKERS = {"C_M1_machine_model_identity": 0.5, "C7_attempt_ordering": 0.5}


def run(workspace: pathlib.Path) -> dict:
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
        "task_id": "vliw_kernel_optimization",
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
