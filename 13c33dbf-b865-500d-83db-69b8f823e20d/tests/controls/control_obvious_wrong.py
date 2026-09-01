# forge-canary: FORGE-CANARY-1BB2B264DB7B36163B3AD778A3401A39
from __future__ import annotations

import pathlib

import control_lib

CONTROL_ID = "CTL_obvious_wrong"
KIND = "obvious_wrong"
EXPECTATION = "a compiler that emits a constant zero result for every program and exits successfully scores below threshold"

CONSTANT_ZERO = '''from __future__ import annotations

PIPELINE_NAME = "constant-zero"

PASS_PIPELINE = {
    "passes": ["parse", "slot_assign", "stack_lower"],
    "pass_preconditions": {"parse": [], "slot_assign": ["cfg_reducible", "types_resolved"], "stack_lower": ["frame_layout_fixed", "registers_virtual"]},
    "pass_invariants": {
        "parse": {"establishes": ["cfg_reducible", "types_resolved", "registers_virtual"], "invalidates": []},
        "slot_assign": {"establishes": ["frame_layout_fixed"], "invalidates": []},
        "stack_lower": {"establishes": ["registers_physical", "calls_marshalled", "abi_resolved", "terminators_normalised"], "invalidates": ["registers_virtual"]},
    },
}


def describe_pipeline():
    return {
        "passes": list(PASS_PIPELINE["passes"]),
        "pass_preconditions": {k: list(v) for k, v in PASS_PIPELINE["pass_preconditions"].items()},
        "pass_invariants": {k: {"establishes": list(v["establishes"]), "invalidates": list(v["invalidates"])} for k, v in PASS_PIPELINE["pass_invariants"].items()},
    }


def compile_program(source, context):
    return [["LOADI", 1, 0], ["OUT", 1], ["HALT"]]


def execute(program, ceiling=2000000):
    return {"trace": [0], "exit_status": 0, "instructions": 3}
'''


def build(workspace: pathlib.Path, records: list) -> None:
    control_lib.write_sources(workspace, {"pipeline.py": CONSTANT_ZERO})
    control_lib.write_reward_log(workspace, records)
    control_lib.honest_artifacts(workspace)
