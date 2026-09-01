#!/usr/bin/env bash
# forge-canary: FORGE-CANARY-8C9E0B8D2FBCC6E24B34F86E4C4C76B9
set -euo pipefail
# Reference solution for edgebench/jagua_nesting_optimization. Runs the full attempt schedule so all four mutations land, then emits the three deliverables against the settled live state.

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${EDGEBENCH_WORKSPACE:-/home/workspace}"
HARNESS="${EDGEBENCH_HARNESS:-/opt/edgebench/harness/submit.py}"
ATTEMPTS="${EDGEBENCH_REFERENCE_ATTEMPTS:-50}"
UUID="${EDGEBENCH_SUBMISSION_UUID:-$(python3 -c 'import uuid;print(uuid.uuid4())')}"

mkdir -p "$WORKSPACE"
NESTER_TAR="$WORKSPACE/${UUID}_D1_nester_src.tar"
python3 -c "
import pathlib, sys, tarfile
tree, out = pathlib.Path(sys.argv[1]), sys.argv[2]
with tarfile.open(out, 'w') as archive:
    archive.add(tree / 'nester', arcname='nester')
" "$HERE/reference_nester" "$NESTER_TAR"

python3 - "$NESTER_TAR" "$HARNESS" "$ATTEMPTS" <<'PY'
import subprocess, sys

nester_path, harness_path, attempts = sys.argv[1], sys.argv[2], int(sys.argv[3])
stages = [
    "bounding box first fit decreasing over the authoritative rotation set",
    "contour anchored bottom left fill on the exact outlines with a one cell separation pad",
    "contour anchored bottom left fill with drop and slide refinement over every authoritative rotation",
]
for attempt in range(1, attempts + 1):
    stage = stages[min(attempt * len(stages) // (attempts + 1), len(stages) - 1)]
    approach = f"{stage}, revision {attempt}"
    subprocess.run(
        [sys.executable, harness_path, "--nester", nester_path, "--approach", approach],
        check=True,
        stdout=subprocess.DEVNULL,
    )
PY

python3 - "$WORKSPACE" "$UUID" "$HERE" <<'PY'
import json, os, pathlib, subprocess, sys, tempfile

workspace, uuid_value, here = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
instance_dir = pathlib.Path(os.environ.get("EDGEBENCH_INSTANCE_DIR", "/mnt/instances"))
log_dir = pathlib.Path(os.environ.get("EDGEBENCH_LOG_DIR", "/logs/harness"))
nanos_per_line_event = 25

manifest = json.loads((instance_dir / "manifest.json").read_text())
sys.path.insert(0, str(here / "reference_nester"))

probe = '''
import importlib, json, pathlib, sys
tree_root, instance_path, output_path, budget, meta_path = sys.argv[1:6]
sys.path.insert(0, tree_root)
module = importlib.import_module("nester.main")
count = 0
def tracer(frame, event, arg):
    global count
    if event == "line":
        count += 1
    return tracer
sys.settrace(tracer)
try:
    module.main(["--instance", instance_path, "--output", output_path, "--budget-seconds", budget])
finally:
    sys.settrace(None)
pathlib.Path(meta_path).write_text(json.dumps({"line_events": count}))
'''

rows = []
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = pathlib.Path(tmp)
    probe_path = tmp_path / "probe.py"
    probe_path.write_text(probe)
    for ordinal in range(manifest["public_instance_count"]):
        instance_id = f"public-{ordinal:03d}"
        output_path = tmp_path / f"{instance_id}.json"
        meta_path = tmp_path / f"{instance_id}.meta"
        subprocess.run(
            [
                sys.executable,
                str(probe_path),
                str(here / "reference_nester"),
                str(instance_dir / "public" / instance_id),
                str(output_path),
                str(manifest["per_instance_budget_seconds"]),
                str(meta_path),
            ],
            check=True,
        )
        payload = json.loads(output_path.read_text())
        payload["solve_seconds"] = json.loads(meta_path.read_text())["line_events"] * nanos_per_line_event / 1.0e09
        rows.append(payload)

(workspace / f"{uuid_value}_D2_placement_bundle.jsonl").write_text(
    "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
)

records = [json.loads(line) for line in (log_dir / "attempts.jsonl").read_text().splitlines() if line.strip()]
(workspace / f"{uuid_value}_D3_reward_log.jsonl").write_text(
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
