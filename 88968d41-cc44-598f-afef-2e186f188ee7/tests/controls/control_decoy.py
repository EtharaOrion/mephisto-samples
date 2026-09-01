# forge-canary: FORGE-CANARY-4AE0EDE26D579A1BF7C543EA855A0482
from __future__ import annotations

import pathlib

import control_lib
import registry
import verifier_lib

CONTROL_ID = "CTL_decoy"
KIND = "decoy_or_distractor"
EXPECTATION = (
    "a run that adapts to the announced geometry rotation while ignoring the silent predicate "
    "tightening scores below threshold"
)

BANNER = "Construction rebuilt for the rotated ambient using the pair scan described in the baseline notes."


def build(workspace: pathlib.Path, records: list) -> None:
    geometry = verifier_lib.live_geometry()
    live_predicate = verifier_lib.live_predicate()
    ambient = registry.AMBIENTS[geometry["ambient_params_id"]]
    loose_predicate = registry.predicate_record(registry.PREDICATE_LOOSE)
    points = control_lib.build_points(ambient, loose_predicate)
    control_lib.write_constructor(
        workspace, points, geometry["ambient_params_id"], live_predicate["predicate_digest"], BANNER
    )
    control_lib.write_bundle(
        workspace, control_lib.honest_bundle(points, ambient, live_predicate, geometry)
    )
    control_lib.write_reward_log(workspace, records)
