# forge-canary: FORGE-CANARY-4AE0EDE26D579A1BF7C543EA855A0482
from __future__ import annotations

import pathlib

import control_lib
import registry
import verifier_lib

CONTROL_ID = "CTL_stale_translation_anchor"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M4 lowest_indexed_point translation anchor scores below threshold and "
    "C_M4_translation_anchor_binding attributes the zero"
)

BANNER = "Certificate assembled with the translation recipe from the starter era, anchored on the lowest indexed point."


def build(workspace: pathlib.Path, records: list) -> None:
    geometry = verifier_lib.live_geometry()
    live_predicate = verifier_lib.live_predicate()
    ambient = registry.AMBIENTS[geometry["ambient_params_id"]]
    points = control_lib.build_points(ambient, live_predicate)
    control_lib.write_constructor(
        workspace, points, geometry["ambient_params_id"], live_predicate["predicate_digest"], BANNER
    )
    stale_geometry = dict(geometry)
    stale_geometry["translation_anchor"] = registry.TRANSLATION_ANCHOR_LOW
    control_lib.write_bundle(
        workspace, control_lib.honest_bundle(points, ambient, live_predicate, stale_geometry)
    )
    control_lib.write_reward_log(workspace, records)
