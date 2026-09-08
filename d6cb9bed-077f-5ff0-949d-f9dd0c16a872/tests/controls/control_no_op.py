# forge-canary: FORGE-CANARY-2D54358AA72E35109CE8E84B73528515
from __future__ import annotations

import pathlib

CONTROL_ID = "CTL_no_op"
KIND = "no_op"
EXPECTATION = "scores exactly zero with reason no_submission"


def build(workspace: pathlib.Path, records: list[dict]) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
