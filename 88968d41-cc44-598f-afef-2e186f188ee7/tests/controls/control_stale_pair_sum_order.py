# forge-canary: FORGE-CANARY-66179744CBBE6D40F17E52FC11A7BD50
from __future__ import annotations

import pathlib

import control_lib
import registry
import verifier_lib

CONTROL_ID = "CTL_stale_pair_sum_order"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M6 ascending pair sum order scores below threshold and "
    "C_M6_pair_sum_order_binding attributes the zero"
)

BANNER = "Certificate assembled with the pair sum recipe from the starter era, walking the domain in ascending order."


def build(workspace: pathlib.Path, records: list) -> None:
    geometry = verifier_lib.live_geometry()
    live_predicate = verifier_lib.live_predicate()
    ambient = registry.AMBIENTS[geometry["ambient_params_id"]]
    points = control_lib.build_points(ambient, live_predicate)
    control_lib.write_constructor(
        workspace, points, geometry["ambient_params_id"], live_predicate["predicate_digest"], BANNER
    )
    stale_geometry = dict(geometry)
    stale_geometry["pair_sum_order"] = registry.PAIR_SUM_ORDER_ASCENDING
    control_lib.write_bundle(
        workspace, control_lib.honest_bundle(points, ambient, live_predicate, stale_geometry)
    )
    control_lib.write_reward_log(workspace, records)
