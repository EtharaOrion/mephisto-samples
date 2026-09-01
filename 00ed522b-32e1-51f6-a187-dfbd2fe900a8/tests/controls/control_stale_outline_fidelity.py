# forge-canary: FORGE-CANARY-DF716052883A908C59FF741CA5A90FE0
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_stale_outline_fidelity"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M6 unit lattice outlines, reuses its cached no fit polygons and "
    "declares the outline-2026-08-17.a revision and digest scores below threshold and "
    "C_M6_outline_fidelity_binding attributes the zero"
)

PATCH = {
    "main.py": [
        (
            'OUTLINE_REVISION_ID = "outline-2026-08-17.b"',
            'OUTLINE_REVISION_ID = "outline-2026-08-17.a"',
        ),
    ]
}


def build(workspace: pathlib.Path, records: list[dict]) -> None:
    tar_path = control_lib.write_nester(workspace, PATCH)
    control_lib.write_bundle(workspace, control_lib.public_rows(tar_path, "control_stale_outline"))
    control_lib.write_reward_log(workspace, records)
