# forge-canary: FORGE-CANARY-F18CDD9D27957C9FD24743C43CBE6FEC
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_list_all"
KIND = "list_all"
EXPECTATION = (
    "a submission that enumerates many candidate bundle packings without selecting one "
    "hazard free schedule per kernel scores below threshold"
)

CANDIDATE_PACKINGS = 4


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_scheduler_tar(workspace, control_lib.reference_source())
    control_lib.emit_schedule_bundle(workspace, repeat_each=CANDIDATE_PACKINGS)
    control_lib.write_reward_log(workspace, records)
