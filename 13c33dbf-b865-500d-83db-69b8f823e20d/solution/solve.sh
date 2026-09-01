#!/usr/bin/env bash
# forge-canary: FORGE-CANARY-22582D8CBA73BFC7E63DCE10B60DAC9D
set -euo pipefail
# Reference solution for edgebench/arc_compiler_runtime. Runs the full attempt schedule so both registry moves land, then emits the four deliverables.

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${EDGEBENCH_WORKSPACE:-/home/workspace}"
HARNESS="${EDGEBENCH_HARNESS:-/opt/edgebench/harness/submit.py}"
ATTEMPTS="${EDGEBENCH_REFERENCE_ATTEMPTS:-50}"
UUID="${EDGEBENCH_SUBMISSION_UUID:-$(python3 -c 'import uuid;print(uuid.uuid4())')}"

SOURCE="$WORKSPACE/compiler/src"
mkdir -p "$SOURCE"
cp "$HERE/reference/frontend.py" "$HERE/reference/runtime.py" "$HERE/reference/lowering.py" "$HERE/reference/pipeline.py" "$SOURCE/"

python3 - "$SOURCE" "$HARNESS" "$ATTEMPTS" <<'PY'
import subprocess, sys

source, harness, attempts = sys.argv[1], sys.argv[2], int(sys.argv[3])
stages = [
    "stack lowering with frame homed locals and no folding",
    "register homed locals with constant folding and dead code elimination",
    "register homed locals with loop rotation and compare branch fusion",
    "register homed locals with argument marshalling resolved from the live registry",
]
for attempt in range(1, attempts + 1):
    summary = f"{stages[min(attempt // 9, len(stages) - 1)]}, revision {attempt}"
    subprocess.run(
        [sys.executable, harness, "--source", source, "--pipeline-summary", summary],
        check=True,
        stdout=subprocess.DEVNULL,
    )
PY

python3 - "$WORKSPACE" "$UUID" "$SOURCE" <<'PY'
import json, os, pathlib, sys, tarfile

workspace, uuid_value, source = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
log_dir = pathlib.Path(os.environ.get("EDGEBENCH_LOG_DIR", "/logs/harness"))
sys.path.insert(0, os.path.dirname(os.environ.get("EDGEBENCH_MEASURE", "/opt/edgebench/harness/measure.py")))
sys.path.insert(0, str(source))
import measure
import pipeline

archive = workspace / f"{uuid_value}_D1_compiler_src.tar"
with tarfile.open(archive, "w") as handle:
    for path in sorted(source.glob("*.py")):
        handle.add(path, arcname=f"compiler/src/{path.name}")

outcome = measure.measure(source)
(workspace / f"{uuid_value}_D2_suite_report.json").write_text(
    json.dumps(
        {
            "weighted_pass_fraction": outcome["weighted_pass_fraction"],
            "raw_passed": outcome["raw_passed"],
            "raw_total": outcome["raw_total"],
            "isa_revision_id": outcome["isa_revision_id"],
            "calling_convention_digest": outcome["calling_convention_digest"],
            "miscompile_count": outcome["miscompile_count"],
            "passed_by_category": outcome["passed_by_category"],
            "unaccelerated_programs": outcome["unaccelerated_programs"],
            "instruction_census_digest": outcome["instruction_census_digest"],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n"
)

records = [json.loads(line) for line in (log_dir / "attempts.jsonl").read_text().splitlines() if line.strip()]
(workspace / f"{uuid_value}_D3_reward_log.jsonl").write_text(
    "".join(
        json.dumps(
            {
                "attempt_index": r["attempt_index"],
                "pipeline_summary": r["pipeline_summary"],
                "semantics_verdict": r["semantics_verdict"],
                "measured_reward": r["measured_reward"],
            },
            sort_keys=True,
        )
        + "\n"
        for r in records
    )
)
(workspace / f"{uuid_value}_D4_pass_pipeline.json").write_text(
    json.dumps(pipeline.describe_pipeline(), indent=2, sort_keys=True) + "\n"
)
PY

echo "reference solution complete for submission ${UUID}"
