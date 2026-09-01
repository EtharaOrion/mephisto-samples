# forge-canary: FORGE-CANARY-8C9E0B8D2FBCC6E24B34F86E4C4C76B9
from __future__ import annotations

import json
import pathlib

import control_lib
import registry

CONTROL_ID = "CTL_stale_geometry_authority"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M2 carrier authority binding scores below threshold and "
    "C_M2_geometry_authority_binding attributes the zero"
)

STALE_RECORD = registry.AUTHORITY_REVISIONS[registry.AUTHORITY_PRE]

PATCH = {
    "carriers.py": [
        (
            "def load_authority() -> dict:\n    return json.loads(authority_path().read_text())",
            "def load_authority() -> dict:\n    return json.loads(PINNED_AUTHORITY)",
        ),
        (
            'CONFLICTING_FIELDS = ("rotation_allowance", "multiplicity", "sheet_margin")',
            'CONFLICTING_FIELDS = ("rotation_allowance", "multiplicity", "sheet_margin")\n'
            f"PINNED_AUTHORITY = {json.dumps(json.dumps(STALE_RECORD, sort_keys=True))}",
        ),
    ]
}


def build(workspace: pathlib.Path, records: list[dict]) -> None:
    tar_path = control_lib.write_nester(workspace, PATCH)
    control_lib.write_bundle(workspace, control_lib.public_rows(tar_path, "control_stale"))
    control_lib.write_reward_log(workspace, records)
