# forge-canary: FORGE-CANARY-6CAA841C1ADA9B611F786DD993BFAE95
from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import control_lib
import score
import verifier_lib

CONTROL_MODULES = (
    "control_no_op",
    "control_stale_calling_convention",
    "control_decoy",
    "control_list_all",
    "control_obvious_wrong",
    "control_stale_category_breakdown",
    "control_stale_speed_anchor",
    "control_stale_pass_fact_ledger",
    "control_stale_instruction_census",
)

CONTROL_ATTEMPT_INDEX = 50


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=verifier_lib.CONTROL_THRESHOLD)
    parser.add_argument("--attempt-index", type=int, default=CONTROL_ATTEMPT_INDEX)
    args = parser.parse_args()

    rows = []
    failures = 0
    for name in CONTROL_MODULES:
        module = importlib.import_module(name)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            control_lib.prepare_mounts(root, args.attempt_index)
            records = control_lib.synthesize_harness(root, args.attempt_index)
            workspace = root / "workspace"
            module.build(workspace, records)
            verifier_lib._MEMO.pop(f"holdout_measure:{workspace.resolve()}", None)
            document = score.run(workspace.resolve())
        zero = document["zero_reason"]
        below = document["score"] < args.threshold
        failures += 0 if below else 1
        rows.append(
            {
                "control_id": module.CONTROL_ID,
                "kind": module.KIND,
                "score": round(document["score"], 6),
                "below_threshold": below,
                "attributed_checker": None if zero is None else zero["checker_id"],
                "code": None if zero is None else zero["code"],
                "reason": None if zero is None else zero["reason"],
            }
        )
    print(json.dumps({"threshold": args.threshold, "controls": rows}, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
