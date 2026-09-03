# forge-canary: FORGE-CANARY-1254CEC55E3E94C4E944B7B7CCD8B8F1
from __future__ import annotations

import json
import pathlib

import verifier_lib

CHECKER_ID = "C4_attempt_ordering"

REWARD_RECONCILE_TOLERANCE = 1.0e-06


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    log_path = verifier_lib.find_deliverable(workspace, "D3")
    entries = []
    for line_number, line in enumerate(log_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "reward_log_line_unparseable", {"line": line_number}
            )
    if not entries:
        return verifier_lib.result(CHECKER_ID, False, 0.0, "reward_log_empty")

    harness = verifier_lib.harness_attempts()
    record_available = bool(harness)
    harness_by_index = {record["attempt_index"]: record for record in harness}

    expected = 1
    seen = {}
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

        record = harness_by_index.get(index)
        if record_available and record is None:
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "reward_log_entry_absent_from_harness_record", {"attempt_index": index}
            )

        claimed_reward = entry.get("measured_reward")
        if not isinstance(claimed_reward, (int, float)) or isinstance(claimed_reward, bool):
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "measured_reward_missing", {"attempt_index": index}
            )
        if record is not None:
            recorded_reward = record["measured_reward"]
            if abs(float(claimed_reward) - recorded_reward) > REWARD_RECONCILE_TOLERANCE * max(1.0, recorded_reward):
                return verifier_lib.result(
                    CHECKER_ID,
                    False,
                    0.0,
                    "measured_reward_diverges_from_harness_record",
                    {"attempt_index": index, "claimed": float(claimed_reward), "recorded": recorded_reward},
                )

        approach = entry.get("approach")
        if not isinstance(approach, str) or not approach.strip():
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "approach_summary_missing", {"attempt_index": index}
            )
        if record is not None and approach != record.get("approach"):
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "approach_summary_diverges_from_harness_record",
                {"attempt_index": index, "claimed": approach, "recorded": record.get("approach")},
            )
        if approach in seen:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "refuted_approach_reintroduced",
                {"attempt_index": index, "first_seen_attempt": seen[approach], "approach": approach},
            )
        seen[approach] = index

    if record_available and len(entries) != len(harness):
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reward_log_length_diverges_from_harness_record",
            {"log_entries": len(entries), "harness_records": len(harness)},
        )

    if not record_available:
        return verifier_lib.result(
            CHECKER_ID,
            True,
            1.0,
            "attempt_log_internally_consistent_harness_record_unavailable",
            {
                "attempts": len(entries),
                "distinct_approaches": len(seen),
                "harness_record_available": False,
            },
        )
    return verifier_lib.result(
        CHECKER_ID,
        True,
        1.0,
        "attempt_indices_reconcile",
        {"attempts": len(entries), "distinct_approaches": len(seen)},
    )
