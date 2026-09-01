# forge-canary: FORGE-CANARY-DF716052883A908C59FF741CA5A90FE0
from __future__ import annotations

import json
import pathlib

import verifier_lib

CHECKER_ID = "C4_attempt_ordering"


def check(workspace: pathlib.Path) -> dict:
    if not verifier_lib.submission_present(workspace):
        return verifier_lib.result(CHECKER_ID, False, 0.0, "no_submission")

    path = verifier_lib.find_deliverable(workspace, "D3")
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            return verifier_lib.result(CHECKER_ID, False, 0.0, "reward_log_unparseable", {"line": number})

    records = verifier_lib.harness_attempts()
    if len(rows) != len(records):
        return verifier_lib.result(
            CHECKER_ID,
            False,
            0.0,
            "reward_log_length_diverges_from_harness_record",
            {"reward_log_entries": len(rows), "harness_records": len(records)},
        )

    seen_approaches: dict[str, int] = {}
    for position, (row, record) in enumerate(zip(rows, records), start=1):
        if row.get("attempt_index") != position:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "attempt_index_not_monotone_without_gaps",
                {"position": position, "attempt_index": row.get("attempt_index")},
            )
        if record["attempt_index"] != position:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "harness_record_index_not_monotone_without_gaps",
                {"position": position, "harness_attempt_index": record["attempt_index"]},
            )
        approach = row.get("approach")
        if not isinstance(approach, str) or not approach.strip():
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "approach_summary_missing", {"attempt_index": position}
            )
        if approach != record.get("approach"):
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "approach_summary_diverges_from_harness_record",
                {"attempt_index": position, "reward_log": approach, "harness_record": record.get("approach")},
            )
        if approach in seen_approaches:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "approach_summary_repeats_an_already_refuted_configuration",
                {"attempt_index": position, "first_seen_at": seen_approaches[approach], "approach": approach},
            )
        seen_approaches[approach] = position
        reward = row.get("measured_reward")
        if not isinstance(reward, (int, float)):
            return verifier_lib.result(
                CHECKER_ID, False, 0.0, "measured_reward_missing", {"attempt_index": position}
            )
        if abs(float(reward) - float(record.get("measured_reward", 0.0))) > verifier_lib.REWARD_TOLERANCE:
            return verifier_lib.result(
                CHECKER_ID,
                False,
                0.0,
                "measured_reward_diverges_from_harness_record",
                {
                    "attempt_index": position,
                    "reward_log": float(reward),
                    "harness_record": float(record.get("measured_reward", 0.0)),
                },
            )

    return verifier_lib.result(
        CHECKER_ID, True, 1.0, "attempt_log_reconciles", {"attempts": len(rows)}
    )
