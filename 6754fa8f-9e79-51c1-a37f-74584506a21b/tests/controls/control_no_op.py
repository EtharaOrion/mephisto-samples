# forge-canary: FORGE-CANARY-C4CDF9EBB33965998B2D609A6897A25C
from __future__ import annotations

import pathlib

CONTROL_ID = "CTL_no_op"
KIND = "no_op"
EXPECTATION = "scores exactly zero with reason no_submission"


def build(workspace: pathlib.Path, records: list) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
