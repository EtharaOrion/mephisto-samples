# forge-canary: FORGE-CANARY-22582D8CBA73BFC7E63DCE10B60DAC9D
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TESTS = HERE.parent
BUNDLE = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS / "checkers"))

import registry
import verifier_lib

CONTROL_UUID = "00000000-0000-4000-8000-000000000000"
SYNTHETIC_ATTEMPTS = 34

REFERENCE_DIR = BUNDLE / "solution" / "reference"


def prepare_mounts(root: pathlib.Path, attempt_index: int) -> dict:
    state = registry.resolve_state(attempt_index)
    isa_dir = root / "mnt" / "isa"
    isa_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (("isa.json", state["isa"]), ("abi.json", state["abi"]), ("intrinsics.json", state["intrinsics"])):
        (isa_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    verifier_lib.ISA_DIR = isa_dir
    os.environ["EDGEBENCH_ISA_DIR"] = str(isa_dir)
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
                "pipeline_summary": f"candidate lowering and pass ordering {index}",
                "semantics_verdict": "exact",
                "measured_reward": 0.1 + index * 0.005,
            }
        )
    (log_dir / "attempts.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    (log_dir / "access_audit.jsonl").write_text(
        "".join(
            json.dumps({"attempt_index": r["attempt_index"], "path": "/mnt/isa/public", "mode": "read"}, sort_keys=True) + "\n"
            for r in records
        )
    )
    verifier_lib.LOG_DIR = log_dir
    return records


def write_sources(workspace: pathlib.Path, files: dict) -> pathlib.Path:
    workspace.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(tempfile.mkdtemp(prefix="control_src_")) / "compiler" / "src"
    staging.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (staging / name).write_text(text)
    archive = workspace / f"{CONTROL_UUID}_D1_compiler_src.tar"
    with tarfile.open(archive, "w") as handle:
        for path in sorted(staging.iterdir()):
            handle.add(path, arcname=f"compiler/src/{path.name}")
    return staging


def reference_files(patch=None) -> dict:
    files = {name: (REFERENCE_DIR / name).read_text() for name in ("frontend.py", "runtime.py", "lowering.py", "pipeline.py")}
    return patch(files) if patch else files


def write_reward_log(workspace: pathlib.Path, records: list) -> None:
    lines = [
        json.dumps(
            {
                "attempt_index": r["attempt_index"],
                "pipeline_summary": r["pipeline_summary"],
                "semantics_verdict": r["semantics_verdict"],
                "measured_reward": r["measured_reward"],
            },
            sort_keys=True,
        )
        for r in records
    ]
    (workspace / f"{CONTROL_UUID}_D3_reward_log.jsonl").write_text("\n".join(lines) + "\n")


def write_report(workspace: pathlib.Path, payload: dict) -> None:
    (workspace / f"{CONTROL_UUID}_D2_suite_report.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_pipeline(workspace: pathlib.Path, payload: dict) -> None:
    (workspace / f"{CONTROL_UUID}_D4_pass_pipeline.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def honest_report_payload(workspace: pathlib.Path) -> dict:
    import check_category_breakdown_binding
    import check_instruction_census_binding
    import check_speed_anchor_binding

    verifier_lib._MEMO.pop(f"public_measure:{workspace}", None)
    public = verifier_lib.public_measure(workspace)
    payload = {
        "weighted_pass_fraction": public.get("weighted_pass_fraction", 0.0),
        "raw_passed": public.get("raw_passed", 0),
        "raw_total": public.get("raw_total", 0),
        "isa_revision_id": verifier_lib.live_isa()["isa_revision_id"],
        "calling_convention_digest": verifier_lib.live_abi()["calling_convention_digest"],
        "miscompile_count": public.get("miscompile_count", 0),
    }
    if public.get("ok"):
        rows = public["graded"]["rows"]
        payload["passed_by_category"] = check_category_breakdown_binding.recompute(rows)
        payload["unaccelerated_programs"] = check_speed_anchor_binding.recompute(
            public["graded"], public["baseline_graded"]
        )
        payload["instruction_census_digest"] = check_instruction_census_binding.replayed_census_digest(rows)
    return payload


def honest_pipeline_payload(workspace: pathlib.Path) -> dict:
    public = verifier_lib.public_measure(workspace)
    declared = public.get("compiled", {}).get("pipeline")
    return declared if declared else {"passes": [], "pass_preconditions": {}, "pass_invariants": {}}


def honest_artifacts(workspace: pathlib.Path) -> None:
    write_report(workspace, honest_report_payload(workspace))
    write_pipeline(workspace, honest_pipeline_payload(workspace))
