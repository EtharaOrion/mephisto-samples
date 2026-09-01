# forge-canary: FORGE-CANARY-6CAA841C1ADA9B611F786DD993BFAE95
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lowering
import runtime

PIPELINE_NAME = "register-homed-lowering"

PASS_PIPELINE = {
    "passes": [
        "parse",
        "constant_fold",
        "dead_code_elim",
        "slot_assign",
        "register_allocate",
        "loop_rotate",
        "abi_marshal",
        "peephole",
    ],
    "pass_preconditions": {
        "parse": [],
        "constant_fold": ["types_resolved"],
        "dead_code_elim": ["cfg_reducible", "constants_folded"],
        "slot_assign": ["cfg_reducible", "types_resolved"],
        "register_allocate": ["frame_layout_fixed", "registers_virtual"],
        "loop_rotate": ["cfg_reducible", "registers_physical"],
        "abi_marshal": ["registers_physical", "frame_layout_fixed"],
        "peephole": ["terminators_normalised", "calls_marshalled"],
    },
    "pass_invariants": {
        "parse": {"establishes": ["cfg_reducible", "types_resolved", "registers_virtual"], "invalidates": []},
        "constant_fold": {"establishes": ["constants_folded"], "invalidates": []},
        "dead_code_elim": {"establishes": ["dead_code_removed"], "invalidates": []},
        "slot_assign": {"establishes": ["frame_layout_fixed"], "invalidates": []},
        "register_allocate": {"establishes": ["registers_physical"], "invalidates": ["registers_virtual"]},
        "loop_rotate": {"establishes": ["terminators_normalised", "no_critical_edges"], "invalidates": []},
        "abi_marshal": {"establishes": ["calls_marshalled", "abi_resolved"], "invalidates": []},
        "peephole": {"establishes": [], "invalidates": []},
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
