"""Attempt recorder for edgebench/jagua_nesting_optimization.

Evaluator owned. Advances the attempt counter, asks the sealed mutation applier
to settle the instance mount and the carrier authority registry for the new
attempt, builds and runs the submitted nester over the public practice sweep
only, and appends the run record and the file access audit that the verifier
reconciles against.

Solve seconds are modelled rather than timed. The nester runs under an
interpreter line event tracer, the event count is the solve cost in units, and
each unit is charged at a fixed nanosecond rate, so the same submission always
records the same seconds on every host.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile

INSTANCE_DIR = pathlib.Path(os.environ.get("EDGEBENCH_INSTANCE_DIR", "/mnt/instances"))
AUTHORITY_DIR = pathlib.Path(os.environ.get("EDGEBENCH_AUTHORITY_DIR", "/mnt/authority"))
LOG_DIR = pathlib.Path(os.environ.get("EDGEBENCH_LOG_DIR", "/logs/harness"))
WORKSPACE = pathlib.Path(os.environ.get("EDGEBENCH_WORKSPACE", "/home/workspace"))
PRIVATE_COMMAND = os.environ.get("EDGEBENCH_PRIVATE_COMMAND", "sudo -n /usr/local/bin/edgebench-private")

NANOS_PER_LINE_EVENT = 25

RUN_PROBE = '''
import importlib, json, os, pathlib, sys

tree_root, entry, instance_path, output_path, budget, meta_path = sys.argv[1:7]
sys.path.insert(0, tree_root)
module = importlib.import_module(entry)
count = 0


def tracer(frame, event, arg):
    global count
    if event == "line":
        count += 1
    return tracer


argv = ["--instance", instance_path, "--output", output_path, "--budget-seconds", budget]
sys.settrace(tracer)
try:
    status = module.main(argv)
finally:
    sys.settrace(None)
pathlib.Path(meta_path).write_text(json.dumps({"line_events": count, "status": int(status or 0)}))
'''


def next_attempt_index() -> int:
    path = LOG_DIR / "attempts.jsonl"
    if not path.exists():
        return 1
    return sum(1 for line in path.read_text().splitlines() if line.strip()) + 1


def private(mode: str, attempt_index: int, extra: list[str]) -> dict:
    command = PRIVATE_COMMAND.split() + [
        mode,
        "--attempt-index",
        str(attempt_index),
        "--instance-dir",
        str(INSTANCE_DIR),
        "--authority-dir",
        str(AUTHORITY_DIR),
    ] + extra
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"sealed applier failed in mode {mode}: {proc.stderr.strip()}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def extract(tar_path: pathlib.Path, destination: pathlib.Path) -> tuple[pathlib.Path, str]:
    with tarfile.open(tar_path, "r:*") as archive:
        archive.extractall(destination, filter="data")
    for root in [destination] + [p for p in destination.iterdir() if p.is_dir()]:
        if (root / "nester" / "main.py").exists():
            return root, "nester.main"
    raise SystemExit("submitted archive carries no nester/main.py entry module")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nester", required=True)
    parser.add_argument("--approach", required=True)
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    attempt_index = next_attempt_index()
    advance = private("advance", attempt_index, [])
    manifest = json.loads((INSTANCE_DIR / "manifest.json").read_text())
    authority = json.loads((AUTHORITY_DIR / "authority.json").read_text())
    budget = manifest["per_instance_budget_seconds"]

    opened = []
    per_instance = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        root, entry = extract(pathlib.Path(args.nester).resolve(), tmp_path / "tree")
        build = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", "-f", str(root)], capture_output=True, text=True
        )
        if build.returncode != 0:
            raise SystemExit("submitted nester source tree does not build")
        probe = tmp_path / "run_probe.py"
        probe.write_text(RUN_PROBE)
        placement_dir = tmp_path / "placements"
        placement_dir.mkdir()
        for ordinal in range(manifest["public_instance_count"]):
            instance_id = f"public-{ordinal:03d}"
            instance_path = INSTANCE_DIR / "public" / instance_id
            output_path = placement_dir / f"{instance_id}.json"
            meta_path = tmp_path / f"{instance_id}.meta"
            opened.append(str(instance_path / "outlines.geom"))
            opened.append(str(instance_path / "parts.csv"))
            proc = subprocess.run(
                [
                    sys.executable,
                    str(probe),
                    str(root),
                    entry,
                    str(instance_path),
                    str(output_path),
                    f"{budget}",
                    str(meta_path),
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                tail = proc.stderr.strip().splitlines()
                raise SystemExit(f"nester raised on {instance_id}: {tail[-1] if tail else 'unknown'}")
            events = json.loads(meta_path.read_text())
            seconds = events["line_events"] * NANOS_PER_LINE_EVENT / 1.0e09
            per_instance.append({"instance_id": instance_id, "solve_seconds": seconds})
            (WORKSPACE / "last_placements").mkdir(parents=True, exist_ok=True)
            (WORKSPACE / "last_placements" / f"{instance_id}.json").write_text(output_path.read_text())
        graded = private(
            "evaluate", attempt_index, ["--placement-dir", str(placement_dir)]
        )

    record = {
        "attempt_index": attempt_index,
        "approach": args.approach,
        "measured_reward": graded["measured_reward"],
        "graded_feasible_instances": graded["graded_feasible_instances"],
        "instances": graded["instances"],
        "per_instance": per_instance,
        "total_solve_seconds": sum(item["solve_seconds"] for item in per_instance),
        "sheet_stock_profile_id": manifest["sheet_stock_profile_id"],
        "authority_revision_id": authority["authority_revision_id"],
        "announcement": advance.get("announcement"),
    }
    with (LOG_DIR / "attempts.jsonl").open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    with (LOG_DIR / "access_audit.jsonl").open("a") as handle:
        for path in opened:
            handle.write(
                json.dumps({"attempt_index": attempt_index, "path": path, "mode": "read"}, sort_keys=True) + "\n"
            )

    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
