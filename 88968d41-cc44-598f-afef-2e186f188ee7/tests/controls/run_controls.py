# forge-canary: FORGE-CANARY-1254CEC55E3E94C4E944B7B7CCD8B8F1
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
import registry
import score
import verifier_lib

CONTROL_MODULES = (
    "control_no_op",
    "control_stale_property_predicate",
    "control_decoy",
    "control_list_all",
    "control_obvious_wrong",
    "control_stale_translation_anchor",
    "control_stale_digest_join",
    "control_stale_pair_sum_order",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=registry.CONTROL_THRESHOLD)
    args = parser.parse_args()

    rows = []
    failures = 0
    for name in CONTROL_MODULES:
        module = importlib.import_module(name)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            control_lib.prepare_geometry(root, control_lib.CONTROL_ATTEMPT_INDEX)
            records = control_lib.synthesize_harness(root)
            workspace = root / "workspace"
            module.build(workspace, records)
            verifier_lib._MEMO.pop(f"recompute:{workspace.resolve()}", None)
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
                "reason": None if zero is None else zero["reason"],
            }
        )

    print(json.dumps({"threshold": args.threshold, "controls": rows}, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
