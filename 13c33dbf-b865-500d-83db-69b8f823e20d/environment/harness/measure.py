"""Local scoring model for edgebench/arc_compiler_runtime.

Evaluator owned. This module implements the credit transform exactly as the verifier does,
so any figure it reports over the public smoke slice is reproducible. Speed is charged
against the executed instruction count reported by the submitted runtime, never against a
wall clock, so a measurement never moves between two runs of the same submission.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import pathlib

ISA_DIR = pathlib.Path(os.environ.get("EDGEBENCH_ISA_DIR", "/mnt/isa"))
BASELINE_DIR = pathlib.Path(os.environ.get("EDGEBENCH_BASELINE_DIR", "/opt/edgebench/harness/baseline"))

SPEED_BASE = 0.10
TARGET_SPEEDUP = 1.85
INSTRUCTION_CEILING = 2_000_000

EXIT_CEILING = 3
EXIT_FAULT = 4


SUPPORT_MODULE_NAMES = ("frontend", "lowering", "runtime", "abi_tables")


def load_pipeline(source_dir: pathlib.Path):
    import sys

    for name in SUPPORT_MODULE_NAMES:
        sys.modules.pop(name, None)
    while str(source_dir) in sys.path:
        sys.path.remove(str(source_dir))
    sys.path.insert(0, str(source_dir))
    spec = importlib.util.spec_from_file_location(f"pipeline_{abs(hash(str(source_dir)))}", str(source_dir / "pipeline.py"))
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name in SUPPORT_MODULE_NAMES:
            sys.modules.pop(name, None)
        while str(source_dir) in sys.path:
            sys.path.remove(str(source_dir))
    return module


def live_state() -> dict:
    return {
        "isa": json.loads((ISA_DIR / "isa.json").read_text()),
        "abi": json.loads((ISA_DIR / "abi.json").read_text()),
        "intrinsics": json.loads((ISA_DIR / "intrinsics.json").read_text()),
        "manifest": json.loads((ISA_DIR / "manifest.json").read_text()),
    }


def public_programs(state: dict) -> list:
    out = []
    for entry in state["manifest"]["programs"]:
        source = (ISA_DIR / entry["source_path"]).read_text()
        expected = json.loads((ISA_DIR / entry["expected_path"]).read_text())
        out.append(dict(entry, source=source, expected=expected))
    return out


def context_for(state: dict, program: dict, isa_specs: dict) -> dict:
    revision = program["isa_revision_id"]
    return {
        "isa": isa_specs[revision],
        "abi": state["abi"],
        "intrinsics": state["intrinsics"]["by_isa_revision"][revision],
    }


def isa_specs(state: dict) -> dict:
    return state["manifest"]["isa_specs"]


def speed_credit(baseline_instructions: int, actual_instructions: int) -> float:
    if actual_instructions <= 0 or baseline_instructions <= 0:
        return 0.0
    speedup = baseline_instructions / actual_instructions
    if speedup <= 1.0:
        return 0.0
    return max(0.0, min(1.0, math.log(speedup) / math.log(TARGET_SPEEDUP)))


def run_slice(module, programs: list, state: dict, specs: dict) -> dict:
    rows = {}
    for program in programs:
        row = {"passed": False, "instructions": 0, "verdict": "compile_error", "miscompile": False}
        try:
            image = module.compile_program(program["source"], context_for(state, program, specs))
        except Exception:
            rows[program["name"]] = row
            continue
        try:
            observed = module.execute(image, INSTRUCTION_CEILING)
        except Exception:
            row["verdict"] = "runtime_error"
            rows[program["name"]] = row
            continue
        row["instructions"] = int(observed["instructions"])
        status = int(observed["exit_status"])
        if status == EXIT_CEILING:
            row["verdict"] = "instruction_ceiling_exceeded"
        elif status == EXIT_FAULT:
            row["verdict"] = "machine_fault"
        elif status != program["expected"]["exit_status"] or list(observed["trace"]) != program["expected"]["trace"]:
            row["verdict"] = "trace_divergence"
            row["miscompile"] = True
        else:
            row["verdict"] = "passed"
            row["passed"] = True
        rows[program["name"]] = row
    return rows


def passed_by_category(programs: list, submitted: dict) -> dict:
    breakdown: dict = {}
    for program in programs:
        category = str(program["category"])
        breakdown.setdefault(category, 0)
        if submitted[program["name"]]["passed"]:
            breakdown[category] += 1
    return breakdown


def unaccelerated_programs(programs: list, submitted: dict, baseline: dict) -> list:
    unaccelerated = []
    for program in programs:
        row = submitted[program["name"]]
        if not row["passed"]:
            continue
        anchor = baseline[program["name"]]
        if not anchor["passed"] or int(row["instructions"]) >= int(anchor["instructions"]):
            unaccelerated.append(str(program["name"]))
    return sorted(unaccelerated)


def instruction_census_digest(programs: list, submitted: dict) -> str:
    triples = [
        [str(name), int(submitted[name]["instructions"]), str(submitted[name]["verdict"])]
        for name in sorted(str(program["name"]) for program in programs)
    ]
    return hashlib.sha256(json.dumps(triples, sort_keys=True).encode("utf-8")).hexdigest()


def measure(source_dir: pathlib.Path) -> dict:
    state = live_state()
    specs = isa_specs(state)
    programs = public_programs(state)
    submitted = run_slice(load_pipeline(source_dir), programs, state, specs)
    baseline = run_slice(load_pipeline(BASELINE_DIR), programs, state, specs)

    total_weight = 0.0
    earned = 0.0
    passed = 0
    miscompiles = 0
    for program in programs:
        weight = float(program["weight"])
        total_weight += weight
        row = submitted[program["name"]]
        if row["miscompile"]:
            miscompiles += 1
        if not row["passed"]:
            continue
        passed += 1
        anchor = baseline[program["name"]]["instructions"] if baseline[program["name"]]["passed"] else 0
        earned += weight * (SPEED_BASE + (1.0 - SPEED_BASE) * speed_credit(anchor, row["instructions"]))
    fraction = earned / total_weight if total_weight else 0.0
    return {
        "weighted_pass_fraction": fraction,
        "raw_passed": passed,
        "raw_total": len(programs),
        "miscompile_count": miscompiles,
        "isa_revision_id": state["isa"]["isa_revision_id"],
        "calling_convention_digest": state["abi"]["calling_convention_digest"],
        "total_instructions": sum(r["instructions"] for r in submitted.values() if r["passed"]),
        "passed_by_category": passed_by_category(programs, submitted),
        "unaccelerated_programs": unaccelerated_programs(programs, submitted, baseline),
        "instruction_census_digest": instruction_census_digest(programs, submitted),
        "opened": [str(ISA_DIR / p["source_path"]) for p in state["manifest"]["programs"]],
    }
