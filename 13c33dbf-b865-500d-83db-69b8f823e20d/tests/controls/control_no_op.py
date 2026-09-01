# forge-canary: FORGE-CANARY-837861982023138C90B2C0024F036FE0
from __future__ import annotations

import pathlib

CONTROL_ID = "CTL_no_op"
KIND = "no_op"
EXPECTATION = "scores exactly zero with reason no_submission"


def build(workspace: pathlib.Path, records: list) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
