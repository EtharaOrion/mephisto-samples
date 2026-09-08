# forge-canary: FORGE-CANARY-BC2E4D336F98F1E6AE7F60108C26C733
from __future__ import annotations

import pathlib

CONTROL_ID = "CTL_no_op"
KIND = "no_op"
EXPECTATION = "scores exactly zero with reason no_submission"


def build(workspace: pathlib.Path, records: list) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
