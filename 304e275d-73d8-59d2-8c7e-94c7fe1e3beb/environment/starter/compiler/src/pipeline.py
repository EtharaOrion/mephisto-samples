from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "include"))

import lowering
import runtime

PIPELINE_NAME = "naive-stack-lowering"

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


def pass_fact_ledger() -> dict:
    facts: set = set()
    ledger: dict = {}
    for name in PASS_PIPELINE["passes"]:
        invariants = PASS_PIPELINE["pass_invariants"][name]
        facts.difference_update(str(fact) for fact in invariants["invalidates"])
        facts.update(str(fact) for fact in invariants["establishes"])
        ledger[str(name)] = sorted(facts)
    return ledger


def describe_pipeline() -> dict:
    return {
        "passes": list(PASS_PIPELINE["passes"]),
        "pass_preconditions": {k: list(v) for k, v in PASS_PIPELINE["pass_preconditions"].items()},
        "pass_invariants": {
            k: {"establishes": list(v["establishes"]), "invalidates": list(v["invalidates"])}
            for k, v in PASS_PIPELINE["pass_invariants"].items()
        },
        "pass_fact_ledger": pass_fact_ledger(),
    }


def compile_program(source: str, context: dict) -> list:
    return lowering.lower(source, context)


def execute(program: list, ceiling: int = 2_000_000) -> dict:
    return runtime.execute(program, ceiling)
