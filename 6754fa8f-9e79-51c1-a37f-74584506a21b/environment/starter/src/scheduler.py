#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib


def serial_bundles(kernel: dict, model: dict) -> list:
    stride = max(int(value) for value in model["latencies"].values())
    bundles: list = []
    for op in kernel["ops"]:
        while len(bundles) % stride:
            bundles.append([])
        bundles.append([op["id"]])
    return bundles


def claimed_cycles(kernel: dict, model: dict, bundles: list) -> int:
    issue = {entry: cycle for cycle, bundle in enumerate(bundles) for entry in bundle}
    retire = max(issue[op["id"]] + int(model["latencies"][op["op"]]) for op in kernel["ops"])
    return max(len(bundles), retire)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--machine-model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--budget-seconds", type=float, required=True)
    args = parser.parse_args()

    kernel = json.loads(pathlib.Path(args.kernel).read_text())
    model = json.loads(pathlib.Path(args.machine_model).read_text())
    bundles = serial_bundles(kernel, model)
    record = {
        "kernel_id": kernel["kernel_id"],
        "bundle_count": len(bundles),
        "bundles": bundles,
        "claimed_cycles": claimed_cycles(kernel, model, bundles),
    }
    # Mirror scheduling-relevant pins straight from the model record so the
    # emitted schedule always names the constraints it was built against.
    for field in ("architectural_register_ceiling", "war_rule"):
        if field in model:
            record[field] = model[field]
    pathlib.Path(args.out).write_text(json.dumps(record, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
