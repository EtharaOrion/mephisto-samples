from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lowering
import runtime

PIPELINE_NAME = "frozen-baseline-stack-lowering"

PASS_PIPELINE = {
    "passes": ["parse", "slot_assign", "stack_lower"],
    "pass_preconditions": {
        "parse": [],
        "slot_assign": ["cfg_reducible", "types_resolved"],
        "stack_lower": ["frame_layout_fixed", "registers_virtual"],
    },
    "pass_invariants": {
        "parse": {"establishes": ["cfg_reducible", "types_resolved", "registers_virtual"], "invalidates": []},
        "slot_assign": {"establishes": ["frame_layout_fixed"], "invalidates": []},
        "stack_lower": {
            "establishes": ["registers_physical", "calls_marshalled", "abi_resolved", "terminators_normalised"],
            "invalidates": ["registers_virtual"],
        },
    },
}


def describe_pipeline() -> dict:
    return {
        "passes": list(PASS_PIPELINE["passes"]),
        "pass_preconditions": {k: list(v) for k, v in PASS_PIPELINE["pass_preconditions"].items()},
        "pass_invariants": {
            k: {"establishes": list(v["establishes"]), "invalidates": list(v["invalidates"])}
            for k, v in PASS_PIPELINE["pass_invariants"].items()
        },
    }


def compile_program(source: str, context: dict) -> list:
    return lowering.lower(source, context)


def execute(program: list, ceiling: int = 2_000_000) -> dict:
    return runtime.execute(program, ceiling)
