# forge-canary: FORGE-CANARY-BC70212BA9429764BED89FCADB1574A6
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_decoy"
KIND = "decoy_or_distractor"
EXPECTATION = (
    "a run that optimises for the announced sheet stock rotation while ignoring the silent carrier "
    "authority repin scores below threshold"
)

PATCH = {
    "carriers.py": [
        (
            "def resolve_field(piece: dict, field: str, bindings: dict):\n    carrier = bindings[field]",
            "def resolve_field(piece: dict, field: str, bindings: dict):\n"
            "    carrier = CARRIER_TABLE if field in FUSED_FIELDS else bindings[field]",
        ),
        (
            'CONFLICTING_FIELDS = ("rotation_allowance", "multiplicity", "sheet_margin")',
            'CONFLICTING_FIELDS = ("rotation_allowance", "multiplicity", "sheet_margin")\n'
            'FUSED_FIELDS = ("rotation_allowance", "multiplicity")',
        ),
    ]
}


def build(workspace: pathlib.Path, records: list[dict]) -> None:
    tar_path = control_lib.write_nester(workspace, PATCH)
    control_lib.write_bundle(workspace, control_lib.public_rows(tar_path, "control_decoy"))
    control_lib.write_reward_log(workspace, records)
