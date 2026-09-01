#!/usr/bin/env bash
# forge-canary: FORGE-CANARY-CB5DCD73188C60E84FADF07F58F31424
set -euo pipefail
# Reference solution for edgebench/vliw_kernel_optimization. Runs the full attempt schedule so every mutation lands, then emits the three deliverables.

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${EDGEBENCH_WORKSPACE:-/home/workspace}"
HARNESS_DIR="${EDGEBENCH_HARNESS_DIR:-/opt/edgebench/harness}"
MODEL_DIR="${EDGEBENCH_MODEL_DIR:-/mnt/machine_model}"
KERNEL_DIR="${EDGEBENCH_KERNEL_DIR:-/mnt/kernels}"
LOG_DIR="${EDGEBENCH_LOG_DIR:-/logs/harness}"
ATTEMPTS="${EDGEBENCH_REFERENCE_ATTEMPTS:-50}"
UUID="${EDGEBENCH_SUBMISSION_UUID:-$(python3 -c 'import uuid;print(uuid.uuid4())')}"

TREE="$WORKSPACE/reference_tree"
rm -rf "$TREE"
mkdir -p "$TREE/src"
cp "$HERE/reference_scheduler.py" "$TREE/src/scheduler.py"
cat > "$TREE/build.sh" <<'BUILD'
#!/usr/bin/env sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HERE/bin"
cp "$HERE/src/scheduler.py" "$HERE/bin/schedule"
chmod 0755 "$HERE/bin/schedule"
BUILD
chmod 0755 "$TREE/build.sh"

python3 - "$TREE" "$WORKSPACE/${UUID}_D1_scheduler_src.tar" <<'PY'
import pathlib, sys, tarfile

tree, archive = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
with tarfile.open(archive, "w") as handle:
    for path in sorted(tree.rglob("*")):
        handle.add(path, arcname=str(path.relative_to(tree)))
PY

sh "$TREE/build.sh"

python3 - "$TREE/bin/schedule" "$HARNESS_DIR/submit.py" "$ATTEMPTS" <<'PY'
import subprocess, sys

scheduler, harness, attempts = sys.argv[1], sys.argv[2], int(sys.argv[3])
stages = [
    "height priority list scheduling over the read after write graph",
    "height priority list scheduling with a memory port boost",
    "height priority list scheduling with an unpipelined unit boost",
    "best of the fixed priority variant set",
]
for attempt in range(1, attempts + 1):
    approach = f"{stages[min(attempt // 11, len(stages) - 1)]}, revision {attempt}"
    subprocess.run(
        [sys.executable, harness, "--scheduler", scheduler, "--approach", approach],
        check=True,
        stdout=subprocess.DEVNULL,
    )
PY

python3 - "$WORKSPACE" "$UUID" "$TREE/bin/schedule" "$MODEL_DIR" "$KERNEL_DIR" "$LOG_DIR" "$HARNESS_DIR" <<'PY'
import json, pathlib, subprocess, sys, tempfile

workspace = pathlib.Path(sys.argv[1])
uuid_value, scheduler = sys.argv[2], pathlib.Path(sys.argv[3])
model_dir, kernel_dir, log_dir, harness_dir = (pathlib.Path(p) for p in sys.argv[4:8])
sys.path.insert(0, str(harness_dir))
import machine

model = json.loads((model_dir / "registry.json").read_text())
policy = json.loads((kernel_dir / "manifest.json").read_text())

lines = []
for index in range(int(policy["public_kernel_count"])):
    kernel_path = kernel_dir / "public" / f"public_k{index:03d}.json"
    kernel = json.loads(kernel_path.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        out_path = tmp_path / "schedule.json"
        meta_path = tmp_path / "units.txt"
        canon_kernel = tmp_path / "kernel.json"
        canon_model = tmp_path / "model.json"
        canon_kernel.write_text(json.dumps(kernel, sort_keys=True))
        canon_model.write_text(json.dumps(model, sort_keys=True))
        subprocess.run(
            [
                sys.executable,
                str(harness_dir / "trace_run.py"),
                str(meta_path),
                str(scheduler),
                "--kernel",
                str(canon_kernel),
                "--machine-model",
                str(canon_model),
                "--out",
                str(out_path),
                "--budget-seconds",
                str(policy["per_kernel_budget_seconds"]),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            cwd=str(scheduler.parent.parent),
        )
        record = json.loads(out_path.read_text())
        units = int(meta_path.read_text().split()[0])
        record = json.loads(out_path.read_text())
        units = int(meta_path.read_text().split()[0])
        record = json.loads(out_path.read_text())
        units = int(meta_path.read_text().split()[0])
    outcome = machine.replay(kernel, model, record["bundles"])
    payload = {
        "kernel_id": kernel["kernel_id"],
        "bundle_count": record["bundle_count"],
        "bundles": record["bundles"],
        "claimed_cycles": outcome["cycles"],
        "latency_table_digest": model["latency_table_digest"],
        "machine_model_id": model["machine_model_id"],
        "schedule_seconds": units * int(policy["nanos_per_unit"]) / 1.0e09,
    }
    for field in ("architectural_register_ceiling", "war_rule"):
        if field in model:
            payload[field] = model[field]
    lines.append(json.dumps(payload, sort_keys=True))
(workspace / f"{uuid_value}_D2_schedule_bundle.jsonl").write_text("\n".join(lines) + "\n")

records = [json.loads(line) for line in (log_dir / "attempts.jsonl").read_text().splitlines() if line.strip()]
(workspace / f"{uuid_value}_D3_reward_log.jsonl").write_text(
    "".join(
        json.dumps(
            {
                "attempt_index": r["attempt_index"],
                "approach": r["approach"],
                "measured_reward": r["measured_reward"],
            },
            sort_keys=True,
        )
        + "\n"
        for r in records
    )
)
PY

echo "reference solution complete for submission ${UUID}"
