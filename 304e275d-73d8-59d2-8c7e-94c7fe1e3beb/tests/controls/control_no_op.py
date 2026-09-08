# forge-canary: FORGE-CANARY-D7D611766DCE029BB6ABF16112354005
from __future__ import annotations

import pathlib

CONTROL_ID = "CTL_no_op"
KIND = "no_op"
EXPECTATION = "scores exactly zero with reason no_submission"


def build(workspace: pathlib.Path, records: list) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
