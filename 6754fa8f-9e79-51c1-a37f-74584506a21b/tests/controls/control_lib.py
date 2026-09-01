# forge-canary: FORGE-CANARY-5E66977EB92CE4DFF49566BA6EF73BDC
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TESTS = HERE.parent
BUNDLE = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS / "checkers"))

import kernels
import machine
import registry
import verifier_lib

CONTROL_UUID = "00000000-0000-4000-8000-000000000000"
SYNTHETIC_ATTEMPTS = 12

REFERENCE_SOURCE = BUNDLE / "solution" / "reference_scheduler.py"
BASELINE_SOURCE = TESTS / "private" / "baseline_scheduler.py"

BUILD_SCRIPT = """#!/usr/bin/env sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HERE/bin"
cp "$HERE/src/scheduler.py" "$HERE/bin/schedule"
chmod 0755 "$HERE/bin/schedule"
"""


def prepare_mounts(root: pathlib.Path, attempt_index: int) -> dict:
    state = registry.resolve_state(attempt_index)
    model_dir = root / "mnt" / "machine_model"
    kernel_dir = root / "mnt" / "kernels"
    model_dir.mkdir(parents=True, exist_ok=True)
    kernel_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "registry.json").write_text(json.dumps(state["registry"], indent=2, sort_keys=True) + "\n")
    (model_dir / "latency_manifest.json").write_text(json.dumps(state["manifest"], indent=2, sort_keys=True) + "\n")
    (model_dir / "MODEL.md").write_text(state["prose"])
    (model_dir / "preview_policy.json").write_text(json.dumps(state["preview"], indent=2, sort_keys=True) + "\n")
    (kernel_dir / "manifest.json").write_text(json.dumps(state["kernels"], indent=2, sort_keys=True) + "\n")
    verifier_lib.MODEL_DIR = model_dir
    verifier_lib.KERNEL_DIR = kernel_dir
    os.environ["EDGEBENCH_MODEL_DIR"] = str(model_dir)
    os.environ["EDGEBENCH_KERNEL_DIR"] = str(kernel_dir)
    verifier_lib._MEMO.clear()
    return state


def synthesize_harness(root: pathlib.Path, attempts: int = SYNTHETIC_ATTEMPTS) -> list:
    log_dir = root / "logs" / "harness"
    log_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(1, attempts + 1):
        records.append(
            {
                "attempt_index": index,
                "approach": f"candidate scheduling configuration {index}",
                "measured_reward": 0.02 * index,
                "mean_normalised_cycles": 4.0 - 0.1 * index,
            }
        )
    (log_dir / "attempts.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    (log_dir / "access_audit.jsonl").write_text(
        "".join(
            json.dumps(
                {"attempt_index": r["attempt_index"], "path": "/mnt/kernels/public", "mode": "read"},
                sort_keys=True,
            )
            + "\n"
            for r in records
        )
    )
    verifier_lib.LOG_DIR = log_dir
    return records


def write_scheduler_tar(workspace: pathlib.Path, source: str, readme: str = "") -> pathlib.Path:
    workspace.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(tempfile.mkdtemp(prefix="vko_control_")) / "tree"
    (staging / "src").mkdir(parents=True, exist_ok=True)
    (staging / "src" / "scheduler.py").write_text(source)
    (staging / "build.sh").write_text(BUILD_SCRIPT)
    if readme:
        (staging / "README.md").write_text(readme)
    archive = workspace / f"{CONTROL_UUID}_D1_scheduler_src.tar"
    with tarfile.open(archive, "w") as handle:
        for path in sorted(staging.rglob("*")):
            handle.add(path, arcname=str(path.relative_to(staging)))
    shutil.rmtree(staging.parent, ignore_errors=True)
    return archive


def write_reward_log(workspace: pathlib.Path, records: list) -> None:
    lines = [
        json.dumps(
            {
                "attempt_index": record["attempt_index"],
                "approach": record["approach"],
                "measured_reward": record["measured_reward"],
            },
            sort_keys=True,
        )
        for record in records
    ]
    (workspace / f"{CONTROL_UUID}_D3_reward_log.jsonl").write_text("\n".join(lines) + "\n")


def build_entry(workspace: pathlib.Path) -> pathlib.Path:
    tree = verifier_lib.scheduler_tree(workspace)
    if not tree["ok"]:
        raise RuntimeError(tree["error"])
    return tree["entry"]


_UNSET = object()


def emit_schedule_bundle(
    workspace: pathlib.Path,
    scheduling_model: dict | None = None,
    declared_digest: str | None = None,
    declared_machine_model_id: str | None = None,
    repeat_each: int = 1,
    declared_register_ceiling: object = _UNSET,
    declared_war_rule: object = _UNSET,
) -> None:
    live = verifier_lib.live_registry()
    model = scheduling_model or live
    entry = build_entry(workspace)
    policy = verifier_lib.live_kernel_policy()
    ceiling = (
        live.get("architectural_register_ceiling")
        if declared_register_ceiling is _UNSET
        else declared_register_ceiling
    )
    war_rule = live.get("war_rule") if declared_war_rule is _UNSET else declared_war_rule
    lines = []
    for kernel in verifier_lib.public_kernels():
        record, units = verifier_lib.run_scheduler(
            entry, kernel, model, float(policy["per_kernel_budget_seconds"])
        )
        outcome = machine.replay(kernel, live, record["bundles"])
        payload = {
            "kernel_id": kernel["kernel_id"],
            "bundle_count": record["bundle_count"],
            "bundles": record["bundles"],
            "claimed_cycles": outcome["cycles"] if outcome["cycles"] is not None else record["claimed_cycles"],
            "latency_table_digest": declared_digest or live["latency_table_digest"],
            "machine_model_id": declared_machine_model_id or live["machine_model_id"],
            "schedule_seconds": units * registry.NANOS_PER_UNIT / 1.0e09,
        }
        if ceiling is not None:
            payload["architectural_register_ceiling"] = ceiling
        if war_rule is not None:
            payload["war_rule"] = war_rule
        for _ in range(repeat_each):
            lines.append(json.dumps(payload, sort_keys=True))
    (workspace / f"{CONTROL_UUID}_D2_schedule_bundle.jsonl").write_text("\n".join(lines) + "\n")


def reference_source() -> str:
    return REFERENCE_SOURCE.read_text()


def baseline_source() -> str:
    return BASELINE_SOURCE.read_text()
