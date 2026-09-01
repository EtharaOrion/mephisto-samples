# forge-canary: FORGE-CANARY-1254CEC55E3E94C4E944B7B7CCD8B8F1
from __future__ import annotations

import pathlib

import control_lib
import registry
import verifier_lib

CONTROL_ID = "CTL_stale_digest_join"
KIND = "stale"
EXPECTATION = (
    "a run that keeps the pre M5 comma digest join token scores below threshold and "
    "C_M5_digest_join_binding attributes the zero"
)

BANNER = "Certificate assembled with the digest recipe from the starter era, joining index strings with commas."


def build(workspace: pathlib.Path, records: list) -> None:
    geometry = verifier_lib.live_geometry()
    live_predicate = verifier_lib.live_predicate()
    ambient = registry.AMBIENTS[geometry["ambient_params_id"]]
    points = control_lib.build_points(ambient, live_predicate)
    control_lib.write_constructor(
        workspace, points, geometry["ambient_params_id"], live_predicate["predicate_digest"], BANNER
    )
    stale_geometry = dict(geometry)
    stale_geometry["digest_join"] = registry.DIGEST_JOIN_COMMA
    control_lib.write_bundle(
        workspace, control_lib.honest_bundle(points, ambient, live_predicate, stale_geometry)
    )
    control_lib.write_reward_log(workspace, records)
