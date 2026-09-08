"""Public metric library for edgebench.p3gamma_sec_opmargin_expansion_book.

Byte-identical copy lives in:
- work image /home/workspace/p3gamma_lib.py   (agent-visible)
- judge image /home/workspace/scoring/p3gamma_lib.py (judge-side, imported by score.py)

Per PKW-FAMILIES.md F-A M5 opacity contract: the reference SOLVER method (4-sibling
DuPont-orthogonal ensemble weights) is judge-side only in solution/reference_solver.py
and MUST NOT appear on any agent surface. The SCORING method is fully public here:
every lane point constant, K constant, threshold, control column, and formula binding.

Rank convention:
  rank 1 = MOST margin EXPANSION (largest positive sector-relative Delta OpMargin in pp)
  rank N = MOST margin COMPRESSION (largest negative sector-relative Delta OpMargin)
  Realized ranks derived from descending Delta_pp sort, ties broken by cik ascending.

L3 top_K target semantics: K largest ranks = K most-COMPRESSION filers (worst performers).
Symmetric under precision_at_k; matches p2alpha_lib.py convention.

Stdlib-only, no numpy/pandas/scipy. Python 3.11+.
"""
from __future__ import annotations

import csv
import io
import math
from typing import Dict, List, Optional, Sequence, Tuple

N_UNIVERSE = 2799
RANK_MIN = 1
RANK_MAX = 2799

LANE_L1_POINTS = 10
LANE_L2_POINTS = 30
LANE_L3_POINTS = 25
LANE_L4_POINTS = 20
LANE_L5_POINTS = 15
TOTAL_POINTS = LANE_L1_POINTS + LANE_L2_POINTS + LANE_L3_POINTS + LANE_L4_POINTS + LANE_L5_POINTS

L2_RHO_THRESHOLD = 0.5
TOP_K = 100
N_DECILES = 10
L5_CONTROL_COLUMN = "prior_year_opmargin_level_rank"
N_SIBLING_MEASURES = 4

DELIVERABLE_PATH = "/home/workspace/submission/opmargin_change_ranks.csv"
DELIVERABLE_HEADER = ("cik", "opmargin_change_rank")


def parse_submission_csv(text: str) -> Tuple[List[Tuple[str, int]], List[str]]:
    problems: List[str] = []
    rows: List[Tuple[str, int]] = []
    if not text.strip():
        problems.append("empty_file")
        return rows, problems
    try:
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if header is None:
            problems.append("empty_file")
            return rows, problems
        expected = list(DELIVERABLE_HEADER)
        if [h.strip() for h in header] != expected:
            problems.append(f"header_mismatch:got={header!r}:expected={expected!r}")
        for i, row in enumerate(reader, start=2):
            if len(row) != 2:
                problems.append(f"row_{i}_wrong_column_count:{len(row)}")
                continue
            cik_raw, rank_raw = row[0].strip(), row[1].strip()
            try:
                rank_int = int(rank_raw)
            except (TypeError, ValueError):
                problems.append(f"row_{i}_rank_not_int:{rank_raw!r}")
                continue
            rows.append((cik_raw, rank_int))
    except Exception as exc:
        problems.append(f"parse_exception:{type(exc).__name__}")
    return rows, problems


def load_realized_ranks(path: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cik = row["cik"].strip()
            rank = int(row["realized_opmargin_change_rank"])
            out[cik] = rank
    return out


def load_sibling_ranks(path: str) -> Dict[str, Dict[str, Optional[float]]]:
    out: Dict[str, Dict[str, Optional[float]]] = {}
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        cols = [c for c in (reader.fieldnames or []) if c != "cik"]
        for row in reader:
            cik = row["cik"].strip()
            entry: Dict[str, Optional[float]] = {}
            for c in cols:
                raw = row.get(c, "").strip()
                if raw == "":
                    entry[c] = None
                else:
                    try:
                        entry[c] = float(raw)
                    except (TypeError, ValueError):
                        entry[c] = None
            out[cik] = entry
    return out


def load_universe(path: str) -> List[str]:
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        return [row["cik"].strip() for row in reader]


def structural_check(
    rows: Sequence[Tuple[str, int]],
    header_problems: Sequence[str],
    universe: Sequence[str],
) -> Tuple[bool, List[str]]:
    reasons: List[str] = list(header_problems)
    n = len(universe)
    if len(rows) != n:
        reasons.append(f"row_count:got={len(rows)}:expected={n}")
    submitted_ids = [r[0] for r in rows]
    submitted_ranks = [r[1] for r in rows]
    if len(set(submitted_ids)) != len(submitted_ids):
        reasons.append("duplicate_ids")
    uni_set = set(universe)
    sub_set = set(submitted_ids)
    missing = sorted(uni_set - sub_set)
    extra = sorted(sub_set - uni_set)
    if missing:
        reasons.append(f"missing_ids:{len(missing)}")
    if extra:
        reasons.append(f"extra_ids:{len(extra)}")
    bad_range = [r for r in submitted_ranks if r < RANK_MIN or r > n]
    if bad_range:
        reasons.append(f"ranks_out_of_range:{len(bad_range)}")
    if len(set(submitted_ranks)) != n or sorted(submitted_ranks) != list(range(1, n + 1)):
        reasons.append("ranks_not_permutation")
    return (not reasons), reasons


def average_ranks(values: Sequence[float]) -> List[float]:
    n = len(values)
    idx_sorted = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[idx_sorted[j + 1]] == values[idx_sorted[i]]:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            out[idx_sorted[k]] = avg
        i = j + 1
    return out


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    rx = average_ranks(list(x))
    ry = average_ranks(list(y))
    n = len(rx)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if dx == 0.0 or dy == 0.0:
        return 0.0
    return num / (dx * dy)


def top_k_ids(id_rank_pairs: Sequence[Tuple[str, float]], k: int) -> List[str]:
    ordered = sorted(id_rank_pairs, key=lambda x: (-x[1], x[0]))
    return [pid for pid, _ in ordered[:k]]


def precision_at_k(agent_ids: Sequence[str], gold_ids: Sequence[str]) -> float:
    if not gold_ids:
        return 0.0
    return len(set(agent_ids) & set(gold_ids)) / float(len(gold_ids))


def decile_calibration_tightness(
    id_rank_pairs: Sequence[Tuple[str, float]],
    realized_by_id: Dict[str, int],
    n_bins: int = N_DECILES,
) -> float:
    n = len(id_rank_pairs)
    if n < n_bins:
        return 0.0
    ordered = sorted(id_rank_pairs, key=lambda x: (x[1], x[0]))
    bin_size = n // n_bins
    remainder = n - bin_size * n_bins
    universe_mid = (n + 1) / 2.0
    mae_agent = 0.0
    mae_naive = 0.0
    idx = 0
    for b in range(n_bins):
        size = bin_size + (1 if b < remainder else 0)
        lo = idx + 1
        hi = idx + size
        expected_center = (lo + hi) / 2.0
        bin_ids = [ordered[j][0] for j in range(idx, idx + size)]
        realized_vals = [realized_by_id[i] for i in bin_ids if i in realized_by_id]
        if not realized_vals:
            idx += size
            continue
        mean_realized = sum(realized_vals) / len(realized_vals)
        mae_agent += abs(mean_realized - expected_center)
        mae_naive += abs(universe_mid - expected_center)
        idx += size
    if mae_naive == 0.0:
        return 0.0
    tightness = 1.0 - (mae_agent / mae_naive)
    return max(0.0, min(1.0, tightness))


def score_l2_rank_correlation(
    id_rank_pairs: Sequence[Tuple[str, int]],
    realized_by_id: Dict[str, int],
) -> float:
    common = [(a, realized_by_id[i]) for i, a in id_rank_pairs if i in realized_by_id]
    if len(common) < 2:
        return 0.0
    xs = [c[0] for c in common]
    ys = [c[1] for c in common]
    rho = spearman(xs, ys)
    gained = (rho - L2_RHO_THRESHOLD) / (1.0 - L2_RHO_THRESHOLD)
    return LANE_L2_POINTS * max(0.0, gained)


def score_l3_topk_worst(
    id_rank_pairs: Sequence[Tuple[str, int]],
    realized_by_id: Dict[str, int],
    k: int = TOP_K,
) -> float:
    agent = top_k_ids([(i, float(r)) for i, r in id_rank_pairs], k)
    gold = top_k_ids([(i, float(r)) for i, r in realized_by_id.items()], k)
    return LANE_L3_POINTS * precision_at_k(agent, gold)


def score_l4_decile_calibration(
    id_rank_pairs: Sequence[Tuple[str, int]],
    realized_by_id: Dict[str, int],
) -> float:
    pairs = [(i, float(r)) for i, r in id_rank_pairs]
    return LANE_L4_POINTS * decile_calibration_tightness(pairs, realized_by_id)


def _partial_spearman(agent_r: Sequence[float], sib_r: Sequence[float], ctrl_r: Sequence[float]) -> float:
    r_as = spearman(agent_r, sib_r)
    r_ac = spearman(agent_r, ctrl_r)
    r_sc = spearman(sib_r, ctrl_r)
    denom = math.sqrt(max(0.0, 1.0 - r_ac * r_ac) * max(0.0, 1.0 - r_sc * r_sc))
    if denom == 0.0:
        return 0.0
    return (r_as - r_ac * r_sc) / denom


def _score_one_sibling_partial(
    id_rank_pairs: Sequence[Tuple[str, int]],
    sibling_col: str,
    sibling_by_id: Dict[str, Dict[str, Optional[float]]],
) -> float:
    ax: List[float] = []
    sx: List[float] = []
    cx: List[float] = []
    for cik, agent_rank in id_rank_pairs:
        entry = sibling_by_id.get(cik)
        if entry is None:
            continue
        s = entry.get(sibling_col)
        c = entry.get(L5_CONTROL_COLUMN)
        if s is None or c is None:
            continue
        ax.append(float(agent_rank))
        sx.append(float(s))
        cx.append(float(c))
    if len(ax) < 2:
        return 0.0
    return _partial_spearman(ax, sx, cx)


def score_l5_cross_condition_consistency(
    id_rank_pairs: Sequence[Tuple[str, int]],
    sibling_by_id: Dict[str, Dict[str, Optional[float]]],
) -> float:
    if not id_rank_pairs or not sibling_by_id:
        return 0.0
    first_entry = next(iter(sibling_by_id.values()))
    sibling_cols = sorted(k for k in first_entry.keys() if k != L5_CONTROL_COLUMN)
    if not sibling_cols:
        return 0.0
    values: List[float] = []
    for col in sibling_cols:
        r = _score_one_sibling_partial(id_rank_pairs, col, sibling_by_id)
        values.append(max(0.0, r))
    mean_r = sum(values) / len(values)
    return LANE_L5_POINTS * mean_r


def score_all(
    id_rank_pairs: Sequence[Tuple[str, int]],
    realized_by_id: Dict[str, int],
    sibling_by_id: Dict[str, Dict[str, Optional[float]]],
) -> Dict[str, float]:
    l1 = float(LANE_L1_POINTS)
    l2 = score_l2_rank_correlation(id_rank_pairs, realized_by_id)
    l3 = score_l3_topk_worst(id_rank_pairs, realized_by_id)
    l4 = score_l4_decile_calibration(id_rank_pairs, realized_by_id)
    l5 = score_l5_cross_condition_consistency(id_rank_pairs, sibling_by_id)
    return {"L1": l1, "L2": l2, "L3": l3, "L4": l4, "L5": l5, "total": l1 + l2 + l3 + l4 + l5}


def lane_max_dict() -> Dict[str, int]:
    return {
        "L1": LANE_L1_POINTS,
        "L2": LANE_L2_POINTS,
        "L3": LANE_L3_POINTS,
        "L4": LANE_L4_POINTS,
        "L5": LANE_L5_POINTS,
    }


def zero_lanes() -> Dict[str, float]:
    return {"L1": 0.0, "L2": 0.0, "L3": 0.0, "L4": 0.0, "L5": 0.0}
