# forge-canary: FORGE-CANARY-47F499A518AD2A66AC8C481E3798DDC4
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_obvious_wrong"
KIND = "obvious_wrong"
EXPECTATION = (
    "a fully serialised one operation per bundle schedule with worst case stall padding "
    "scores below threshold"
)


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_scheduler_tar(workspace, control_lib.baseline_source())
    control_lib.emit_schedule_bundle(workspace)
    control_lib.write_reward_log(workspace, records)
