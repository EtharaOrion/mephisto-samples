# forge-canary: FORGE-CANARY-4AE0EDE26D579A1BF7C543EA855A0482
from __future__ import annotations

import pathlib

import control_lib
import registry
import verifier_lib

CONTROL_ID = "CTL_obvious_wrong"
KIND = "obvious_wrong"
EXPECTATION = (
    "a submission that asserts a large point_count while emitting a point list that fails the "
    "recomputed predicate scores exactly zero with reason size_claim_mismatch"
)

BANNER = "Bulk emission of the leading ambient block with the claimed cardinality taken from the search log."

EMITTED_POINTS = 600
CLAIMED_POINT_COUNT = 900


def build(workspace: pathlib.Path, records: list) -> None:
    geometry = verifier_lib.live_geometry()
    live_predicate = verifier_lib.live_predicate()
    ambient = registry.AMBIENTS[geometry["ambient_params_id"]]
    packed = registry.enumerate_ambient(ambient)[:EMITTED_POINTS]
    points = control_lib.points_from(packed, ambient)
    control_lib.write_constructor(
        workspace, points, geometry["ambient_params_id"], live_predicate["predicate_digest"], BANNER
    )
    indexed = registry.canonicalise(points, ambient)
    control_lib.write_bundle(
        workspace,
        {
            "ambient_params_id": geometry["ambient_params_id"],
            "predicate_digest": live_predicate["predicate_digest"],
            "point_count": CLAIMED_POINT_COUNT,
            "points": points,
            "certificate": registry.certificate(indexed, ambient, live_predicate, geometry),
            "search_seconds": 12.5,
        },
    )
    control_lib.write_reward_log(workspace, records)
