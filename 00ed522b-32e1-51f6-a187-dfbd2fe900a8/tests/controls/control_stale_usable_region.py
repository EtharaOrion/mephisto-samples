# forge-canary: FORGE-CANARY-8881AD83FBBDBD62B88DCA22928690C5
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_stale_usable_region"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M5 raw sheet rectangle containment predicate, seats parts against "
    "the raw sheet edge and declares the raw sheet usable_region_digest scores below threshold "
    "and C_M5_usable_region_binding attributes the zero"
)

PATCH = {
    "main.py": [
        (
            'USABLE_REGION_MODE = "trim_inset_rectangle"',
            'USABLE_REGION_MODE = "raw_sheet_rectangle"',
        ),
        (
            "TRIM_INSET_UNITS = 3",
            "TRIM_INSET_UNITS = 0",
        ),
    ]
}


def build(workspace: pathlib.Path, records: list[dict]) -> None:
    tar_path = control_lib.write_nester(workspace, PATCH)
    control_lib.write_bundle(workspace, control_lib.public_rows(tar_path, "control_stale_region"))
    control_lib.write_reward_log(workspace, records)
