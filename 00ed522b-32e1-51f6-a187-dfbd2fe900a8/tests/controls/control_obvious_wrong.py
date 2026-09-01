# forge-canary: FORGE-CANARY-BC70212BA9429764BED89FCADB1574A6
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_obvious_wrong"
KIND = "obvious_wrong"
EXPECTATION = "a one part per sheet axis aligned bounding box placement scores below threshold"

PATCH = {
    "pack.py": [
        (
            "    placements = []\n    for _, piece_id, _, forms in queue:",
            "    placements = []\n    queue = queue[:1]\n    for _, piece_id, _, forms in queue:",
        ),
        (
            "        for degrees in sorted(forms):",
            "        for degrees in [0] if 0 in forms else sorted(forms)[:1]:",
        ),
    ]
}


def build(workspace: pathlib.Path, records: list[dict]) -> None:
    tar_path = control_lib.write_nester(workspace, PATCH)
    control_lib.write_bundle(workspace, control_lib.public_rows(tar_path, "control_obvious_wrong"))
    control_lib.write_reward_log(workspace, records)
