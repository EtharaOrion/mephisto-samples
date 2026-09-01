# forge-canary: FORGE-CANARY-8C9E0B8D2FBCC6E24B34F86E4C4C76B9
"""Canonical definitions for the carrier authority registry, the sheet stock pin,
the budget pin and the mutation schedule.

This file is installed root owned with mode 0700 inside the solving image and is
byte identical to tests/registry.py inside the verifier image. It is the single
authority for which carrier binds a conflicting field at a given attempt index,
so the mutation applier and the verifier can never drift apart.
"""

from __future__ import annotations

import hashlib
import json

AUTHORITY_PRE = "ca-2026-08-17.a"
AUTHORITY_POST = "ca-2026-08-17.b"

STOCK_A = "stock-a-2026-08-17"
STOCK_B = "stock-b-2026-08-17"

CARRIER_VECTOR = "vector_outline"
CARRIER_TABLE = "parameter_table"

M1_TURN = 11
M2_TURN = 27
M3_TURN = 39
M4_TURN = 33
M5_TURN = 18
M6_TURN = 46

PIVOT_INSTANCE = 2

NANOS_PER_LINE_EVENT = 25

PREVIEW_CLEARANCE_UNITS = 0
GRADED_CLEARANCE_PRE = 0
GRADED_CLEARANCE_POST = 2

USABLE_REGION_PRE = "raw_sheet_rectangle"
USABLE_REGION_POST = "trim_inset_rectangle"
TRIM_INSET_UNITS = 3

OUTLINE_REVISION_PRE = "outline-2026-08-17.a"
OUTLINE_REVISION_POST = "outline-2026-08-17.b"
OUTLINE_SCALE = 4
FIDELITY_OFFSET_UNITS = 1
OFFSET_MODULUS = 3
OFFSET_RESIDUE = 1

SHEET_PROFILES = {
    STOCK_A: {
        "sheet_stock_profile_id": STOCK_A,
        "width": 300,
        "height": 200,
        "defects": [
            [126, 0, 150, 34],
            [242, 118, 276, 148],
        ],
    },
    STOCK_B: {
        "sheet_stock_profile_id": STOCK_B,
        "width": 260,
        "height": 240,
        "defects": [
            [0, 96, 28, 126],
            [96, 0, 124, 30],
            [118, 128, 152, 160],
            [214, 60, 244, 92],
            [60, 206, 96, 240],
        ],
    },
}

AUTHORITY_REVISIONS = {
    AUTHORITY_PRE: {
        "authority_revision_id": AUTHORITY_PRE,
        "carriers": [CARRIER_VECTOR, CARRIER_TABLE],
        "bindings": {
            "rotation_allowance": CARRIER_TABLE,
            "multiplicity": CARRIER_TABLE,
            "sheet_margin": CARRIER_TABLE,
        },
    },
    AUTHORITY_POST: {
        "authority_revision_id": AUTHORITY_POST,
        "carriers": [CARRIER_VECTOR, CARRIER_TABLE],
        "bindings": {
            "rotation_allowance": CARRIER_VECTOR,
            "multiplicity": CARRIER_VECTOR,
            "sheet_margin": CARRIER_TABLE,
        },
    },
}

BUDGET_PRE = {
    "per_instance_budget_seconds": 1.2,
    "sweep_budget_seconds": 9.0,
    "public_instance_count": 4,
    "hidden_instance_count": 6,
}

BUDGET_POST = {
    "per_instance_budget_seconds": 0.6,
    "sweep_budget_seconds": 6.0,
    "public_instance_count": 6,
    "hidden_instance_count": 9,
}

WASTE_ANCHORS = {
    STOCK_A: {"floor": 0.650, "target": 0.472},
    STOCK_B: {"floor": 0.659, "target": 0.481},
}

STOCK_EFFECT_MARGIN = 0.06


def authority_digest(record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def resolve_state(attempt_index: int) -> dict:
    authority = AUTHORITY_REVISIONS[AUTHORITY_POST if attempt_index >= M2_TURN else AUTHORITY_PRE]
    budget = dict(BUDGET_POST if attempt_index >= M3_TURN else BUDGET_PRE)
    clearance = GRADED_CLEARANCE_POST if attempt_index >= M4_TURN else GRADED_CLEARANCE_PRE
    region_mode = USABLE_REGION_POST if attempt_index >= M5_TURN else USABLE_REGION_PRE
    trim_inset = TRIM_INSET_UNITS if attempt_index >= M5_TURN else 0
    outline_revision = OUTLINE_REVISION_POST if attempt_index >= M6_TURN else OUTLINE_REVISION_PRE

    if attempt_index < M1_TURN:
        stock = {
            "sheet_stock_profile_id": STOCK_A,
            "transition": "settled",
            "pivot_instance": 0,
            "previous_profile_id": None,
        }
    elif attempt_index == M1_TURN:
        stock = {
            "sheet_stock_profile_id": STOCK_B,
            "transition": "in_flight",
            "pivot_instance": PIVOT_INSTANCE,
            "previous_profile_id": STOCK_A,
        }
    else:
        stock = {
            "sheet_stock_profile_id": STOCK_B,
            "transition": "settled",
            "pivot_instance": 0,
            "previous_profile_id": STOCK_A,
        }

    manifest = dict(stock)
    manifest.update(budget)
    manifest["attempt_index"] = attempt_index
    manifest["preview_clearance_units"] = PREVIEW_CLEARANCE_UNITS
    manifest["authority_revision_id"] = authority["authority_revision_id"]
    manifest["usable_region_mode"] = USABLE_REGION_PRE
    manifest["trim_inset_units"] = 0
    manifest["outline_revision_id"] = OUTLINE_REVISION_PRE

    return {
        "attempt_index": attempt_index,
        "authority": dict(authority),
        "authority_digest": authority_digest(authority),
        "manifest": manifest,
        "graded_clearance_units": clearance,
        "budget": budget,
        "usable_region_mode": region_mode,
        "trim_inset_units": trim_inset,
        "outline_revision_id": outline_revision,
    }


def profile_for_instance(manifest: dict, instance_ordinal: int) -> str:
    """During the announced stock rotation the sweep straddles two profiles, so the
    profile is resolved per instance ordinal and never once per attempt."""
    if manifest.get("transition") == "in_flight" and instance_ordinal < manifest.get("pivot_instance", 0):
        return manifest["previous_profile_id"]
    return manifest["sheet_stock_profile_id"]


def resolve_field(piece: dict, field: str, bindings: dict):
    carrier = bindings[field]
    if carrier == CARRIER_VECTOR:
        return piece[f"vector_{field}"]
    if carrier == CARRIER_TABLE:
        return piece[f"table_{field}"]
    raise KeyError(f"unknown_carrier:{carrier}")


def usable_twice_area(profile: dict) -> int:
    total = 2 * profile["width"] * profile["height"]
    for x0, y0, x1, y1 in profile["defects"]:
        total -= 2 * (x1 - x0) * (y1 - y0)
    return total


def waste_to_score(mean_waste: float, profile_id: str) -> float:
    anchors = WASTE_ANCHORS[profile_id]
    floor = anchors["floor"]
    target = anchors["target"]
    value = (floor - mean_waste) / (floor - target)
    return max(0.0, min(1.0, value))
