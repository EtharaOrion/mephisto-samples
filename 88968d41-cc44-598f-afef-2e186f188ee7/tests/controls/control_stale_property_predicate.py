# forge-canary: FORGE-CANARY-C3A4D0A724B2C1B4ABB13DD5F51313F5
from __future__ import annotations

import pathlib

import control_lib
import registry
import verifier_lib

CONTROL_ID = "CTL_stale_property_predicate"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M2 property predicate scores below threshold and "
    "C_M2_property_predicate_binding attributes the zero"
)

BANNER = "Construction carried forward from the attempt schedule before the property predicate was repinned."


def build(workspace: pathlib.Path, records: list) -> None:
    geometry = verifier_lib.live_geometry()
    ambient = registry.AMBIENTS[geometry["ambient_params_id"]]
    stale_predicate = registry.predicate_record(registry.PREDICATE_LOOSE)
    points = control_lib.build_points(ambient, stale_predicate)
    control_lib.write_constructor(
        workspace, points, geometry["ambient_params_id"], stale_predicate["predicate_digest"], BANNER
    )
    bundle = control_lib.honest_bundle(points, ambient, stale_predicate, geometry)
    control_lib.write_bundle(workspace, bundle)
    control_lib.write_reward_log(workspace, records)
