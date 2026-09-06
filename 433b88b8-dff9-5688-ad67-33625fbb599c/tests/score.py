"""p6zeta 5-lane grader for the from-scratch zero-one IP solver task.

This module is the sole judge-side scorer for the task, byte-mirrored between the
build directory (author-side calibration), `dataset/<uuid>/tests/score.py` (Harbor
judge entry), and referenced from `tests/test.sh` as the reward-writing step.

The grader reads:

  --instances DIR            Directory of hidden instance JSONs (`*.ip.json`).
  --optima FILE              Judge-only oracle map produced by compute_optima.py.
  --outputs DIR              Solver outputs per instance (`<instance_id>.out.json`).
  --traces DIR               Optional per-instance stderr traces (`<instance_id>.log`)
                             consumed by the L4 anytime-progression lane. Absent
                             traces yield zero L4 credit for the instance.
  --perturbation-subset FILE Optional list of instance_ids (one per line) the L5
                             sweep covered; L5 is computed over exactly these.
  --perturbations-root DIR   Optional root whose immediate subdirectories are the
                             seven perturbation identifiers (see PERTURBATIONS in
                             p6zeta_lib), each mirroring `--outputs` layout. Absent
                             root yields zero L5 credit.
  --l3-ranking FILE          Optional JSON file with an agent-submitted ranking of
                             the L3 stress cohort (`multi-dimensional-knapsack`) by
                             difficulty descending. Absent file yields zero L3
                             credit.
  --kill-reasons-file FILE   Optional JSON list of kill reasons detected by the
                             harness. Any entry in KILL_REASONS clamps the total
                             to zero.
  --reward-out FILE          Path to write the reward JSON (defaults to the
                             REWARD_CONTRACT_PATH bound in the delivery block).

The grader writes a single reward JSON document with the schema documented in
`emit_reward_document` below. The document is the sole authoritative artifact the
Harbor verifier consumes; every derived detail lives beside the aggregate score so
CRUCIBLE and Phase 2 self-verify can reconstruct exactly why a submission received
its total.

The module is pure stdlib and importable. `grade_submission` returns the same
dictionary that the CLI writes to disk, so the author-time orchestrator
(`build_task.py`) and Phase 2 conformance harness can call the grader
programmatically without a subprocess boundary.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import p6zeta_lib as lib


# ---------------------------------------------------------------------------
# Machine-readable zero-score reason vocabulary
#
# Every enum below is a substring the reward document may carry inside
# `zero_score_reasons`. Downstream FORGE Phase 2 verifier-robustness fixtures
# assert that a graded zero fires with one of these exact tokens, so the strings
# are a load-bearing part of the reward schema. Additions require Phase 0.5
# re-sign of seed/contract.yaml.
# ---------------------------------------------------------------------------

REASON_NO_OUTPUTS_DIR = "no_outputs_directory"
REASON_NO_INSTANCES_DIR = "no_instances_directory"
REASON_NO_OPTIMA_FILE = "no_optima_file"
REASON_INSTANCE_MISSING_OUTPUT = "instance_missing_output"
REASON_OUTPUT_SCHEMA_INVALID = "output_schema_invalid"
REASON_STATUS_MISMATCH = "status_mismatch"
REASON_VARIABLES_INFEASIBLE = "variables_infeasible"
REASON_L3_RANKING_ABSENT = "l3_ranking_absent"
REASON_L3_RANKING_MALFORMED = "l3_ranking_malformed"
REASON_L4_TRACES_ABSENT = "l4_traces_absent"
REASON_L5_PERTURBATIONS_ABSENT = "l5_perturbations_absent"
REASON_L5_SUBSET_EMPTY = "l5_subset_empty"
REASON_KILL_BAND_TRIGGERED = "kill_band_triggered"


# ---------------------------------------------------------------------------
# Per-instance record kept beside the aggregate reward document
# ---------------------------------------------------------------------------

@dataclass
class InstanceRecord:
    instance_id: str
    family: str
    oracle_status: str
    oracle_objective: Optional[float]
    reported_status: Optional[str]
    reported_objective: Optional[float]
    schema_ok: bool
    schema_errors: List[str]
    status_match: bool
    variables_feasible: bool
    feasibility_violations: List[str]
    l1_pass: bool
    l1_reasons: List[str]
    l2_gap: Optional[float]
    l2_credit: float
    l4_trace_present: bool
    l4_trace_tokens: int
    l4_credit: float


@dataclass
class PerturbationRecord:
    perturbation: str
    per_instance_l2_credits: List[float]
    base_matching_l2_credits: List[float]
    robustness_credit: float
    missing_output_count: int


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_instances(instances_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load every `*.ip.json` under instances_dir keyed by instance_id."""
    if not instances_dir.is_dir():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for path in sorted(instances_dir.iterdir()):
        if not path.name.endswith(lib.INSTANCE_INPUT_SUFFIX):
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                obj = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(obj, dict):
            continue
        iid = obj.get("instance_id")
        if isinstance(iid, str):
            out[iid] = obj
    return out


def _load_optima(optima_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load the compute_optima.py oracle map keyed by instance_id."""
    try:
        with optima_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)}


def _load_outputs(outputs_dir: Path) -> Dict[str, Any]:
    """Load per-instance solver outputs. Non-JSON or missing files map to None.

    The returned dict is populated for every JSON file found. Callers determine
    absence by cross-referencing the instance ID set from `_load_instances`.
    """
    if not outputs_dir.is_dir():
        return {}
    out: Dict[str, Any] = {}
    for path in sorted(outputs_dir.iterdir()):
        stem = path.name
        if stem.endswith(".out.json"):
            iid = stem[: -len(".out.json")]
        elif stem.endswith(".json"):
            iid = stem[: -len(".json")]
        else:
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                out[iid] = json.load(fh)
        except (json.JSONDecodeError, OSError):
            out[iid] = None
    return out


def _load_trace(traces_dir: Optional[Path], instance_id: str) -> Optional[str]:
    """Load a per-instance stderr log if present. Missing = None."""
    if traces_dir is None or not traces_dir.is_dir():
        return None
    for suffix in (".log", ".stderr", ".trace"):
        candidate = traces_dir / f"{instance_id}{suffix}"
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
    return None


def _load_perturbations(root: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """For each subdirectory of `root`, load per-instance outputs.

    Returns dict[perturbation_name -> dict[instance_id -> output]]. Perturbation
    names not in `lib.PERTURBATIONS` are still loaded so score.py can be a
    faithful mirror of whatever the harness ran; the aggregation lane averages
    only over the intersection with `lib.PERTURBATIONS`.
    """
    if root is None or not root.is_dir():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        out[child.name] = _load_outputs(child)
    return out


def _load_l3_ranking(path: Optional[Path]) -> Optional[List[str]]:
    """Load agent-submitted L3 ranking. Malformed input returns [] not None so
    the caller can differentiate absence (None) from malformed (empty)."""
    if path is None or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, str)]
    if isinstance(data, dict):
        maybe = data.get("ranking")
        if isinstance(maybe, list):
            return [x for x in maybe if isinstance(x, str)]
    return []


def _load_kill_reasons(path: Optional[Path]) -> List[str]:
    if path is None or not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, str)]
    if isinstance(data, dict):
        maybe = data.get("kill_reasons")
        if isinstance(maybe, list):
            return [x for x in maybe if isinstance(x, str)]
    return []


# ---------------------------------------------------------------------------
# Per-instance scoring primitives (L1 + L2)
# ---------------------------------------------------------------------------

def _status_agreement(oracle_status: str, reported_status: Optional[str]) -> bool:
    """Return True when reported status is compatible with oracle status.

    The oracle catalog binds ground-truth status. Compatibility semantics:
      - oracle=optimal: reported in {optimal, feasible} is accepted; feasible
        loses credit through L2's gap but does not fail L1.
      - oracle=infeasible: reported must be exactly infeasible.
      - oracle=unknown: reported unknown accepted; any concrete status
        contradicting an unknown oracle is treated as mismatch to keep the
        grader conservative under future oracle degradations.
    """
    if reported_status is None:
        return False
    if oracle_status == lib.STATUS_OPTIMAL:
        return reported_status in (lib.STATUS_OPTIMAL, lib.STATUS_FEASIBLE)
    if oracle_status == lib.STATUS_INFEASIBLE:
        return reported_status == lib.STATUS_INFEASIBLE
    if oracle_status == lib.STATUS_UNKNOWN:
        return reported_status == lib.STATUS_UNKNOWN
    if oracle_status == lib.STATUS_FEASIBLE:
        return reported_status in (lib.STATUS_OPTIMAL, lib.STATUS_FEASIBLE)
    return False


def _score_instance(
    instance: Dict[str, Any],
    output: Any,
    oracle_entry: Dict[str, Any],
) -> InstanceRecord:
    iid = instance["instance_id"]
    family = instance.get("family", "")
    oracle_status = str(oracle_entry.get("status", lib.STATUS_UNKNOWN))
    oracle_obj_raw = oracle_entry.get("objective_value")
    oracle_obj: Optional[float] = None
    if isinstance(oracle_obj_raw, (int, float)) and not isinstance(oracle_obj_raw, bool):
        oracle_obj = float(oracle_obj_raw)
    sense = instance["objective_sense"]

    schema_errors: List[str] = []
    schema_ok = False
    reported_status: Optional[str] = None
    reported_obj: Optional[float] = None
    variables_feasible = False
    feas_violations: List[str] = []

    if not isinstance(output, dict):
        schema_errors.append("output_not_dict")
    else:
        schema_ok, schema_errors = lib.validate_output_json(output, expected_instance_id=iid)
        if schema_ok:
            reported_status = str(output.get("status"))
            reported_obj_raw = output.get("objective_value")
            if isinstance(reported_obj_raw, (int, float)) and not isinstance(reported_obj_raw, bool):
                reported_obj = float(reported_obj_raw)
            variables = output.get("variables")
            if reported_status in (lib.STATUS_OPTIMAL, lib.STATUS_FEASIBLE) and isinstance(variables, list):
                feas_violations = lib.feasibility_violations(instance, variables)
                variables_feasible = not feas_violations
                if variables_feasible and reported_obj is None:
                    reported_obj = lib.compute_objective(instance, variables)

    status_match = _status_agreement(oracle_status, reported_status)

    # L1: structural pass = schema-valid + status agreement + (feasible vars OR
    # infeasibility/unknown declared). A submission that fails any leg fails L1.
    l1_reasons: List[str] = []
    l1_pass = True
    if not schema_ok:
        l1_pass = False
        l1_reasons.append(REASON_OUTPUT_SCHEMA_INVALID)
    if not status_match:
        l1_pass = False
        l1_reasons.append(REASON_STATUS_MISMATCH)
    if (
        reported_status in (lib.STATUS_OPTIMAL, lib.STATUS_FEASIBLE)
        and not variables_feasible
    ):
        l1_pass = False
        l1_reasons.append(REASON_VARIABLES_INFEASIBLE)

    # L2: optimality gap credit. Only meaningful when the oracle carries a
    # numeric objective AND the agent claims optimal/feasible AND variables are
    # feasible AND status match holds; anything else clamps L2 to zero.
    l2_gap: Optional[float] = None
    l2_credit = 0.0
    if (
        oracle_status == lib.STATUS_OPTIMAL
        and oracle_obj is not None
        and status_match
        and variables_feasible
        and reported_obj is not None
    ):
        l2_gap = lib.optimality_gap(reported_obj, oracle_obj, sense)
        l2_credit = lib.l2_credit_for_gap(l2_gap)
    elif oracle_status == lib.STATUS_INFEASIBLE and reported_status == lib.STATUS_INFEASIBLE:
        # Correct infeasibility declaration gets full L2 credit for the instance.
        l2_credit = 1.0

    return InstanceRecord(
        instance_id=iid,
        family=family,
        oracle_status=oracle_status,
        oracle_objective=oracle_obj,
        reported_status=reported_status,
        reported_objective=reported_obj,
        schema_ok=schema_ok,
        schema_errors=schema_errors,
        status_match=status_match,
        variables_feasible=variables_feasible,
        feasibility_violations=feas_violations,
        l1_pass=l1_pass,
        l1_reasons=l1_reasons,
        l2_gap=l2_gap,
        l2_credit=l2_credit,
        l4_trace_present=False,
        l4_trace_tokens=0,
        l4_credit=0.0,
    )


# ---------------------------------------------------------------------------
# Lane graders
# ---------------------------------------------------------------------------

def _grade_l1(records: Sequence[InstanceRecord]) -> Tuple[float, int]:
    if not records:
        return 0.0, 0
    passes = sum(1 for r in records if r.l1_pass)
    return passes / float(len(records)), passes


def _grade_l2(records: Sequence[InstanceRecord]) -> float:
    if not records:
        return 0.0
    total = sum(r.l2_credit for r in records)
    return total / float(len(records))


def _grade_l3(
    submitted_ranking: Optional[Sequence[str]],
    optima: Dict[str, Dict[str, Any]],
    zero_score_reasons: List[str],
) -> Tuple[float, Dict[str, Any]]:
    cohort = [
        (iid, entry)
        for iid, entry in optima.items()
        if entry.get("family") == lib.L3_TOPK_COHORT_FAMILY
    ]
    cohort.sort(
        key=lambda kv: (float(kv[1].get("solver_wall_seconds", 0.0)), kv[0]),
        reverse=True,
    )
    oracle_top = [iid for iid, _ in cohort[: lib.L3_TOPK_K]]
    details: Dict[str, Any] = {
        "cohort_size": len(cohort),
        "k": lib.L3_TOPK_K,
        "oracle_hardest_top_k": oracle_top,
        "submitted_top_k": [],
        "precision": 0.0,
    }
    if submitted_ranking is None:
        zero_score_reasons.append(REASON_L3_RANKING_ABSENT)
        return 0.0, details
    if not submitted_ranking:
        zero_score_reasons.append(REASON_L3_RANKING_MALFORMED)
        return 0.0, details
    valid_cohort_ids = {iid for iid, _ in cohort}
    filtered = [iid for iid in submitted_ranking if iid in valid_cohort_ids]
    precision = lib.top_k_precision(filtered, oracle_top, lib.L3_TOPK_K)
    details["submitted_top_k"] = filtered[: lib.L3_TOPK_K]
    details["precision"] = precision
    return precision, details


def _grade_l4(
    records: List[InstanceRecord],
    instances: Dict[str, Dict[str, Any]],
    optima: Dict[str, Dict[str, Any]],
    traces_dir: Optional[Path],
    zero_score_reasons: List[str],
) -> float:
    if traces_dir is None or not traces_dir.is_dir():
        zero_score_reasons.append(REASON_L4_TRACES_ABSENT)
        return 0.0
    credits: List[float] = []
    for record in records:
        oracle_entry = optima.get(record.instance_id, {})
        oracle_obj = oracle_entry.get("objective_value")
        if oracle_entry.get("status") != lib.STATUS_OPTIMAL or not isinstance(oracle_obj, (int, float)):
            credits.append(0.0)
            continue
        trace_text = _load_trace(traces_dir, record.instance_id)
        if trace_text is None:
            credits.append(0.0)
            continue
        record.l4_trace_present = True
        tokens = lib.parse_progression_tokens(trace_text)
        record.l4_trace_tokens = len(tokens)
        instance = instances[record.instance_id]
        credit = lib.anytime_progression_score(
            tokens,
            float(oracle_obj),
            instance["objective_sense"],
            lib.PER_INSTANCE_TIMEOUT_SEC,
        )
        record.l4_credit = credit
        credits.append(credit)
    if not credits:
        return 0.0
    return sum(credits) / float(len(credits))


def _grade_l5(
    base_records: Sequence[InstanceRecord],
    perturbations: Dict[str, Dict[str, Any]],
    instances: Dict[str, Dict[str, Any]],
    optima: Dict[str, Dict[str, Any]],
    zero_score_reasons: List[str],
    subset_ids: Optional[Sequence[str]] = None,
) -> Tuple[float, List[PerturbationRecord]]:
    if not perturbations:
        zero_score_reasons.append(REASON_L5_PERTURBATIONS_ABSENT)
        return 0.0, []

    # v2: the judge runs the sweep on a declared subset of the hidden set. Only
    # instances in that subset are compared; a subset instance with no usable
    # perturbed output still counts as a full loss (credit 0), so a solver that
    # crashes on perturbed input is not rewarded. Without a subset the whole
    # base cohort is expected, as in v1.
    if subset_ids:
        wanted = set(subset_ids)
        base_records = [r for r in base_records if r.instance_id in wanted]
        if not base_records:
            zero_score_reasons.append(REASON_L5_SUBSET_EMPTY)
            return 0.0, []

    # Base per-instance L2 credits keyed by instance_id for O(1) lookup.
    base_l2: Dict[str, float] = {r.instance_id: r.l2_credit for r in base_records}

    per_pert_records: List[PerturbationRecord] = []
    per_pert_credits: List[float] = []
    for pert_name in lib.PERTURBATIONS:
        perturbed_outputs = perturbations.get(pert_name)
        if perturbed_outputs is None:
            # Missing perturbation = zero contribution for that perturbation.
            per_pert_records.append(
                PerturbationRecord(
                    perturbation=pert_name,
                    per_instance_l2_credits=[],
                    base_matching_l2_credits=[],
                    robustness_credit=0.0,
                    missing_output_count=len(base_records),
                )
            )
            per_pert_credits.append(0.0)
            continue

        pert_l2: List[float] = []
        base_l2_aligned: List[float] = []
        missing = 0
        for record in base_records:
            output = perturbed_outputs.get(record.instance_id)
            if output is None:
                missing += 1
                pert_l2.append(0.0)
                base_l2_aligned.append(base_l2.get(record.instance_id, 0.0))
                continue
            instance = instances[record.instance_id]
            oracle_entry = optima.get(record.instance_id, {})
            perturbed_record = _score_instance(instance, output, oracle_entry)
            pert_l2.append(perturbed_record.l2_credit)
            base_l2_aligned.append(base_l2.get(record.instance_id, 0.0))
        robustness = lib.perturbation_robustness_score(base_l2_aligned, pert_l2)
        per_pert_records.append(
            PerturbationRecord(
                perturbation=pert_name,
                per_instance_l2_credits=pert_l2,
                base_matching_l2_credits=base_l2_aligned,
                robustness_credit=robustness,
                missing_output_count=missing,
            )
        )
        per_pert_credits.append(robustness)

    if not per_pert_credits:
        return 0.0, per_pert_records
    return sum(per_pert_credits) / float(len(per_pert_credits)), per_pert_records


# ---------------------------------------------------------------------------
# Reward document assembly
# ---------------------------------------------------------------------------

def _serialize_instance_record(record: InstanceRecord) -> Dict[str, Any]:
    return asdict(record)


def _serialize_perturbation_record(record: PerturbationRecord) -> Dict[str, Any]:
    return asdict(record)


def grade_submission(
    *,
    instances_dir: Path,
    optima_path: Path,
    outputs_dir: Path,
    traces_dir: Optional[Path] = None,
    perturbations_root: Optional[Path] = None,
    perturbation_subset_path: Optional[Path] = None,
    l3_ranking_path: Optional[Path] = None,
    kill_reasons_path: Optional[Path] = None,
    extra_kill_reasons: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Public grading entry point used by both the CLI and the author-side
    calibration orchestrator."""

    zero_score_reasons: List[str] = []

    if not instances_dir.is_dir():
        zero_score_reasons.append(REASON_NO_INSTANCES_DIR)
    if not optima_path.is_file():
        zero_score_reasons.append(REASON_NO_OPTIMA_FILE)
    if not outputs_dir.is_dir():
        zero_score_reasons.append(REASON_NO_OUTPUTS_DIR)

    instances = _load_instances(instances_dir)
    optima = _load_optima(optima_path)
    outputs = _load_outputs(outputs_dir)

    records: List[InstanceRecord] = []
    for iid in sorted(instances.keys()):
        instance = instances[iid]
        oracle_entry = optima.get(iid)
        if oracle_entry is None:
            continue
        output = outputs.get(iid)
        if output is None:
            record = InstanceRecord(
                instance_id=iid,
                family=instance.get("family", ""),
                oracle_status=str(oracle_entry.get("status", lib.STATUS_UNKNOWN)),
                oracle_objective=(
                    float(oracle_entry["objective_value"])
                    if isinstance(oracle_entry.get("objective_value"), (int, float))
                    else None
                ),
                reported_status=None,
                reported_objective=None,
                schema_ok=False,
                schema_errors=[REASON_INSTANCE_MISSING_OUTPUT],
                status_match=False,
                variables_feasible=False,
                feasibility_violations=[],
                l1_pass=False,
                l1_reasons=[REASON_INSTANCE_MISSING_OUTPUT],
                l2_gap=None,
                l2_credit=0.0,
                l4_trace_present=False,
                l4_trace_tokens=0,
                l4_credit=0.0,
            )
        else:
            record = _score_instance(instance, output, oracle_entry)
        records.append(record)

    l1_fraction, l1_pass_count = _grade_l1(records)
    l2_fraction = _grade_l2(records)

    submitted_ranking = _load_l3_ranking(l3_ranking_path)
    l3_fraction, l3_details = _grade_l3(submitted_ranking, optima, zero_score_reasons)

    l4_fraction = _grade_l4(records, instances, optima, traces_dir, zero_score_reasons)

    perturbations = _load_perturbations(perturbations_root)
    subset_ids: Optional[List[str]] = None
    if perturbation_subset_path is not None and perturbation_subset_path.is_file():
        subset_ids = [
            line.strip() for line in perturbation_subset_path.read_text().splitlines() if line.strip()
        ]
    l5_fraction, perturbation_records = _grade_l5(
        records, perturbations, instances, optima, zero_score_reasons, subset_ids
    )

    lane_scores = lib.aggregate_lane_totals(
        l1_fraction, l2_fraction, l3_fraction, l4_fraction, l5_fraction
    )
    raw_total = lane_scores["total"]

    file_kill = _load_kill_reasons(kill_reasons_path)
    kill_reasons_all: List[str] = list(file_kill)
    if extra_kill_reasons:
        kill_reasons_all.extend(x for x in extra_kill_reasons if isinstance(x, str))

    final_total, active_kill = lib.apply_kill_band(raw_total, kill_reasons_all)
    if active_kill:
        zero_score_reasons.append(REASON_KILL_BAND_TRIGGERED)

    document: Dict[str, Any] = {
        "schema_version": 1,
        "task_id": lib.TASK_ID,
        "score": final_total,
        "raw_total": raw_total,
        "score_direction": "maximize",
        "score_scale": [0, lib.TOTAL_POINTS],
        "lane_scores": {
            "L1_structural": lane_scores["L1_structural"],
            "L2_optimality_gap": lane_scores["L2_optimality_gap"],
            "L3_topk_precision": lane_scores["L3_topk_precision"],
            "L4_anytime_progression": lane_scores["L4_anytime_progression"],
            "L5_perturbation_robustness": lane_scores["L5_perturbation_robustness"],
        },
        "lane_fractions": {
            "L1_structural": l1_fraction,
            "L2_optimality_gap": l2_fraction,
            "L3_topk_precision": l3_fraction,
            "L4_anytime_progression": l4_fraction,
            "L5_perturbation_robustness": l5_fraction,
        },
        "lane_max_points": {
            "L1_structural": lib.LANE_L1_STRUCTURAL_POINTS,
            "L2_optimality_gap": lib.LANE_L2_OPTIMALITY_GAP_POINTS,
            "L3_topk_precision": lib.LANE_L3_TOPK_PRECISION_POINTS,
            "L4_anytime_progression": lib.LANE_L4_ANYTIME_PROGRESSION_POINTS,
            "L5_perturbation_robustness": lib.LANE_L5_PERTURBATION_ROBUSTNESS_POINTS,
        },
        "counts": {
            "instances_evaluated": len(records),
            "instances_l1_pass": l1_pass_count,
            "instances_declared": len(instances),
            "oracle_entries": len(optima),
            "output_files_present": len(outputs),
            "perturbations_present": sorted(perturbations.keys()),
            "perturbation_subset_size": len(subset_ids) if subset_ids else None,
        },
        "l3_details": l3_details,
        "perturbation_scores": {
            r.perturbation: r.robustness_credit for r in perturbation_records
        },
        "kill_reasons": active_kill,
        "kill_reasons_reported": kill_reasons_all,
        "zero_score_reasons": zero_score_reasons,
        "per_instance": [_serialize_instance_record(r) for r in records],
        "per_perturbation": [_serialize_perturbation_record(r) for r in perturbation_records],
    }
    return document


def emit_reward_document(document: Dict[str, Any], reward_out: Path) -> None:
    """Write the reward JSON to reward_out with deterministic key ordering."""
    reward_out.parent.mkdir(parents=True, exist_ok=True)
    with reward_out.open("w", encoding="utf-8") as fh:
        json.dump(document, fh, sort_keys=True, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="p6zeta 5-lane grader",
        add_help=True,
    )
    parser.add_argument("--instances", required=True, type=Path)
    parser.add_argument("--optima", required=True, type=Path)
    parser.add_argument("--outputs", required=True, type=Path)
    parser.add_argument("--traces", type=Path, default=None)
    parser.add_argument("--perturbations-root", type=Path, default=None)
    parser.add_argument("--perturbation-subset", type=Path, default=None,
                        help="File with one instance_id per line: the subset the sweep ran on (v2)")
    parser.add_argument("--l3-ranking", type=Path, default=None)
    parser.add_argument("--kill-reasons-file", type=Path, default=None)
    parser.add_argument("--reward-out", type=Path, default=Path(lib.REWARD_CONTRACT_PATH))
    parser.add_argument(
        "--extra-kill-reason",
        action="append",
        default=[],
        help="Kill reason detected by the harness beyond the file-based list.",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Emit a one-line human-readable summary to stdout after writing.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    document = grade_submission(
        instances_dir=args.instances,
        optima_path=args.optima,
        outputs_dir=args.outputs,
        traces_dir=args.traces,
        perturbations_root=args.perturbations_root,
        perturbation_subset_path=args.perturbation_subset,
        l3_ranking_path=args.l3_ranking,
        kill_reasons_path=args.kill_reasons_file,
        extra_kill_reasons=args.extra_kill_reason,
    )
    emit_reward_document(document, args.reward_out)
    if args.print_summary:
        counts = document["counts"]
        lanes = document["lane_scores"]
        print(
            (
                "score={score:.2f}/{total} l1={l1:.2f} l2={l2:.2f} "
                "l3={l3:.2f} l4={l4:.2f} l5={l5:.2f} "
                "n_eval={n} pass_l1={p} kill={kill}"
            ).format(
                score=document["score"],
                total=lib.TOTAL_POINTS,
                l1=lanes["L1_structural"],
                l2=lanes["L2_optimality_gap"],
                l3=lanes["L3_topk_precision"],
                l4=lanes["L4_anytime_progression"],
                l5=lanes["L5_perturbation_robustness"],
                n=counts["instances_evaluated"],
                p=counts["instances_l1_pass"],
                kill=document["kill_reasons"],
            )
        )
    return 0


__all__ = [
    "InstanceRecord",
    "PerturbationRecord",
    "grade_submission",
    "emit_reward_document",
    "main",
    "REASON_NO_OUTPUTS_DIR",
    "REASON_NO_INSTANCES_DIR",
    "REASON_NO_OPTIMA_FILE",
    "REASON_INSTANCE_MISSING_OUTPUT",
    "REASON_OUTPUT_SCHEMA_INVALID",
    "REASON_STATUS_MISMATCH",
    "REASON_VARIABLES_INFEASIBLE",
    "REASON_L3_RANKING_ABSENT",
    "REASON_L3_RANKING_MALFORMED",
    "REASON_L4_TRACES_ABSENT",
    "REASON_L5_PERTURBATIONS_ABSENT",
    "REASON_KILL_BAND_TRIGGERED",
]


if __name__ == "__main__":
    sys.exit(main())
