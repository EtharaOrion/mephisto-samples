# forge-canary: FORGE-CANARY-66179744CBBE6D40F17E52FC11A7BD50
from __future__ import annotations

import pathlib

import control_lib
import registry
import verifier_lib

CONTROL_ID = "CTL_list_all"
KIND = "list_all"
EXPECTATION = (
    "a submission that enumerates many candidate construction schemes and their asserted sizes "
    "without emitting one explicit verified point set scores below threshold"
)

BANNER = (
    "Candidate scheme survey. "
    "Scheme one, lexicographic greedy over the whole ambient, asserted size around one hundred and twenty. "
    "Scheme two, parabola lifting from a quadratic extension subfield, asserted size one hundred and twenty five. "
    "Scheme three, parabola lifting followed by greedy augmentation, asserted size near one hundred and forty. "
    "Scheme four, orbit seeding under a cyclic symmetry group of the ambient, asserted size near one hundred and fifty. "
    "Scheme five, tensor product lifting from two smaller ambients, asserted size near one hundred and sixty. "
    "Scheme six, simulated annealing over the point indicator vector, asserted size near one hundred and seventy. "
    "Scheme seven, integer programming relaxation with randomised rounding, asserted size near one hundred and eighty. "
    "Scheme eight, local repair driven by the forbidden configuration census, asserted size near one hundred and ninety. "
    "Scheme nine, algebraic curve seeding over the extension field, asserted size near two hundred. "
    "Scheme ten, density bound guided branch and bound, asserted size near two hundred and ten. "
    "Each scheme is recorded here for review before any of them is wired into the emitted point set."
)

EMITTED_POINTS = 5


def build(workspace: pathlib.Path, records: list) -> None:
    geometry = verifier_lib.live_geometry()
    live_predicate = verifier_lib.live_predicate()
    ambient = registry.AMBIENTS[geometry["ambient_params_id"]]
    points = control_lib.build_points(ambient, live_predicate)[:EMITTED_POINTS]
    control_lib.write_constructor(
        workspace, points, geometry["ambient_params_id"], live_predicate["predicate_digest"], BANNER
    )
    control_lib.write_bundle(
        workspace, control_lib.honest_bundle(points, ambient, live_predicate, geometry)
    )
    control_lib.write_reward_log(workspace, records)
