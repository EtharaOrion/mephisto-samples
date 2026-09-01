# forge-canary: FORGE-CANARY-F18CDD9D27957C9FD24743C43CBE6FEC
from __future__ import annotations

import json
import pathlib

import verifier_lib

CHECKER_ID = "C7_attempt_ordering"

REWARD_RECONCILE_TOLERANCE = 1.0e-06


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
    by_index = {record["attempt_index"]: record for record in harness}

    expected = 1
    seen_approaches = {}
    for position, entry in enumerate(entries):
        index = entry.get("attempt_index")
        if index != expected:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "attempt_index_not_monotone_without_gaps",
                {"position": position, "expected": expected, "found": index},
            )
        expected += 1

        record = by_index.get(index)
        if record is None:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "reward_log_entry_absent_from_harness_record", {"attempt_index": index}
            )
        approach = entry.get("approach")
        if not isinstance(approach, str) or not approach.strip():
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "approach_summary_missing", {"attempt_index": index}
            )
        if approach != record["approach"]:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "approach_summary_diverges_from_harness_record",
                {"attempt_index": index, "claimed": approach, "recorded": record["approach"]},
            )
        if approach in seen_approaches:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "refuted_approach_reintroduced",
                {"attempt_index": index, "first_seen_attempt": seen_approaches[approach], "approach": approach},
            )
        seen_approaches[approach] = index

        claimed = entry.get("measured_reward")
        if not isinstance(claimed, (int, float)):
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "measured_reward_missing", {"attempt_index": index}
            )
        recorded = float(record["measured_reward"])
        if abs(float(claimed) - recorded) > REWARD_RECONCILE_TOLERANCE * max(1.0, recorded):
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "measured_reward_diverges_from_harness_record",
                {"attempt_index": index, "claimed": float(claimed), "recorded": recorded},
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
        "attempt_indices_reconcile_with_the_harness_record",
        {"attempts": len(entries), "distinct_approaches": len(seen_approaches)},
    )
