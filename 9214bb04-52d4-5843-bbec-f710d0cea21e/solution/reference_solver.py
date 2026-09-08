"""Reference solver for edgebench.p3gamma_sec_opmargin_expansion_book.

Judge-side only. Ships in solution/reference_solver.py for auditability.
Method NEVER appears on any agent-visible surface per PKW-FAMILIES.md F-A M5.

Method: 4-sibling DuPont-orthogonal composite. Each sibling is a candidate
predictor of Delta OpMargin_YoY per Nissim-Penman 2001 + Nissim 2023 +
Amir/Kama/Livnat 2011 + Chen/Cho/Dou/Lev 2022:

  Delta_GM_pp    = (GP_2026Q1 / Rev_2026Q1 - GP_2025Q1 / Rev_2025Q1) * 100
  Delta_ATO      = Rev_2026Q1 / avg(A_2025Q4I, A_2026Q1I)
                   - Rev_2025Q1 / avg(A_2024Q4I, A_2025Q1I)
  Delta_OCFM_pp  = (OCF_2026Q1 / Rev_2026Q1 - OCF_2025Q1 / Rev_2025Q1) * 100
  RevGrowth_log  = log(Rev_2026Q1 / Rev_2025Q1)   ; Rev > 0 both quarters

Each sibling raw value sector-residualized at SIC-2 (mean-subtracted).
Each sibling ranked DESCENDING (rank 1 = biggest positive sibling delta).
Weighted composite = 0.45 * gm_rank + 0.10 * ato_rank + 0.25 * ocfm_rank
+ 0.20 * revgrowth_rank. Missing sibling falls back to neutral midpoint
(N+1)/2.0. Final rank ASCENDING on composite (rank 1 = smallest composite
= expected biggest Delta OpMargin expansion).

Rationale for weights:
- W_GM = 0.45: Delta GM is the mechanically dominant driver of Delta OPM
  because OPM = GM - SGA/Rev - R&D/Rev - other operating cost ratios, and
  GM is by far the largest component.
- W_OCFM = 0.25: accrual/cash quality (Sloan 1996) often precedes margin
  shifts.
- W_REV = 0.20: operating leverage - revenue growth dilutes fixed costs
  and expands margins.
- W_ATO = 0.10: DuPont-orthogonal to OPM (Amir-Kama-Livnat 2011); helps
  as a diversifier but is the weakest direct predictor of Delta OPM.

Weights sum to 1.0.

All inputs derivable from the agent-visible sec_xbrl_panel_stripped.csv
which SHIPS: gross_profit_cy2025q1, gross_profit_cy2026q1, ocf_cy2025q1,
ocf_cy2026q1, assets_cy2024q4i, assets_cy2025q1i, assets_cy2025q4i,
assets_cy2026q1i, revenues_cy2025q1, revenues_cy2026q1, and sic2.
Panel does NOT ship op_income_loss_cy2026q1 (the graded numerator),
preserving realized-outcome opacity.

Stdlib-only, no numpy/pandas.
"""
from __future__ import annotations

import csv
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

UNIVERSE_FILENAME = "universe_p3gamma_2026.csv"
PANEL_FILENAME = "sec_xbrl_panel_stripped.csv"
SECTOR_FILENAME = "sec_sector_taxonomy.csv"

W_GM = 0.45
W_ATO = 0.10
W_OCFM = 0.25
W_REV = 0.20


def load_universe(path: str) -> List[str]:
    with open(path, "r", newline="") as f:
        return [row["cik"].strip() for row in csv.DictReader(f)]


def load_panel(path: str) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with open(path, "r", newline="") as f:
        for row in csv.DictReader(f):
            out[row["cik"].strip()] = row
    return out


def _parse_float(s: str) -> Optional[float]:
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _sector_mean(values: Dict[str, float], sic2_by_cik: Dict[str, str]) -> Dict[str, float]:
    per_sector: Dict[str, List[float]] = {}
    for cik, v in values.items():
        s = sic2_by_cik.get(cik)
        if s is None:
            continue
        per_sector.setdefault(s, []).append(v)
    return {s: sum(vs) / len(vs) for s, vs in per_sector.items() if vs}


def _ranks_descending(scored: Dict[str, float]) -> Dict[str, float]:
    items = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
    return {cik: float(idx + 1) for idx, (cik, _) in enumerate(items)}


def _compute_sibling(
    universe: List[str],
    panel: Dict[str, Dict[str, str]],
    sic2_by_cik: Dict[str, str],
    key_fn,
) -> Dict[str, float]:
    raw: Dict[str, float] = {}
    for cik in universe:
        row = panel.get(cik)
        if row is None:
            continue
        v = key_fn(row)
        if v is not None:
            raw[cik] = v
    means = _sector_mean(raw, sic2_by_cik)
    return {
        cik: v - means[sic2_by_cik[cik]]
        for cik, v in raw.items()
        if sic2_by_cik.get(cik) in means
    }


def _delta_gm(row: Dict[str, str]) -> Optional[float]:
    gp_25 = _parse_float(row.get("gross_profit_cy2025q1", ""))
    gp_26 = _parse_float(row.get("gross_profit_cy2026q1", ""))
    r_25 = _parse_float(row.get("revenues_cy2025q1", ""))
    r_26 = _parse_float(row.get("revenues_cy2026q1", ""))
    if None in (gp_25, gp_26, r_25, r_26) or r_25 <= 0 or r_26 <= 0:
        return None
    return (gp_26 / r_26 - gp_25 / r_25) * 100.0


def _delta_ato(row: Dict[str, str]) -> Optional[float]:
    r_25 = _parse_float(row.get("revenues_cy2025q1", ""))
    r_26 = _parse_float(row.get("revenues_cy2026q1", ""))
    a_24q4 = _parse_float(row.get("assets_cy2024q4i", ""))
    a_25q1 = _parse_float(row.get("assets_cy2025q1i", ""))
    a_25q4 = _parse_float(row.get("assets_cy2025q4i", ""))
    a_26q1 = _parse_float(row.get("assets_cy2026q1i", ""))
    if None in (r_25, r_26, a_24q4, a_25q1, a_25q4, a_26q1):
        return None
    avg_25 = 0.5 * (a_24q4 + a_25q1)
    avg_26 = 0.5 * (a_25q4 + a_26q1)
    if avg_25 <= 0 or avg_26 <= 0:
        return None
    return r_26 / avg_26 - r_25 / avg_25


def _delta_ocfm(row: Dict[str, str]) -> Optional[float]:
    ocf_25 = _parse_float(row.get("ocf_cy2025q1", ""))
    ocf_26 = _parse_float(row.get("ocf_cy2026q1", ""))
    r_25 = _parse_float(row.get("revenues_cy2025q1", ""))
    r_26 = _parse_float(row.get("revenues_cy2026q1", ""))
    if None in (ocf_25, ocf_26, r_25, r_26) or r_25 <= 0 or r_26 <= 0:
        return None
    return (ocf_26 / r_26 - ocf_25 / r_25) * 100.0


def _revgrowth(row: Dict[str, str]) -> Optional[float]:
    r_25 = _parse_float(row.get("revenues_cy2025q1", ""))
    r_26 = _parse_float(row.get("revenues_cy2026q1", ""))
    if r_25 is None or r_26 is None or r_25 <= 0 or r_26 <= 0:
        return None
    return math.log(r_26 / r_25)


def solve(data_dir: str) -> List[Tuple[str, int]]:
    universe = load_universe(os.path.join(data_dir, UNIVERSE_FILENAME))
    panel = load_panel(os.path.join(data_dir, PANEL_FILENAME))
    sector_rows = load_panel(os.path.join(data_dir, SECTOR_FILENAME))
    sic2_by_cik: Dict[str, str] = {c: r["sic2"].strip() for c, r in sector_rows.items()}

    gm_resid = _compute_sibling(universe, panel, sic2_by_cik, _delta_gm)
    ato_resid = _compute_sibling(universe, panel, sic2_by_cik, _delta_ato)
    ocfm_resid = _compute_sibling(universe, panel, sic2_by_cik, _delta_ocfm)
    rev_resid = _compute_sibling(universe, panel, sic2_by_cik, _revgrowth)

    gm_rank = _ranks_descending(gm_resid)
    ato_rank = _ranks_descending(ato_resid)
    ocfm_rank = _ranks_descending(ocfm_resid)
    rev_rank = _ranks_descending(rev_resid)

    n = len(universe)
    neutral = (n + 1) / 2.0

    composite: Dict[str, float] = {}
    for cik in universe:
        composite[cik] = (
            W_GM * gm_rank.get(cik, neutral)
            + W_ATO * ato_rank.get(cik, neutral)
            + W_OCFM * ocfm_rank.get(cik, neutral)
            + W_REV * rev_rank.get(cik, neutral)
        )

    ordered = sorted(universe, key=lambda c: (composite.get(c, neutral), c))
    return [(cik, idx + 1) for idx, cik in enumerate(ordered)]


def main(argv: List[str]) -> int:
    data_dir = argv[1] if len(argv) > 1 else "/home/workspace/data"
    out_path = argv[2] if len(argv) > 2 else "/home/workspace/submission/opmargin_change_ranks.csv"
    pairs = solve(data_dir)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cik", "opmargin_change_rank"])
        for cik, rank in pairs:
            w.writerow([cik, rank])
    print(f"wrote {len(pairs)} rows to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
