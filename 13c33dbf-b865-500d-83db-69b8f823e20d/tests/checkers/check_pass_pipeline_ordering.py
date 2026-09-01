# forge-canary: FORGE-CANARY-6CAA841C1ADA9B611F786DD993BFAE95
from __future__ import annotations

import json
import pathlib

import verifier_lib

CHECKER_ID = "C4_pass_pipeline_ordering"

REWARD_TOLERANCE = 1.0e-06


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")
    log_path = verifier_lib.find_deliverable(workspace, "D3")
    entries = []
    for number, line in enumerate(log_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            return verifier_lib.result(CHECKER_ID, False, 0.0, "reward_log_line_unparseable", {"line": number})
    if not entries:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "reward_log_empty")

    harness = verifier_lib.harness_attempts()
    if not harness:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "harness_run_record_absent")
    recorded = {record["attempt_index"]: record for record in harness}

    expected_index = 1
    seen = {}
    for position, entry in enumerate(entries):
        index = entry.get("attempt_index")
        if index != expected_index:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "attempt_index_not_monotone_without_gaps",
                {"position": position, "expected": expected_index, "found": index},
            )
        expected_index += 1
        record = recorded.get(index)
        if record is None:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "reward_log_entry_absent_from_harness_record", {"attempt_index": index}
            )
        summary = entry.get("pipeline_summary")
        if not isinstance(summary, str) or not summary.strip():
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "pipeline_summary_missing", {"attempt_index": index}
            )
        if summary != record.get("pipeline_summary"):
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "pipeline_summary_diverges_from_harness_record",
                {"attempt_index": index, "claimed": summary, "recorded": record.get("pipeline_summary")},
            )
        if summary in seen:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "refuted_pipeline_summary_reintroduced",
                {"attempt_index": index, "first_seen_attempt": seen[summary], "pipeline_summary": summary},
            )
        seen[summary] = index
        if entry.get("semantics_verdict") != record.get("semantics_verdict"):
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "semantics_verdict_diverges_from_harness_record",
                {
                    "attempt_index": index,
                    "claimed": entry.get("semantics_verdict"),
                    "recorded": record.get("semantics_verdict"),
                },
            )
        claimed_reward = entry.get("measured_reward")
        if not isinstance(claimed_reward, (int, float)):
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "measured_reward_missing", {"attempt_index": index}
            )
        if abs(float(claimed_reward) - float(record.get("measured_reward", -1.0))) > REWARD_TOLERANCE:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "measured_reward_diverges_from_harness_record",
                {"attempt_index": index, "claimed": float(claimed_reward), "recorded": record.get("measured_reward")},
            )
    if len(entries) != len(harness):
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reward_log_length_diverges_from_harness_record",
            {"log_entries": len(entries), "harness_records": len(harness)},
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "attempt_indices_and_pipeline_history_reconcile",
        {"attempts": len(entries), "distinct_pipelines": len(seen)},
    )
