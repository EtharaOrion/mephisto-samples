"""Canonical machine model registry, latency tables and mutation schedule.

This file is installed root owned with mode 0700 inside the solving image and is
byte identical to tests/registry.py inside the verifier image, so the mutation
applier and the graded replay can never drift apart. The registry record is the
declared authority for the live latencies. The shipped tabular manifest and the
prose model description are secondary carriers that are deliberately frozen at
the pre repin values.
"""

from __future__ import annotations

import hashlib
import json

MM_PRE = "mm-2026-08-17.wide4"
MM_POST = "mm-2026-08-17.wide6"

LT_PRE = "lt-2026-08-17.a"
LT_POST = "lt-2026-08-17.b"

M1_TURN = 10
M5_TURN = 17
M2_TURN = 25
M4_TURN = 32
M3_TURN = 40
M6_TURN = 46

ARCHITECTURAL_REGISTER_CEILING_PRE = 32
ARCHITECTURAL_REGISTER_CEILING_POST = 28

WAR_RULE_PRE = "late_landing_relaxed"
WAR_RULE_POST = "issue_ordered_strict"

PUBLIC_KERNEL_COUNT = 12
SWEEP_KERNEL_COUNT_PRE = 24
SWEEP_KERNEL_COUNT_POST = 32

PER_KERNEL_BUDGET_SECONDS_PRE = 0.030
PER_KERNEL_BUDGET_SECONDS_POST = 0.014
SWEEP_BUDGET_SECONDS_PRE = 0.50
SWEEP_BUDGET_SECONDS_POST = 0.30

NANOS_PER_UNIT = 40

LATENCY_TABLES = {
    LT_PRE: {"add": 1, "sub": 1, "xor": 1, "shl": 1, "mul": 4, "mac": 5, "load": 4, "store": 1},
    LT_POST: {"add": 1, "sub": 1, "xor": 1, "shl": 1, "mul": 4, "mac": 7, "load": 6, "store": 1},
}

MACHINE_TARGETS = {
    MM_PRE: {
        "machine_model_id": MM_PRE,
        "issue_width": 4,
        "port_capacity": {"alu": 2, "mem": 1, "mul": 1},
        "unit_occupancy": {"mac": 2},
    },
    MM_POST: {
        "machine_model_id": MM_POST,
        "issue_width": 6,
        "port_capacity": {"alu": 3, "mem": 2, "mul": 2},
        "unit_occupancy": {"mac": 2},
    },
}

SCORE_ANCHORS = {
    f"{MM_PRE}|{LT_PRE}": {"floor": 11.0, "mid": 1.33, "target": 1.185},
    f"{MM_PRE}|{LT_POST}": {"floor": 12.0, "mid": 1.30, "target": 1.155},
    f"{MM_POST}|{LT_PRE}": {"floor": 11.5, "mid": 1.26, "target": 1.115},
    f"{MM_POST}|{LT_POST}": {"floor": 12.5, "mid": 1.22, "target": 1.075},
}

LOW_BAND_CEILING = 0.25

EFFECT_MARGIN = 4.0
SECONDS_TOLERANCE = 1.0e-09

REASON_VOCABULARY = (
    "no_submission",
    "hazard_violation",
    "latency_violation",
    "port_oversubscription",
    "semantic_divergence",
    "budget_overrun",
    "red_line_trip",
)


def latency_table_digest(table: dict) -> str:
    payload = json.dumps(table, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def machine_model(machine_model_id: str, latency_table_id: str) -> dict:
    target = MACHINE_TARGETS[machine_model_id]
    table = dict(LATENCY_TABLES[latency_table_id])
    return {
        "machine_model_id": target["machine_model_id"],
        "issue_width": target["issue_width"],
        "port_capacity": dict(target["port_capacity"]),
        "unit_occupancy": dict(target["unit_occupancy"]),
        "latency_table_id": latency_table_id,
        "latency_table_digest": latency_table_digest(table),
        "latencies": table,
        "score_anchors": dict(SCORE_ANCHORS[f"{machine_model_id}|{latency_table_id}"]),
    }


def ratio_to_score(ratio: float, anchors: dict) -> float:
    """Piecewise logarithmic map. The band below the competent anchor is worth at most
    LOW_BAND_CEILING, so a legal but unscheduled kernel sweep scores low without
    scoring zero, and the band above it carries the rest of the reward."""
    import math

    if ratio <= 0:
        return 0.0
    floor = float(anchors["floor"])
    mid = float(anchors["mid"])
    target = float(anchors["target"])
    if ratio >= mid:
        span = math.log(floor) - math.log(mid)
        value = LOW_BAND_CEILING * (math.log(floor) - math.log(ratio)) / span
    else:
        span = math.log(mid) - math.log(target)
        value = LOW_BAND_CEILING + (1.0 - LOW_BAND_CEILING) * (math.log(mid) - math.log(ratio)) / span
    return max(0.0, min(1.0, value))


def latency_manifest() -> dict:
    table = dict(LATENCY_TABLES[LT_PRE])
    return {
        "latency_table_id": LT_PRE,
        "latency_table_digest": latency_table_digest(table),
        "latencies": table,
        "architectural_register_ceiling": ARCHITECTURAL_REGISTER_CEILING_PRE,
        "war_rule": WAR_RULE_PRE,
        "carrier": "shipped_tabular_manifest",
    }


def model_prose(machine_model_id: str) -> str:
    target = MACHINE_TARGETS[machine_model_id]
    table = LATENCY_TABLES[LT_PRE]
    ports = ", ".join(f"{port} {count}" for port, count in sorted(target["port_capacity"].items()))
    return (
        "# Machine model description\n"
        "\n"
        f"The pinned target is {machine_model_id}. It issues at most {target['issue_width']} operations per bundle and carries the port map {ports}. The multiply accumulate unit is unpipelined and cannot be reissued for {target['unit_occupancy']['mac']} cycles.\n"
        "\n"
        f"The load to use distance is {table['load']} cycles and the multiply accumulate result latency is {table['mac']} cycles. Plain multiply retires in {table['mul']} cycles and every single cycle arithmetic operation retires in {table['add']} cycle.\n"
        "\n"
        "This description and the shipped tabular latency manifest are convenience carriers. The machine model registry record is the declared authority whenever the three disagree.\n"
    )


def kernel_policy(attempt_index: int) -> dict:
    if attempt_index >= M3_TURN:
        return {
            "public_kernel_count": PUBLIC_KERNEL_COUNT,
            "sweep_kernel_count": SWEEP_KERNEL_COUNT_POST,
            "per_kernel_budget_seconds": PER_KERNEL_BUDGET_SECONDS_POST,
            "sweep_budget_seconds": SWEEP_BUDGET_SECONDS_POST,
            "nanos_per_unit": NANOS_PER_UNIT,
        }
    return {
        "public_kernel_count": PUBLIC_KERNEL_COUNT,
        "sweep_kernel_count": SWEEP_KERNEL_COUNT_PRE,
        "per_kernel_budget_seconds": PER_KERNEL_BUDGET_SECONDS_PRE,
        "sweep_budget_seconds": SWEEP_BUDGET_SECONDS_PRE,
        "nanos_per_unit": NANOS_PER_UNIT,
    }


def preview_policy(attempt_index: int) -> dict:
    return {"reports_register_waw": attempt_index < M4_TURN}


def resolve_state(attempt_index: int) -> dict:
    machine_model_id = MM_POST if attempt_index >= M1_TURN else MM_PRE
    latency_table_id = LT_POST if attempt_index >= M2_TURN else LT_PRE
    record = machine_model(machine_model_id, latency_table_id)
    record["war_rule"] = WAR_RULE_POST if attempt_index >= M6_TURN else WAR_RULE_PRE
    if attempt_index >= M5_TURN:
        record["architectural_register_ceiling"] = ARCHITECTURAL_REGISTER_CEILING_POST
        record["architectural_register_ceiling_pre"] = ARCHITECTURAL_REGISTER_CEILING_PRE
    return {
        "attempt_index": attempt_index,
        "registry": record,
        "manifest": latency_manifest(),
        "prose": model_prose(machine_model_id),
        "kernels": kernel_policy(attempt_index),
        "preview": preview_policy(attempt_index),
    }


def announcement(attempt_index: int):
    if attempt_index == M1_TURN:
        target = MACHINE_TARGETS[MM_POST]
        ports = ", ".join(f"{port} {count}" for port, count in sorted(target["port_capacity"].items()))
        return (
            f"machine model rotated to {MM_POST} with issue width {target['issue_width']} "
            f"and functional unit port map {ports}"
        )
    if attempt_index == M3_TURN:
        policy = kernel_policy(attempt_index)
        return (
            f"sweep kernel count raised to {policy['sweep_kernel_count']} and per kernel budget "
            f"reduced to {policy['per_kernel_budget_seconds']} modelled seconds"
        )
    return None
