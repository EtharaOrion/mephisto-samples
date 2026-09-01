# forge-canary: FORGE-CANARY-DF716052883A908C59FF741CA5A90FE0
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_list_all"
KIND = "list_all"
EXPECTATION = (
    "a submission that enumerates many candidate placement sets without selecting one overlap free "
    "containment valid placement per instance scores below threshold"
)

VARIANT_ROTATIONS = (0, 90, 180, 270)


def build(workspace: pathlib.Path, records: list[dict]) -> None:
    tar_path = control_lib.write_nester(workspace)
    rows = control_lib.public_rows(tar_path, "control_list_all")
    enumerated = []
    for row in rows:
        for rotation in VARIANT_ROTATIONS:
            variant = dict(row)
            variant["placements"] = [
                dict(item, rotation_degrees=rotation) for item in row["placements"]
            ]
            variant["candidate_rotation_bias"] = rotation
            enumerated.append(variant)
    control_lib.write_bundle(workspace, enumerated)
    control_lib.write_reward_log(workspace, records)
