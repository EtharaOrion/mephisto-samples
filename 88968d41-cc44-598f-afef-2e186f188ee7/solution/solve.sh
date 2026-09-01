#!/usr/bin/env bash
# forge-canary: FORGE-CANARY-C3A4D0A724B2C1B4ABB13DD5F51313F5
set -euo pipefail
# Reference solution for edgebench/cap_set_extremal_construction. Runs the full attempt schedule so all three mutations land, then emits the three deliverables.

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${EDGEBENCH_WORKSPACE:-/home/workspace}"
HARNESS="${EDGEBENCH_HARNESS:-/opt/edgebench/harness/submit.py}"
ATTEMPTS="${EDGEBENCH_REFERENCE_ATTEMPTS:-40}"
UUID="${EDGEBENCH_SUBMISSION_UUID:-$(python3 -c 'import uuid;print(uuid.uuid4())')}"

mkdir -p "$WORKSPACE"
CONSTRUCT="$WORKSPACE/${UUID}_D1_construct.py"

python3 - "$HERE/reference_construct.py" "$WORKSPACE" "$CONSTRUCT" "$HARNESS" "$ATTEMPTS" <<'PY'
import pathlib, subprocess, sys

source_path, workspace, construct_path, harness_path, attempts = sys.argv[1:6]
source = pathlib.Path(source_path).read_text()
staging = pathlib.Path(workspace) / "reference_stage.py"
stages = [
    (0, "parabola lifted from the extension subfield with a single greedy augmentation pass"),
    (1, "parabola lifting with a short iterated repair schedule over the augmentation order"),
    (4, "parabola lifting with a widened repair kick and a reshuffled candidate order"),
]
for attempt in range(1, int(attempts)):
    rounds, label = stages[min(attempt // 14, len(stages) - 1)]
    staging.write_text(source.replace("REFERENCE_ROUNDS = 4", f"REFERENCE_ROUNDS = {rounds}"))
    subprocess.run(
        [sys.executable, harness_path, "--construct", str(staging), "--approach", f"{label}, revision {attempt}"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
staging.unlink()
pathlib.Path(construct_path).write_text(source)
subprocess.run(
    [
        sys.executable,
        harness_path,
        "--construct",
        construct_path,
        "--approach",
        "parabola lifting with the full iterated repair schedule under the live predicate",
    ],
    check=True,
    stdout=subprocess.DEVNULL,
)
PY

python3 - "$WORKSPACE" "$UUID" "$CONSTRUCT" <<'PY'
import importlib.util, json, os, pathlib, sys, time

workspace, submission_uuid, construct_path = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
geometry_dir = pathlib.Path(os.environ.get("EDGEBENCH_GEOMETRY_DIR", "/mnt/geometry"))
log_dir = pathlib.Path(os.environ.get("EDGEBENCH_LOG_DIR", "/logs/harness"))

geometry = json.loads((geometry_dir / "manifest.json").read_text())
predicate = json.loads((geometry_dir / "predicate.json").read_text())

spec = importlib.util.spec_from_file_location("reference_submission", str(construct_path))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

started = time.monotonic()
points = module.construct({"geometry": geometry, "predicate": predicate})
search_seconds = time.monotonic() - started

(workspace / f"{submission_uuid}_D2_construction_bundle.json").write_text(
    json.dumps(
        {
            "ambient_params_id": geometry["ambient_params_id"],
            "predicate_digest": predicate["predicate_digest"],
            "point_count": len(points),
            "points": points,
            "certificate": module.certificate(points, geometry, predicate),
            "search_seconds": round(search_seconds, 6),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)

records = [json.loads(line) for line in (log_dir / "attempts.jsonl").read_text().splitlines() if line.strip()]
(workspace / f"{submission_uuid}_D3_reward_log.jsonl").write_text(
    "".join(
        json.dumps(
            {
                "attempt_index": record["attempt_index"],
                "approach": record["approach"],
                "measured_reward": record["measured_reward"],
            },
            sort_keys=True,
        )
        + "\n"
        for record in records
    )
)
PY

echo "reference solution complete for submission ${UUID}"
