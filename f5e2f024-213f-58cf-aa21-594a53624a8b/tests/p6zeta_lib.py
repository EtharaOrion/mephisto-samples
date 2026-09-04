"""Public metric library for edgebench.p6zeta_zero_one_ip_solver_from_scratch.

Byte-identical copy lives in:
- work image /home/workspace/p6zeta/p6zeta_lib.py       (agent-visible)
- judge image /home/workspace/scoring/p6zeta_lib.py     (judge-side, imported by score.py)

Per FORGE.md invariant 22, the reference SOLVER method is judge-side only in
solution/reference_solver.py and MUST NOT appear on any agent surface. The
SCORING method is fully public here: every lane point constant, K constant,
threshold, penalty binding, and formula.

Task family is combinatorial-optimization, Framework A (outcome-anchored on
author-computed optima). Instances are pure 0-1 integer programs across seven
sub-families (set-cover, zero-one-knapsack, graph-coloring-ip, tsp-cutting-
plane-ip, generalized-assignment, capacitated-facility-location, multi-
dimensional-knapsack). The evaluator calls the submitted solver once per
frozen instance, parses the output JSON, and aggregates a 5-lane 0-100 score.

Ranking convention:
  optimum objective is the author-computed exact optimum from the hidden
  optima book. Optimality gap for a maximization instance is
    max(0, (optimum - reported_obj) / max(abs(optimum), 1)); for a
  minimization instance it is
    max(0, (reported_obj - optimum) / max(abs(optimum), 1)); infeasible
  claims on feasible instances receive gap=infinity handled as full penalty.

Stdlib-only, no numpy/pandas/scipy. Python 3.10+.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Genesis-pinned constants
# ---------------------------------------------------------------------------

FORGE_TASK_NAMESPACE = uuid.UUID("c53e8f3b-526f-52c0-a04e-89e2269b237d")

TASK_ID = "p6zeta_zero_one_ip_solver_from_scratch"

# ---------------------------------------------------------------------------
# Cohort structure (frozen at Phase 1)
# ---------------------------------------------------------------------------

FAMILY_SET_COVER = "set-cover"
FAMILY_ZERO_ONE_KNAPSACK = "zero-one-knapsack"
FAMILY_GRAPH_COLORING_IP = "graph-coloring-ip"
FAMILY_TSP_CUTTING_PLANE_IP = "tsp-cutting-plane-ip"
FAMILY_GENERALIZED_ASSIGNMENT = "generalized-assignment"
FAMILY_CAPACITATED_FACILITY_LOCATION = "capacitated-facility-location"
FAMILY_MULTI_DIMENSIONAL_KNAPSACK = "multi-dimensional-knapsack"

FAMILIES: Tuple[str, ...] = (
    FAMILY_SET_COVER,
    FAMILY_ZERO_ONE_KNAPSACK,
    FAMILY_GRAPH_COLORING_IP,
    FAMILY_TSP_CUTTING_PLANE_IP,
    FAMILY_GENERALIZED_ASSIGNMENT,
    FAMILY_CAPACITATED_FACILITY_LOCATION,
    FAMILY_MULTI_DIMENSIONAL_KNAPSACK,
)

# Instance counts per contract: 10 primary per family across 6 primary
# families (60) + one family (multi-dimensional-knapsack) serves as the L3
# stress sub-cohort at 30 instances -> total 90 hidden instances.
INSTANCES_PER_PRIMARY_FAMILY = 10
PRIMARY_FAMILIES: Tuple[str, ...] = (
    FAMILY_SET_COVER,
    FAMILY_ZERO_ONE_KNAPSACK,
    FAMILY_GRAPH_COLORING_IP,
    FAMILY_TSP_CUTTING_PLANE_IP,
    FAMILY_GENERALIZED_ASSIGNMENT,
    FAMILY_CAPACITATED_FACILITY_LOCATION,
)
L3_STRESS_FAMILY = FAMILY_MULTI_DIMENSIONAL_KNAPSACK
L3_STRESS_INSTANCE_COUNT = 30
HIDDEN_INSTANCE_TOTAL = (
    INSTANCES_PER_PRIMARY_FAMILY * len(PRIMARY_FAMILIES) + L3_STRESS_INSTANCE_COUNT
)
DEV_INSTANCE_COUNT = 6

# ---------------------------------------------------------------------------
# Objective conventions
# ---------------------------------------------------------------------------

SENSE_MAXIMIZE = "max"
SENSE_MINIMIZE = "min"
SENSES: Tuple[str, ...] = (SENSE_MAXIMIZE, SENSE_MINIMIZE)

CONSTRAINT_LE = "<="
CONSTRAINT_GE = ">="
CONSTRAINT_EQ = "=="
CONSTRAINT_SENSES: Tuple[str, ...] = (CONSTRAINT_LE, CONSTRAINT_GE, CONSTRAINT_EQ)

STATUS_OPTIMAL = "optimal"
STATUS_FEASIBLE = "feasible"
STATUS_INFEASIBLE = "infeasible"
STATUS_UNKNOWN = "unknown"
STATUSES: Tuple[str, ...] = (
    STATUS_OPTIMAL,
    STATUS_FEASIBLE,
    STATUS_INFEASIBLE,
    STATUS_UNKNOWN,
)

# ---------------------------------------------------------------------------
# Grading lane point budget (must sum to TOTAL_POINTS)
# ---------------------------------------------------------------------------

LANE_L1_STRUCTURAL_POINTS = 10
LANE_L2_OPTIMALITY_GAP_POINTS = 30
LANE_L3_TOPK_PRECISION_POINTS = 25
LANE_L4_ANYTIME_PROGRESSION_POINTS = 20
LANE_L5_PERTURBATION_ROBUSTNESS_POINTS = 15
TOTAL_POINTS = (
    LANE_L1_STRUCTURAL_POINTS
    + LANE_L2_OPTIMALITY_GAP_POINTS
    + LANE_L3_TOPK_PRECISION_POINTS
    + LANE_L4_ANYTIME_PROGRESSION_POINTS
    + LANE_L5_PERTURBATION_ROBUSTNESS_POINTS
)
assert TOTAL_POINTS == 100

# L2 optimality-gap threshold curve: piecewise per-instance credit, mean over
# the cohort scaled to LANE_L2_OPTIMALITY_GAP_POINTS. Curve is monotone-
# non-increasing in gap; infeasibility claim on feasible instance floors to 0.
L2_THRESHOLD_CURVE: Tuple[Tuple[float, float], ...] = (
    (0.00, 1.00),
    (0.02, 0.90),
    (0.05, 0.80),
    (0.10, 0.60),
    (0.20, 0.33),
    (0.35, 0.13),
)
L2_FLOOR = 0.0

# L3 top-K precision: on the L3 stress sub-cohort, rank instances by
# solution objective density (relative to optimum) and score precision-at-K
# against the hardest-K oracle set. K is fixed at 8 for the 30-instance
# stress cohort.
L3_TOPK_K = 8
L3_TOPK_COHORT_FAMILY = L3_STRESS_FAMILY

# L4 anytime progression: submitted solver must write per-instance
# intermediate best-objective values on stderr (BEST tokens with a
# monotonic timestamp). Score = mean over instances of the area under the
# normalized (best_obj / optimum) x (time / instance_timeout) curve, clipped
# to [0, 1]. Missing progression trace scores 0 for that instance.
L4_MIN_PROGRESSION_TOKENS = 2
L4_BEST_TOKEN_REGEX = re.compile(
    r"^BEST\s+ts=(?P<ts>-?\d+(?:\.\d+)?)\s+obj=(?P<obj>-?\d+(?:\.\d+)?)\s*$",
)

# L5 perturbation robustness: 7 named perturbations applied at judge time.
# For each perturbation, rerun the solver on the perturbed cohort, then
# score = 1 - mean_absolute_delta(base_L2_per_instance, perturbed_L2_per_instance)
# clipped to [0, 1]. Report mean across 7 perturbations.
PERTURBATIONS: Tuple[str, ...] = (
    "variable_order_within_constraint",
    "constraint_reorder",
    "coefficient_common_scale",
    "instance_id_salt_rewrite",
    "json_whitespace_reformat",
    "output_json_field_order",
    "output_json_trailing_whitespace",
)

# Per-instance wall-clock timeout (seconds); judged in tests/score.py.
PER_INSTANCE_TIMEOUT_SEC = 60
JUDGE_PARALLEL_WORKERS = 16
JUDGE_WHOLE_RUN_BUDGET_SEC = 7200

# ---------------------------------------------------------------------------
# KILL band (score -> 0 for entire submission)
# ---------------------------------------------------------------------------

KILL_REASON_FORBIDDEN_LIBRARY = "forbidden_library"
KILL_REASON_NETWORK_EGRESS = "network_egress"
KILL_REASON_PRIVATE_ARTIFACT_READ = "private_artifact_read"
KILL_REASON_SHORTCUT_MINE_AND_RETURN = "shortcut_mine_and_return"

KILL_REASONS: Tuple[str, ...] = (
    KILL_REASON_FORBIDDEN_LIBRARY,
    KILL_REASON_NETWORK_EGRESS,
    KILL_REASON_PRIVATE_ARTIFACT_READ,
    KILL_REASON_SHORTCUT_MINE_AND_RETURN,
)

# Forbidden library import stems detected by shortcut-probe library scan.
# Mirrors seed/contract.yaml service_exclusions block byte-for-byte.
FORBIDDEN_LIBRARY_STEMS: Tuple[str, ...] = (
    "cplex",
    "docplex",
    "gurobi",
    "gurobipy",
    "ortools",
    "or_tools",
    "pulp",
    "cbc",
    "coinor_cbc",
    "coinor",
    "glpk",
    "glpsol",
    "pyglpk",
    "scip",
    "pyscipopt",
    "highs",
    "highspy",
    "mosek",
    "xpress",
    "cvxpy",
    "cvxopt",
    "pymip",
    "python_mip",
    "mip",
    "amply",
    "miplearn",
    "z3",
    "cvc5",
    "minisat",
    "kissat",
    "cadical",
    "lingeling",
    "plingeling",
)
FORBIDDEN_SCIPY_ATTRS: Tuple[str, ...] = (
    "scipy.optimize.milp",
    "scipy.optimize.linprog",
)

# ---------------------------------------------------------------------------
# Deliverable paths (agent-side and judge-side)
# ---------------------------------------------------------------------------

AGENT_WORKDIR = "/home/workspace/p6zeta"
JUDGE_WORKDIR = "/home/workspace/p6zeta"
SUBMIT_PATHS: Tuple[str, ...] = ("build.sh", "solve", "src/")
INSTANCE_INPUT_DIRNAME = "hidden_benchmarks"
INSTANCE_INPUT_SUFFIX = ".ip.json"
SOLVER_ENTRYPOINT = "./solve"

REWARD_CONTRACT_PATH = "/tmp/reward.json"


# ---------------------------------------------------------------------------
# Schema validators
# ---------------------------------------------------------------------------

INSTANCE_REQUIRED_KEYS: Tuple[str, ...] = (
    "instance_id",
    "family",
    "n_vars",
    "objective_sense",
    "objective_coefficients",
    "constraints",
)
INSTANCE_OPTIONAL_KEYS: Tuple[str, ...] = ("comment",)

CONSTRAINT_REQUIRED_KEYS: Tuple[str, ...] = ("coefficients", "rhs", "sense")

OUTPUT_REQUIRED_KEYS: Tuple[str, ...] = (
    "instance_id",
    "status",
    "variables",
    "objective_value",
)


def validate_instance_json(obj: Any) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    if not isinstance(obj, dict):
        return False, ["instance_not_object"]
    for k in INSTANCE_REQUIRED_KEYS:
        if k not in obj:
            problems.append(f"instance_missing_key:{k}")
    for k in obj.keys():
        if k not in INSTANCE_REQUIRED_KEYS and k not in INSTANCE_OPTIONAL_KEYS:
            problems.append(f"instance_unknown_key:{k}")
    if problems:
        return False, problems
    if not isinstance(obj["instance_id"], str) or not obj["instance_id"]:
        problems.append("instance_id_not_nonempty_string")
    if obj["family"] not in FAMILIES:
        problems.append(f"instance_family_unknown:{obj['family']!r}")
    n_vars = obj["n_vars"]
    if not isinstance(n_vars, int) or n_vars <= 0:
        problems.append(f"n_vars_not_positive_int:{n_vars!r}")
    if obj["objective_sense"] not in SENSES:
        problems.append(f"objective_sense_unknown:{obj['objective_sense']!r}")
    coeffs = obj["objective_coefficients"]
    if not isinstance(coeffs, list) or len(coeffs) != n_vars:
        problems.append("objective_coefficients_length_mismatch")
    else:
        for i, c in enumerate(coeffs):
            if not isinstance(c, (int, float)) or isinstance(c, bool):
                problems.append(f"objective_coefficient_not_numeric:{i}")
    cons = obj["constraints"]
    if not isinstance(cons, list) or not cons:
        problems.append("constraints_not_nonempty_list")
    else:
        for ci, con in enumerate(cons):
            if not isinstance(con, dict):
                problems.append(f"constraint_{ci}_not_object")
                continue
            for k in CONSTRAINT_REQUIRED_KEYS:
                if k not in con:
                    problems.append(f"constraint_{ci}_missing_key:{k}")
            if "sense" in con and con["sense"] not in CONSTRAINT_SENSES:
                problems.append(f"constraint_{ci}_sense_unknown:{con['sense']!r}")
            if "coefficients" in con:
                cc = con["coefficients"]
                if not isinstance(cc, list) or len(cc) != n_vars:
                    problems.append(f"constraint_{ci}_coefficients_length_mismatch")
                else:
                    for j, v in enumerate(cc):
                        if not isinstance(v, (int, float)) or isinstance(v, bool):
                            problems.append(f"constraint_{ci}_coefficient_{j}_not_numeric")
            if "rhs" in con:
                r = con["rhs"]
                if not isinstance(r, (int, float)) or isinstance(r, bool):
                    problems.append(f"constraint_{ci}_rhs_not_numeric")
    return (not problems), problems


def validate_output_json(obj: Any, expected_instance_id: Optional[str] = None) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    if not isinstance(obj, dict):
        return False, ["output_not_object"]
    for k in OUTPUT_REQUIRED_KEYS:
        if k not in obj:
            problems.append(f"output_missing_key:{k}")
    if problems:
        return False, problems
    if not isinstance(obj["instance_id"], str) or not obj["instance_id"]:
        problems.append("output_instance_id_not_nonempty_string")
    if expected_instance_id is not None and obj["instance_id"] != expected_instance_id:
        problems.append(
            f"output_instance_id_mismatch:got={obj['instance_id']!r}:expected={expected_instance_id!r}"
        )
    if obj["status"] not in STATUSES:
        problems.append(f"output_status_unknown:{obj['status']!r}")
    if obj["status"] in (STATUS_OPTIMAL, STATUS_FEASIBLE):
        variables = obj["variables"]
        if not isinstance(variables, list):
            problems.append("output_variables_not_list")
        else:
            for i, v in enumerate(variables):
                if v not in (0, 1):
                    problems.append(f"output_variable_{i}_not_binary:{v!r}")
        ov = obj["objective_value"]
        if not isinstance(ov, (int, float)) or isinstance(ov, bool):
            problems.append("output_objective_value_not_numeric")
    elif obj["status"] in (STATUS_INFEASIBLE, STATUS_UNKNOWN):
        variables = obj["variables"]
        if variables not in (None, [], ):
            if not (isinstance(variables, list) and all(v in (0, 1) for v in variables)):
                problems.append("output_variables_should_be_null_or_binary_list_for_nonsolved")
        ov = obj["objective_value"]
        if ov is not None and not isinstance(ov, (int, float)):
            problems.append("output_objective_value_should_be_null_or_numeric_for_nonsolved")
    return (not problems), problems


# ---------------------------------------------------------------------------
# Feasibility and objective computation
# ---------------------------------------------------------------------------

def compute_objective(instance: Dict[str, Any], variables: Sequence[int]) -> float:
    c = instance["objective_coefficients"]
    return float(sum(ci * xi for ci, xi in zip(c, variables)))


def feasibility_violations(
    instance: Dict[str, Any],
    variables: Sequence[int],
    tolerance: float = 1e-9,
) -> List[str]:
    problems: List[str] = []
    if len(variables) != instance["n_vars"]:
        problems.append("variables_length_mismatch")
        return problems
    for ci, con in enumerate(instance["constraints"]):
        lhs = sum(a * x for a, x in zip(con["coefficients"], variables))
        rhs = con["rhs"]
        sense = con["sense"]
        if sense == CONSTRAINT_LE and lhs > rhs + tolerance:
            problems.append(f"constraint_{ci}_le_violated:{lhs}>{rhs}")
        elif sense == CONSTRAINT_GE and lhs < rhs - tolerance:
            problems.append(f"constraint_{ci}_ge_violated:{lhs}<{rhs}")
        elif sense == CONSTRAINT_EQ and abs(lhs - rhs) > tolerance:
            problems.append(f"constraint_{ci}_eq_violated:{lhs}!={rhs}")
    return problems


# ---------------------------------------------------------------------------
# L2 threshold-curve credit
# ---------------------------------------------------------------------------

def optimality_gap(reported_obj: float, optimum: float, sense: str) -> float:
    denom = max(abs(optimum), 1.0)
    if sense == SENSE_MAXIMIZE:
        return max(0.0, (optimum - reported_obj) / denom)
    if sense == SENSE_MINIMIZE:
        return max(0.0, (reported_obj - optimum) / denom)
    raise ValueError(f"unknown sense:{sense!r}")


def l2_credit_for_gap(gap: float) -> float:
    if gap != gap or gap == math.inf:
        return L2_FLOOR
    prev_gap, prev_credit = L2_THRESHOLD_CURVE[0]
    if gap <= prev_gap:
        return prev_credit
    for next_gap, next_credit in L2_THRESHOLD_CURVE[1:]:
        if gap <= next_gap:
            return next_credit
        prev_gap, prev_credit = next_gap, next_credit
    return L2_FLOOR


# ---------------------------------------------------------------------------
# L3 top-K precision on the stress sub-cohort
# ---------------------------------------------------------------------------

def top_k_precision(
    submitted_ranked_ids: Sequence[str],
    oracle_hardest_ids: Sequence[str],
    k: int,
) -> float:
    if k <= 0:
        return 0.0
    top_submitted = list(submitted_ranked_ids)[:k]
    oracle_set = set(list(oracle_hardest_ids)[:k])
    if not oracle_set:
        return 0.0
    hits = sum(1 for x in top_submitted if x in oracle_set)
    return hits / float(k)


# ---------------------------------------------------------------------------
# L4 anytime progression: area under normalized best-so-far curve
# ---------------------------------------------------------------------------

def parse_progression_tokens(stderr_text: str) -> List[Tuple[float, float]]:
    trace: List[Tuple[float, float]] = []
    for line in stderr_text.splitlines():
        m = L4_BEST_TOKEN_REGEX.match(line.strip())
        if not m:
            continue
        trace.append((float(m.group("ts")), float(m.group("obj"))))
    return trace


def anytime_progression_score(
    trace: Sequence[Tuple[float, float]],
    optimum: float,
    sense: str,
    timeout_sec: float,
) -> float:
    if timeout_sec <= 0:
        return 0.0
    if len(trace) < L4_MIN_PROGRESSION_TOKENS:
        return 0.0
    denom = max(abs(optimum), 1.0)
    points: List[Tuple[float, float]] = []
    best_so_far: Optional[float] = None
    last_ts = 0.0
    for ts, obj in sorted(trace, key=lambda t: t[0]):
        if ts < 0 or ts > timeout_sec:
            continue
        if sense == SENSE_MAXIMIZE:
            candidate = obj
            if best_so_far is None or candidate > best_so_far:
                best_so_far = candidate
        else:
            candidate = -obj
            if best_so_far is None or candidate > best_so_far:
                best_so_far = candidate
        display = best_so_far if sense == SENSE_MAXIMIZE else -best_so_far
        credit = max(0.0, 1.0 - optimality_gap(display, optimum, sense))
        points.append((ts, credit))
        last_ts = ts
    if not points:
        return 0.0
    if last_ts < timeout_sec:
        points.append((timeout_sec, points[-1][1]))
    area = 0.0
    prev_ts, prev_credit = 0.0, 0.0
    for ts, credit in points:
        area += (ts - prev_ts) * prev_credit
        prev_ts, prev_credit = ts, credit
    return max(0.0, min(1.0, area / timeout_sec))


# ---------------------------------------------------------------------------
# L5 perturbation robustness
# ---------------------------------------------------------------------------

def perturbation_robustness_score(
    base_per_instance_credits: Sequence[float],
    perturbed_per_instance_credits: Sequence[float],
) -> float:
    if len(base_per_instance_credits) != len(perturbed_per_instance_credits):
        return 0.0
    if not base_per_instance_credits:
        return 0.0
    n = len(base_per_instance_credits)
    delta_sum = 0.0
    for b, p in zip(base_per_instance_credits, perturbed_per_instance_credits):
        delta_sum += abs(float(b) - float(p))
    return max(0.0, min(1.0, 1.0 - delta_sum / n))


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_lane_totals(
    l1_fraction: float,
    l2_fraction: float,
    l3_fraction: float,
    l4_fraction: float,
    l5_fraction: float,
) -> Dict[str, float]:
    def clip(x: float) -> float:
        return max(0.0, min(1.0, float(x)))
    l1 = clip(l1_fraction) * LANE_L1_STRUCTURAL_POINTS
    l2 = clip(l2_fraction) * LANE_L2_OPTIMALITY_GAP_POINTS
    l3 = clip(l3_fraction) * LANE_L3_TOPK_PRECISION_POINTS
    l4 = clip(l4_fraction) * LANE_L4_ANYTIME_PROGRESSION_POINTS
    l5 = clip(l5_fraction) * LANE_L5_PERTURBATION_ROBUSTNESS_POINTS
    total = l1 + l2 + l3 + l4 + l5
    return {
        "L1_structural": l1,
        "L2_optimality_gap": l2,
        "L3_topk_precision": l3,
        "L4_anytime_progression": l4,
        "L5_perturbation_robustness": l5,
        "total": total,
    }


def apply_kill_band(total_score: float, kill_reasons: Sequence[str]) -> Tuple[float, List[str]]:
    hits = [r for r in kill_reasons if r in KILL_REASONS]
    if hits:
        return 0.0, hits
    return float(total_score), []


# ---------------------------------------------------------------------------
# Canonical bundle hashing for uuid5 derivation
# ---------------------------------------------------------------------------

BUNDLE_EXCLUDE_PREFIXES: Tuple[str, ...] = (
    "trajectories/",
    ".git/",
    "__pycache__/",
)
BUNDLE_EXCLUDE_SUFFIXES: Tuple[str, ...] = (
    ".pyc",
)


def _iter_bundle_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
        for name in sorted(filenames):
            rel = os.path.join(rel_dir, name) if rel_dir else name
            rel_posix = rel.replace(os.sep, "/")
            if any(rel_posix.startswith(p) for p in BUNDLE_EXCLUDE_PREFIXES):
                continue
            if any(rel_posix.endswith(s) for s in BUNDLE_EXCLUDE_SUFFIXES):
                continue
            files.append(Path(dirpath) / name)
    return files


def canonical_bundle_hash(bundle_root: Path) -> str:
    root = Path(bundle_root).resolve()
    h = hashlib.sha256()
    for f in _iter_bundle_files(root):
        rel = f.resolve().relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        with open(f, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        h.update(b"\x01")
    return h.hexdigest()


def derive_bundle_uuid(canonical_hash: str) -> uuid.UUID:
    return uuid.uuid5(FORGE_TASK_NAMESPACE, canonical_hash)


# ---------------------------------------------------------------------------
# HKDF-SHA256 for canary token derivation
# ---------------------------------------------------------------------------

def hkdf_sha256(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    if length > 32 * 255:
        raise ValueError("hkdf output length too large")
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b""
    t = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]


def derive_canary_token(bundle_hash_hex: str, purpose: str, index: int) -> str:
    ikm = bytes.fromhex(bundle_hash_hex)
    salt = b"p6zeta-canary-v1"
    info = f"{purpose}|{index}".encode("utf-8")
    raw = hkdf_sha256(salt, ikm, info, 16)
    return "MEPHISTO_CANARY_P6Z_" + raw.hex().upper()


# ---------------------------------------------------------------------------
# Shortcut-detection utility (used at author time and in tests/score.py)
# ---------------------------------------------------------------------------

_IMPORT_RE = re.compile(r"^\s*import\s+([\w\.]+)", re.MULTILINE)
_FROM_IMPORT_RE = re.compile(
    r"^[ \t]*from[ \t]+([\w\.]+)[ \t]+import[ \t]+([\w\.\*,\ \t]+)", re.MULTILINE
)


def _check_forbidden(mod: str, hits: List[str]) -> None:
    head = mod.split(".")[0]
    if head in FORBIDDEN_LIBRARY_STEMS:
        hits.append(mod)
    for attr in FORBIDDEN_SCIPY_ATTRS:
        if mod == attr or mod.startswith(attr + "."):
            hits.append(mod)


def scan_forbidden_imports(source_text: str) -> List[str]:
    hits: List[str] = []
    for match in _IMPORT_RE.finditer(source_text):
        _check_forbidden(match.group(1), hits)
    for match in _FROM_IMPORT_RE.finditer(source_text):
        base = match.group(1)
        _check_forbidden(base, hits)
        for name in match.group(2).split(","):
            name = name.strip().split(" as ")[0].strip()
            if not name or name == "*":
                continue
            _check_forbidden(f"{base}.{name}", hits)
    if "subprocess" in source_text:
        for stem in FORBIDDEN_LIBRARY_STEMS:
            pattern = re.compile(r"['\"]" + re.escape(stem) + r"['\"]")
            if pattern.search(source_text):
                hits.append(f"subprocess_ref:{stem}")
    return hits


# ---------------------------------------------------------------------------
# JSON I/O helpers with canonical serialization for hashing
# ---------------------------------------------------------------------------

def dump_canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def load_json_file(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json_file(path: Path, obj: Any, sort_keys: bool = True) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=sort_keys, indent=2)
        fh.write("\n")


__all__ = [
    "FORGE_TASK_NAMESPACE",
    "TASK_ID",
    "FAMILIES",
    "PRIMARY_FAMILIES",
    "L3_STRESS_FAMILY",
    "L3_STRESS_INSTANCE_COUNT",
    "INSTANCES_PER_PRIMARY_FAMILY",
    "HIDDEN_INSTANCE_TOTAL",
    "DEV_INSTANCE_COUNT",
    "SENSE_MAXIMIZE",
    "SENSE_MINIMIZE",
    "SENSES",
    "CONSTRAINT_LE",
    "CONSTRAINT_GE",
    "CONSTRAINT_EQ",
    "CONSTRAINT_SENSES",
    "STATUS_OPTIMAL",
    "STATUS_FEASIBLE",
    "STATUS_INFEASIBLE",
    "STATUS_UNKNOWN",
    "STATUSES",
    "LANE_L1_STRUCTURAL_POINTS",
    "LANE_L2_OPTIMALITY_GAP_POINTS",
    "LANE_L3_TOPK_PRECISION_POINTS",
    "LANE_L4_ANYTIME_PROGRESSION_POINTS",
    "LANE_L5_PERTURBATION_ROBUSTNESS_POINTS",
    "TOTAL_POINTS",
    "L2_THRESHOLD_CURVE",
    "L3_TOPK_K",
    "L4_MIN_PROGRESSION_TOKENS",
    "L4_BEST_TOKEN_REGEX",
    "PERTURBATIONS",
    "PER_INSTANCE_TIMEOUT_SEC",
    "JUDGE_PARALLEL_WORKERS",
    "JUDGE_WHOLE_RUN_BUDGET_SEC",
    "KILL_REASONS",
    "FORBIDDEN_LIBRARY_STEMS",
    "FORBIDDEN_SCIPY_ATTRS",
    "AGENT_WORKDIR",
    "JUDGE_WORKDIR",
    "SUBMIT_PATHS",
    "INSTANCE_INPUT_DIRNAME",
    "INSTANCE_INPUT_SUFFIX",
    "SOLVER_ENTRYPOINT",
    "REWARD_CONTRACT_PATH",
    "validate_instance_json",
    "validate_output_json",
    "compute_objective",
    "feasibility_violations",
    "optimality_gap",
    "l2_credit_for_gap",
    "top_k_precision",
    "parse_progression_tokens",
    "anytime_progression_score",
    "perturbation_robustness_score",
    "aggregate_lane_totals",
    "apply_kill_band",
    "canonical_bundle_hash",
    "derive_bundle_uuid",
    "hkdf_sha256",
    "derive_canary_token",
    "scan_forbidden_imports",
    "dump_canonical_json",
    "load_json_file",
    "dump_json_file",
]
