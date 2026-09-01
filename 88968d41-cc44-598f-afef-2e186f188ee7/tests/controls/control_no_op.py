# forge-canary: FORGE-CANARY-C3A4D0A724B2C1B4ABB13DD5F51313F5
from __future__ import annotations

import pathlib

CONTROL_ID = "CTL_no_op"
KIND = "no_op"
EXPECTATION = "scores exactly zero with reason no_submission"


def build(workspace: pathlib.Path, records: list) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
