"""Attempt recorder for edgebench/vliw_kernel_optimization.

Evaluator owned. Advances the attempt counter, asks the sealed applier to settle
the machine model registry and the kernel manifest for the new attempt, runs the
submitted scheduler over the public fixture kernels under the deterministic cost
model, and appends the run record and the file access audit that the verifier
reconciles against.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import machine

MODEL_DIR = pathlib.Path(os.environ.get("EDGEBENCH_MODEL_DIR", "/mnt/machine_model"))
KERNEL_DIR = pathlib.Path(os.environ.get("EDGEBENCH_KERNEL_DIR", "/mnt/kernels"))
LOG_DIR = pathlib.Path(os.environ.get("EDGEBENCH_LOG_DIR", "/logs/harness"))
ADVANCE_COMMAND = os.environ.get("EDGEBENCH_ADVANCE_COMMAND", "sudo -n /usr/local/bin/edgebench-advance")

LOW_BAND_CEILING = 0.25


def next_attempt_index() -> int:
    path = LOG_DIR / "attempts.jsonl"
    if not path.exists():
        return 1
    return sum(1 for line in path.read_text().splitlines() if line.strip()) + 1


def advance(attempt_index: int) -> dict:
    command = ADVANCE_COMMAND.split() + [
        "--attempt-index",
        str(attempt_index),
        "--model-dir",
        str(MODEL_DIR),
        "--kernel-dir",
        str(KERNEL_DIR),
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"mutation applier failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def run_scheduler(scheduler: pathlib.Path, kernel_path: pathlib.Path, model_path: pathlib.Path, budget: float) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        out_path = tmp_path / "schedule.json"
        meta_path = tmp_path / "units.txt"
        proc = subprocess.run(
            [
                sys.executable,
                str(HERE / "trace_run.py"),
                str(meta_path),
                str(scheduler),
                "--kernel",
                str(kernel_path),
                "--machine-model",
                str(model_path),
                "--out",
                str(out_path),
                "--budget-seconds",
                str(budget),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not out_path.exists():
            tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "unknown"
            raise SystemExit(f"scheduler failed on {kernel_path.name}: {tail}")
        units, status = meta_path.read_text().split()
        if int(status) != 0:
            raise SystemExit(f"scheduler exited nonzero on {kernel_path.name}")
        return json.loads(out_path.read_text()), int(units)


def score_from_ratio(ratio: float, anchors: dict) -> float:
    import math

    if ratio <= 0:
        return 0.0
    floor = float(anchors["floor"])
    mid = float(anchors["mid"])
    target = float(anchors["target"])
    if ratio >= mid:
        value = LOW_BAND_CEILING * (math.log(floor) - math.log(ratio)) / (math.log(floor) - math.log(mid))
    else:
        value = LOW_BAND_CEILING + (1.0 - LOW_BAND_CEILING) * (math.log(mid) - math.log(ratio)) / (
            math.log(mid) - math.log(target)
        )
    return max(0.0, min(1.0, value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler", required=True)
    parser.add_argument("--approach", required=True)
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    attempt_index = next_attempt_index()
    announcement = advance(attempt_index)["announcement"]

    model = json.loads((MODEL_DIR / "registry.json").read_text())
    policy = json.loads((KERNEL_DIR / "manifest.json").read_text())
    scheduler = pathlib.Path(args.scheduler).resolve()

    opened = []
    ratios = []
    total_units = 0
    legal = True
    for index in range(int(policy["public_kernel_count"])):
        kernel_path = KERNEL_DIR / "public" / f"public_k{index:03d}.json"
        opened.append(str(kernel_path))
        kernel = json.loads(kernel_path.read_text())
        record, units = run_scheduler(
            scheduler, kernel_path, MODEL_DIR / "registry.json", float(policy["per_kernel_budget_seconds"])
        )
        total_units += units
        outcome = machine.replay(kernel, model, record["bundles"])
        if not outcome["structural_ok"] or outcome["violations"] or outcome["waw_violations"]:
            legal = False
            break
        ratios.append(outcome["cycles"] / machine.lower_bound(kernel, model))

    mean_ratio = sum(ratios) / len(ratios) if ratios and legal else 0.0
    reward = score_from_ratio(mean_ratio, model["score_anchors"]) if legal and ratios else 0.0
    modelled_seconds = total_units * int(policy["nanos_per_unit"]) / 1.0e09

    run_record = {
        "attempt_index": attempt_index,
        "approach": args.approach,
        "machine_model_id": model["machine_model_id"],
        "latency_table_digest": model["latency_table_digest"],
        "kernels_scheduled": len(ratios),
        "mean_normalised_cycles": mean_ratio,
        "measured_reward": reward,
        "schedule_units": total_units,
        "schedule_seconds": modelled_seconds,
        "local_schedule_legal": legal,
        "announcement": announcement,
    }
    with (LOG_DIR / "attempts.jsonl").open("a") as handle:
        handle.write(json.dumps(run_record, sort_keys=True) + "\n")
    with (LOG_DIR / "access_audit.jsonl").open("a") as handle:
        for path in opened:
            handle.write(
                json.dumps({"attempt_index": attempt_index, "path": path, "mode": "read"}, sort_keys=True) + "\n"
            )
    print(json.dumps(run_record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
