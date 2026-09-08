"""Workspace hazard preview. Convenience only, never the graded authority.

The preview reports the hazard classes the live preview policy enables. The
graded replay always checks every class, so a preview that reports clean is not
a proof that a schedule is legal.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import machine

MODEL_DIR = pathlib.Path(os.environ.get("EDGEBENCH_MODEL_DIR", "/mnt/machine_model"))


def preview(kernel: dict, model: dict, bundles: list, reports_register_waw: bool) -> dict:
    outcome = machine.replay(kernel, model, bundles)
    findings = list(outcome["violations"])
    if reports_register_waw:
        findings.extend(outcome["waw_violations"])
    return {
        "kernel_id": kernel["kernel_id"],
        "structural_ok": outcome["structural_ok"],
        "cycles": outcome["cycles"],
        "bundle_count": outcome["bundle_count"],
        "findings": findings,
        "clean": outcome["structural_ok"] and not findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--schedule", required=True)
    args = parser.parse_args()

    kernel = json.loads(pathlib.Path(args.kernel).read_text())
    model = json.loads((MODEL_DIR / "registry.json").read_text())
    policy = json.loads((MODEL_DIR / "preview_policy.json").read_text())
    record = json.loads(pathlib.Path(args.schedule).read_text())
    print(
        json.dumps(
            preview(kernel, model, record["bundles"], bool(policy["reports_register_waw"])),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
