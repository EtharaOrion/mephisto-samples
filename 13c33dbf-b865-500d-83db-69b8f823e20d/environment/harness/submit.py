"""Attempt recorder for edgebench/arc_compiler_runtime.

Evaluator owned. Advances the attempt counter, asks the sealed mutation applier to settle
the instruction set and calling convention registries for the new attempt, measures the
submitted compiler against the public smoke slice only, and appends the run record and the
file access audit that the verifier reconciles against.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import measure

LOG_DIR = pathlib.Path(os.environ.get("EDGEBENCH_LOG_DIR", "/logs/harness"))
SUITE_DIR = pathlib.Path(os.environ.get("EDGEBENCH_SUITE_DIR", "/logs/suite"))
ISA_DIR = pathlib.Path(os.environ.get("EDGEBENCH_ISA_DIR", "/mnt/isa"))
ADVANCE_COMMAND = os.environ.get("EDGEBENCH_ADVANCE_COMMAND", "sudo -n /usr/local/bin/edgebench-advance")


def next_attempt_index() -> int:
    path = LOG_DIR / "attempts.jsonl"
    if not path.exists():
        return 1
    return sum(1 for line in path.read_text().splitlines() if line.strip()) + 1


def advance(attempt_index: int) -> dict:
    command = ADVANCE_COMMAND.split() + ["--attempt-index", str(attempt_index), "--isa-dir", str(ISA_DIR)]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"mutation applier failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--pipeline-summary", required=True)
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    attempt_index = next_attempt_index()
    announcement = advance(attempt_index).get("announcement")
    outcome = measure.measure(pathlib.Path(args.source).resolve())

    if outcome["miscompile_count"]:
        verdict = "miscompile_detected"
    elif outcome["raw_passed"] == outcome["raw_total"]:
        verdict = "exact"
    else:
        verdict = "incomplete"

    record = {
        "attempt_index": attempt_index,
        "pipeline_summary": args.pipeline_summary,
        "semantics_verdict": verdict,
        "measured_reward": outcome["weighted_pass_fraction"],
        "raw_passed": outcome["raw_passed"],
        "raw_total": outcome["raw_total"],
        "miscompile_count": outcome["miscompile_count"],
        "isa_revision_id": outcome["isa_revision_id"],
        "calling_convention_digest": outcome["calling_convention_digest"],
        "total_instructions": outcome["total_instructions"],
        "passed_by_category": outcome["passed_by_category"],
        "unaccelerated_programs": outcome["unaccelerated_programs"],
        "instruction_census_digest": outcome["instruction_census_digest"],
        "announcement": announcement,
    }
    with (LOG_DIR / "attempts.jsonl").open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    with (LOG_DIR / "access_audit.jsonl").open("a") as handle:
        for path in outcome["opened"]:
            handle.write(json.dumps({"attempt_index": attempt_index, "path": path, "mode": "read"}, sort_keys=True) + "\n")
    with (SUITE_DIR / "results.jsonl").open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")

    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
