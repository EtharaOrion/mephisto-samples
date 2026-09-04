"""
reference_solver.py — p6zeta reference oracle for 0-1 Integer Programming.

PRIVATE, JUDGE-ONLY ARTIFACT. Ships in dataset/<uuid>/solution/reference_solver.py.
NEVER appears on the agent-visible surface. Boundary is enforced by FORGE invariant 22.

From-scratch branch-and-bound over binary variables using pure-Python primal simplex
for the LP relaxation. No numpy, no scipy, no external solvers. Deliberately naive
so that self-scoring through score.py lands in the calibration band [0.20, 0.40] of
100 points. The oracle demonstrates that a legitimate from-scratch solver exists
inside the delivered service and budget constraints; it is not a frontier solver.

Ranking convention for reporting: max -> larger objective is better; min -> smaller
objective is better. Interior optimality-gap semantics follow p6zeta_lib.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import p6zeta_lib as lib

# ---------------------------------------------------------------------------
# LP simplex constants
# ---------------------------------------------------------------------------

BIGM = 1.0e7                    # Artificial-variable penalty (min form)
SIMPLEX_EPS = 1.0e-9            # Ratio / pivot tolerance
SIMPLEX_MAX_ITERS = 2_000       # Loop cap tuned for calibration band [0.20, 0.40]; larger LPs hit iter-limit, propagating to B&B `unknown` on hard instances
INT_TOL = 1.0e-6                # Integrality tolerance for B&B rounding checks
FRACTIONAL_TOL = 1.0e-6         # Distance from 0/1 that still counts as fractional
BB_NODE_LIMIT = 200_000         # Hard node cap on top of wall-clock timeout

LP_OPTIMAL = "optimal"
LP_INFEASIBLE = "infeasible"
LP_UNBOUNDED = "unbounded"
LP_ITERATION_LIMIT = "iteration_limit"

# ---------------------------------------------------------------------------
# Primal simplex over Ax = b, x >= 0 (min form). Big-M for artificial rows.
# ---------------------------------------------------------------------------


def _simplex_min(
    c: List[float],
    A: List[List[float]],
    b: List[float],
    artificial_cols: List[int],
    max_iters: int = SIMPLEX_MAX_ITERS,
) -> Tuple[str, float, List[float]]:
    """
    Solve min c^T x s.t. Ax = b, x >= 0 by primal simplex.

    Assumes an initial basic feasible solution can be read off from a set of
    identity columns supplied to the caller (typically slacks + artificials).
    The caller is responsible for arranging A so the last len(b) columns form
    the identity basis at start.

    Returns (status, objective, x_full) where x_full has length equal to number
    of columns in A. status is one of LP_OPTIMAL, LP_INFEASIBLE, LP_UNBOUNDED,
    LP_ITERATION_LIMIT. Artificial columns still positive at termination flag
    infeasibility of the caller's LP.
    """
    n_rows = len(b)
    n_cols = len(c)
    if n_rows == 0:
        return LP_OPTIMAL, 0.0, [0.0] * n_cols
    # Identity basis assumed as the trailing n_rows columns.
    basis: List[int] = list(range(n_cols - n_rows, n_cols))
    tableau_A = [row[:] for row in A]
    tableau_b = b[:]
    tableau_c = c[:]

    for _ in range(max_iters):
        # Compute reduced costs r_j = c_j - c_B^T A_j
        c_B = [tableau_c[i] for i in basis]
        # Choose entering column: most negative reduced cost. Bland tie-break
        # on smallest column index prevents cycling on degenerate pivots.
        entering = -1
        entering_rc = -SIMPLEX_EPS
        for j in range(n_cols):
            if j in basis:
                continue
            rc = tableau_c[j]
            for i in range(n_rows):
                rc -= c_B[i] * tableau_A[i][j]
            if rc < entering_rc - SIMPLEX_EPS:
                entering_rc = rc
                entering = j
            elif rc < -SIMPLEX_EPS and (entering == -1 or j < entering) and abs(rc - entering_rc) <= SIMPLEX_EPS:
                entering = j
        if entering == -1:
            break

        # Ratio test on entering column
        leaving_row = -1
        min_ratio = math.inf
        for i in range(n_rows):
            a_ij = tableau_A[i][entering]
            if a_ij > SIMPLEX_EPS:
                ratio = tableau_b[i] / a_ij
                if ratio < min_ratio - SIMPLEX_EPS:
                    min_ratio = ratio
                    leaving_row = i
                elif ratio < min_ratio + SIMPLEX_EPS and leaving_row != -1 and basis[i] < basis[leaving_row]:
                    leaving_row = i
        if leaving_row == -1:
            return LP_UNBOUNDED, -math.inf, [0.0] * n_cols

        # Pivot on tableau_A[leaving_row][entering]
        pivot = tableau_A[leaving_row][entering]
        inv_pivot = 1.0 / pivot
        for j in range(n_cols):
            tableau_A[leaving_row][j] *= inv_pivot
        tableau_b[leaving_row] *= inv_pivot
        for i in range(n_rows):
            if i == leaving_row:
                continue
            factor = tableau_A[i][entering]
            if factor == 0.0:
                continue
            for j in range(n_cols):
                tableau_A[i][j] -= factor * tableau_A[leaving_row][j]
            tableau_b[i] -= factor * tableau_b[leaving_row]
        basis[leaving_row] = entering
    else:
        return LP_ITERATION_LIMIT, math.nan, [0.0] * n_cols

    x_full = [0.0] * n_cols
    for i, col in enumerate(basis):
        x_full[col] = tableau_b[i]

    # Detect infeasibility: any artificial still basic with positive value.
    for col in artificial_cols:
        if col < n_cols and x_full[col] > 1.0e-6:
            return LP_INFEASIBLE, math.inf, x_full

    obj = sum(tableau_c[j] * x_full[j] for j in range(n_cols))
    return LP_OPTIMAL, obj, x_full


# ---------------------------------------------------------------------------
# LP relaxation adapter over instance constraints + per-variable [lb, ub] bounds
# ---------------------------------------------------------------------------


def _solve_lp_relaxation(
    sense: str,
    obj_coeffs: Sequence[float],
    constraints: Sequence[Dict[str, Any]],
    var_lb: Sequence[float],
    var_ub: Sequence[float],
) -> Tuple[str, float, List[float]]:
    """
    Solve the LP relaxation of the 0-1 IP with variable bounds fixed to
    [var_lb[i], var_ub[i]] and sense in {max, min}. Returns (status, obj, x)
    in the ORIGINAL variable space (length n_vars).

    Substitution: let y = x - lb so y >= 0 with y <= ub - lb. Add explicit
    y_i <= (ub - lb) rows. The instance's original constraints become
    A(y + lb) sense b, i.e. Ay sense b - A*lb, then normalized to Ay = b - Alb
    via slack/surplus/artificial columns.
    """
    n_vars = len(obj_coeffs)
    lb = [float(x) for x in var_lb]
    ub = [float(x) for x in var_ub]
    y_ub = [ub[i] - lb[i] for i in range(n_vars)]

    fixed_mask = [abs(y_ub[i]) <= 1.0e-12 for i in range(n_vars)]

    # Build normalized rows: (row_coeffs on y, rhs, sense_char).
    # Sense char in { 'L', 'G', 'E' }.
    rows: List[Tuple[List[float], float, str]] = []
    for con in constraints:
        coeffs = [float(v) for v in con["coefficients"]]
        rhs = float(con["rhs"]) - sum(coeffs[i] * lb[i] for i in range(n_vars))
        sense_str = con["sense"]
        if sense_str == lib.CONSTRAINT_LE:
            sense_char = "L"
        elif sense_str == lib.CONSTRAINT_GE:
            sense_char = "G"
        else:
            sense_char = "E"
        # Normalize rhs >= 0 by row negation (flips sense L <-> G)
        if rhs < 0.0:
            coeffs = [-v for v in coeffs]
            rhs = -rhs
            if sense_char == "L":
                sense_char = "G"
            elif sense_char == "G":
                sense_char = "L"
        rows.append((coeffs, rhs, sense_char))
    for i in range(n_vars):
        if fixed_mask[i]:
            continue
        row = [0.0] * n_vars
        row[i] = 1.0
        rows.append((row, max(0.0, y_ub[i]), "L"))

    n_rows = len(rows)

    # Assemble A columns: original y columns + slack/surplus/artificial columns
    # per row. Trailing n_rows columns will form the identity basis.
    # Column layout: [y_0..y_{n-1}, aux_row_0, aux_row_1, ..., aux_row_{n_rows-1}]
    # For L rows: aux is slack (+1), initial basis (identity column).
    # For G rows: introduce surplus (-1) column BEFORE the identity basis, then
    #             identity column is an artificial with cost BIGM.
    # For E rows: identity column is an artificial with cost BIGM.
    # Compact scheme: extend A with surplus columns first (with 0 in identity
    # region), then add identity columns in order.

    surplus_cols: List[List[float]] = []
    surplus_cost: List[float] = []
    row_needs_artificial: List[bool] = [False] * n_rows
    for r, (_, _, sc) in enumerate(rows):
        if sc == "G":
            col = [0.0] * n_rows
            col[r] = -1.0
            surplus_cols.append(col)
            surplus_cost.append(0.0)
            row_needs_artificial[r] = True
        elif sc == "E":
            row_needs_artificial[r] = True

    tableau_cols: List[List[float]] = []
    for j in range(n_vars):
        col = [rows[r][0][j] for r in range(n_rows)]
        tableau_cols.append(col)
    for col in surplus_cols:
        tableau_cols.append(col)
    # Trailing identity columns: slack for L rows, Big-M artificial for G/E rows.
    artificial_cols: List[int] = []
    identity_cost: List[float] = []
    n_pre_identity = n_vars + len(surplus_cols)
    for r in range(n_rows):
        col = [0.0] * n_rows
        col[r] = 1.0
        tableau_cols.append(col)
        if row_needs_artificial[r]:
            identity_cost.append(BIGM)
            artificial_cols.append(n_pre_identity + r)
        else:
            identity_cost.append(0.0)

    n_cols_total = len(tableau_cols)
    A = [[tableau_cols[j][r] for j in range(n_cols_total)] for r in range(n_rows)]

    sense_multiplier = -1.0 if sense == lib.SENSE_MAXIMIZE else 1.0
    c_y = [sense_multiplier * float(coeff) for coeff in obj_coeffs]
    c_full = list(c_y) + list(surplus_cost) + list(identity_cost)

    b_vec = [rows[r][1] for r in range(n_rows)]

    status, obj_min, x_full = _simplex_min(c_full, A, b_vec, artificial_cols)
    if status == LP_INFEASIBLE:
        return LP_INFEASIBLE, math.inf, [0.0] * n_vars
    if status in (LP_UNBOUNDED, LP_ITERATION_LIMIT):
        return status, math.nan, [0.0] * n_vars

    # Recover x = y + lb in original space
    y_vals = x_full[:n_vars]
    x_orig = [y_vals[i] + lb[i] for i in range(n_vars)]
    # Clamp tiny negative/over-upper drift from floating-point pivots.
    for i in range(n_vars):
        if x_orig[i] < 0.0 and x_orig[i] > -1.0e-8:
            x_orig[i] = 0.0
        if x_orig[i] > 1.0 and x_orig[i] < 1.0 + 1.0e-8:
            x_orig[i] = 1.0
        if x_orig[i] < lb[i]:
            x_orig[i] = lb[i]
        if x_orig[i] > ub[i]:
            x_orig[i] = ub[i]

    # Convert objective back to original sense. Simplex optimized c^T y where
    # y = x - lb, so c^T x = c^T y + c^T lb; add that constant offset here.
    constant_offset = sum(float(obj_coeffs[i]) * lb[i] for i in range(n_vars))
    if sense == lib.SENSE_MAXIMIZE:
        obj_orig = -obj_min + constant_offset
    else:
        obj_orig = obj_min + constant_offset
    return LP_OPTIMAL, obj_orig, x_orig


# ---------------------------------------------------------------------------
# Branch-and-bound over 0-1 variables
# ---------------------------------------------------------------------------


def _is_integer_solution(x: Sequence[float]) -> bool:
    for xi in x:
        if abs(xi - round(xi)) > INT_TOL:
            return False
    return True


def _pick_branch_variable(x: Sequence[float], var_lb: Sequence[float], var_ub: Sequence[float]) -> int:
    best_idx = -1
    best_frac = -1.0
    for i, xi in enumerate(x):
        if var_lb[i] >= var_ub[i] - 1.0e-12:
            continue
        frac = abs(xi - round(xi))
        if frac > FRACTIONAL_TOL and frac > best_frac:
            best_frac = frac
            best_idx = i
    return best_idx


def _emit_best(stderr, ts: float, obj: float) -> None:
    stderr.write(f"BEST ts={ts:.6f} obj={obj:.6f}\n")
    stderr.flush()


def _solve_instance(
    instance: Dict[str, Any],
    timeout_sec: float,
    emit_progression: bool,
    stderr,
) -> Dict[str, Any]:
    """
    Solve one 0-1 IP instance. Returns an output dict matching the schema
    accepted by lib.validate_output_json.
    """
    instance_id = instance["instance_id"]
    sense = instance["objective_sense"]
    obj_coeffs = [float(v) for v in instance["objective_coefficients"]]
    constraints = instance["constraints"]
    n_vars = int(instance["n_vars"])

    start = time.monotonic()

    var_lb = [0.0] * n_vars
    var_ub = [1.0] * n_vars

    root_status, root_lp_obj, root_x = _solve_lp_relaxation(sense, obj_coeffs, constraints, var_lb, var_ub)
    if root_status == LP_INFEASIBLE:
        return {
            "instance_id": instance_id,
            "status": lib.STATUS_INFEASIBLE,
            "variables": None,
            "objective_value": None,
        }
    if root_status != LP_OPTIMAL or math.isnan(root_lp_obj):
        return {
            "instance_id": instance_id,
            "status": lib.STATUS_UNKNOWN,
            "variables": None,
            "objective_value": None,
        }

    incumbent_x: Optional[List[int]] = None
    incumbent_obj: Optional[float] = None
    proven_optimal = False

    if _is_integer_solution(root_x):
        cand = [int(round(v)) for v in root_x]
        violations = lib.feasibility_violations(instance, cand)
        if not violations:
            incumbent_x = cand
            incumbent_obj = lib.compute_objective(instance, cand)
            proven_optimal = True
            if emit_progression:
                _emit_best(stderr, time.monotonic() - start, incumbent_obj)
            return {
                "instance_id": instance_id,
                "status": lib.STATUS_OPTIMAL,
                "variables": incumbent_x,
                "objective_value": float(incumbent_obj),
            }

    # Priority queue keyed by LP bound. For max we want highest bound first
    # (best-first over upper bound of remaining subtree); heap is min-heap so
    # push -bound. For min we want lowest bound first; push +bound directly.
    key_multiplier = -1.0 if sense == lib.SENSE_MAXIMIZE else 1.0
    counter = 0
    heap: List[Tuple[float, int, List[float], List[float], float]] = []
    heapq.heappush(heap, (key_multiplier * root_lp_obj, counter, var_lb[:], var_ub[:], root_lp_obj))
    counter += 1

    nodes_explored = 0
    node_limit = BB_NODE_LIMIT

    while heap:
        elapsed = time.monotonic() - start
        if elapsed > timeout_sec:
            break
        if nodes_explored >= node_limit:
            break
        _, _, cur_lb, cur_ub, cur_bound = heapq.heappop(heap)
        nodes_explored += 1

        # Bound prune
        if incumbent_obj is not None:
            if sense == lib.SENSE_MAXIMIZE and cur_bound <= incumbent_obj + INT_TOL:
                continue
            if sense == lib.SENSE_MINIMIZE and cur_bound >= incumbent_obj - INT_TOL:
                continue

        lp_status, lp_obj, lp_x = _solve_lp_relaxation(sense, obj_coeffs, constraints, cur_lb, cur_ub)
        if lp_status == LP_INFEASIBLE:
            continue
        if lp_status != LP_OPTIMAL:
            continue

        # Re-check bound after subproblem solve
        if incumbent_obj is not None:
            if sense == lib.SENSE_MAXIMIZE and lp_obj <= incumbent_obj + INT_TOL:
                continue
            if sense == lib.SENSE_MINIMIZE and lp_obj >= incumbent_obj - INT_TOL:
                continue

        if _is_integer_solution(lp_x):
            cand = [int(round(v)) for v in lp_x]
            # Clamp to bounds (integer rounding may have hopped over a fixed var)
            valid = True
            for i in range(n_vars):
                if cand[i] < int(round(cur_lb[i])) or cand[i] > int(round(cur_ub[i])):
                    valid = False
                    break
                if cand[i] not in (0, 1):
                    valid = False
                    break
            if not valid:
                continue
            violations = lib.feasibility_violations(instance, cand)
            if violations:
                continue
            cand_obj = lib.compute_objective(instance, cand)
            better = incumbent_obj is None or (
                (sense == lib.SENSE_MAXIMIZE and cand_obj > incumbent_obj + INT_TOL)
                or (sense == lib.SENSE_MINIMIZE and cand_obj < incumbent_obj - INT_TOL)
            )
            if better:
                incumbent_x = cand
                incumbent_obj = float(cand_obj)
                if emit_progression:
                    _emit_best(stderr, time.monotonic() - start, incumbent_obj)
            continue

        branch_var = _pick_branch_variable(lp_x, cur_lb, cur_ub)
        if branch_var == -1:
            continue

        # Down child: x_branch = 0 (ub -> 0)
        down_lb = cur_lb[:]
        down_ub = cur_ub[:]
        down_ub[branch_var] = 0.0
        # Up child: x_branch = 1 (lb -> 1)
        up_lb = cur_lb[:]
        up_ub = cur_ub[:]
        up_lb[branch_var] = 1.0

        # Push children with LP bound of parent as first-pass estimate (parent
        # bound is a valid over/under-estimate of any child bound).
        heapq.heappush(heap, (key_multiplier * lp_obj, counter, down_lb, down_ub, lp_obj))
        counter += 1
        heapq.heappush(heap, (key_multiplier * lp_obj, counter, up_lb, up_ub, lp_obj))
        counter += 1

    if incumbent_x is None:
        return {
            "instance_id": instance_id,
            "status": lib.STATUS_UNKNOWN,
            "variables": None,
            "objective_value": None,
        }
    if not heap and nodes_explored < node_limit and (time.monotonic() - start) <= timeout_sec:
        proven_optimal = True
    status_out = lib.STATUS_OPTIMAL if proven_optimal else lib.STATUS_FEASIBLE
    return {
        "instance_id": instance_id,
        "status": status_out,
        "variables": [int(v) for v in incumbent_x],
        "objective_value": float(incumbent_obj),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="p6zeta reference from-scratch 0-1 IP solver")
    parser.add_argument("instance_path", type=Path, help="Path to instance .ip.json file")
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(lib.PER_INSTANCE_TIMEOUT_SEC),
        help="Per-instance wall-clock budget in seconds",
    )
    parser.add_argument(
        "--no-progression",
        action="store_true",
        help="Suppress BEST ts=... obj=... progression tokens on stderr",
    )
    args = parser.parse_args(argv)

    try:
        instance = lib.load_json_file(args.instance_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"ERROR reading instance: {exc}\n")
        return 2

    ok, errs = lib.validate_instance_json(instance)
    if not ok:
        sys.stderr.write("ERROR invalid instance JSON: " + "; ".join(errs) + "\n")
        return 2

    output = _solve_instance(
        instance=instance,
        timeout_sec=float(args.timeout),
        emit_progression=not args.no_progression,
        stderr=sys.stderr,
    )
    ok_out, errs_out = lib.validate_output_json(output, expected_instance_id=instance["instance_id"])
    if not ok_out:
        sys.stderr.write("ERROR reference produced invalid output: " + "; ".join(errs_out) + "\n")
        return 3

    sys.stdout.write(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
