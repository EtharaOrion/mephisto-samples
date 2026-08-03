# sec_leverage_trajectory_projection_book - agent instructions

You are building a cross-sectional equity capital-structure trajectory
projection system on US SEC EDGAR filer data. Your task: for each filer-quarter
in the CY2025Q1-CY2026Q1 test window (~5,000 observations from a top-1000-by-
Assets US filer universe), produce four outputs:

1. **Composite capital-structure trajectory score** per filer per quarter,
   ranked cross-sectionally with peer-group normalization.
2. **Refinancing-risk direction classification** per filer per quarter
   (`risk_up` / `neutral` / `risk_down`) given prevailing rate cycle with
   self-reported confidence.
3. **Extreme-mover probability** - probability that this filer-quarter lies
   in the top decile (best deleveragers) or bottom decile (worst leverage-uppers)
   of composite trajectory rank.
4. **Positioning book** per quarter - long / short exposures on top / bottom
   decile with rate-cycle overlay + turnover discipline.

## Bundle layout

```
d3cd6658-d997-5f26-89e3-97e5443046b4/
    README.md                          (this file)
    train/
        xbrl.jsonl                     per-filer-quarter CY2018Q1-CY2024Q4 XBRL data (~28000 obs)
        universe.jsonl                 top-1000 filers by Assets per quarter with entry/exit flags
        macro.jsonl                    monthly DGS10, DGS2, DFF, T10Y2Y (FRED via redistribution route)
    test/
        xbrl.jsonl                     per-filer-quarter CY2025Q1-CY2026Q1 XBRL data (~5000 obs; INPUT ONLY)
        universe.jsonl                 test-window universe membership
        macro.jsonl                    test-window macro anchors
        test_filer_quarters.json       list of (cik, period) tuples to predict
```

## Data schema (xbrl.jsonl)

Each line is a JSON object with these keys:

- `period` - `"YYYYQq"` (e.g. `"2025Q1"`)
- `cik` - SEC Central Index Key (integer)
- `entity_name` - filer name (may be null)
- `Assets`, `Liabilities`, `StockholdersEquity` - balance-sheet stock USD (quarter-end)
- `LongTermDebt` - stock USD (fallback aliases already resolved:
  LongTermDebtNoncurrent / LongTermDebtAndCapitalLeaseObligations)
- `ShortTermBorrowings`, `CashAndCashEquivalentsAtCarryingValue` - stock USD
- `InterestExpense` - flow USD per-quarter (SUBSET, ~21% of universe reports)
- `OperatingIncomeLoss`, `NetIncomeLoss` - flow USD per-quarter

Missing values are `null` (not zero, not omitted key).

## Data provenance

- **SEC EDGAR XBRL frames** - https://data.sec.gov/api/xbrl/frames/us-gaap/
  Fetched at bundle build time with `User-Agent: FORGE tanmaytushar21@gmail.com`
  per SEC EDGAR fair-access policy. Frames are US Government public disclosure
  per 17 CFR §232.301.
- **FRED (Federal Reserve Economic Data)** - DGS10, DGS2, DFF, T10Y2Y.
  All US Government public domain via FRED redistribution.

## Deliverables

- `leverage_trajectory.py` - your solver
- `requirements.txt` - pinned dependencies (numpy, pandas, scipy allowed;
  no Bloomberg / Yahoo / Kaggle / hmmlearn / direct-BLS)
- `trajectory_results.json` - output artifact keyed by (cik, period) with:
    - `composite_score` (float or null)
    - `peer_rank_percentile` (0.0-1.0)
    - `global_rank_percentile` (0.0-1.0)
    - `refi_direction` (one of `risk_up` / `neutral` / `risk_down`)
    - `refi_confidence` (0.0-1.0)
    - `extreme_probability` (0.0-1.0)
    - `in_top_decile` (bool)
    - `in_bottom_decile` (bool)
    - `position_weight` (signed; positive = long, negative = short)
    - `self_reported_metrics` block matching lane names L1-L8

## Scoring lanes (0-110 total)

- L1 composite trajectory rank correlation (20 pts, Spearman IC per quarter, avg)
- L2 refinancing risk direction (15 pts, 3-class accuracy)
- L3 extreme mover detection F1 (15 pts)
- L4 delta liabilities growth ranking (10 pts, Spearman IC on delta-Liab/Assets YoY)
- L5 interest coverage direction (10 pts, up/flat/down accuracy on subset)
- L6 composite position PnL (10 pts, positive-Sharpe-only anchor, cap 5.0)
- L7 anti-fabrication (5 pts, self-report vs judge-recompute tolerance)
- L8 cross-quarter stability (10 pts, variance-and-mean across 5 test quarters)
- leverage_cycle_bonus (10 pts, CY2025 rate-hike-to-cutting-cycle turning-point precision)

## Rules

- **No network access.** All data you need is in `train/` and `test/`.
- **No hindsight on test targets.** The `test/xbrl.jsonl` contains raw balance-
  sheet / flow fundamentals only; composite scores, ranks, refi directions,
  and price response are held out.
- **Persistence-disease caution - HIGHER SEVERITY than earnings tasks.**
  Capital structure changes require board approval, refinancing windows, and
  covenant navigation - persistence rho on raw Liabilities/Assets levels is
  typically +0.95 or higher. Copy-last-quarter is a real temptation. Scoring
  is TRAJECTORY-SLOPE / rank-based / direction-based / PnL-based, not level-
  based, so copy-last-quarter is a genuine trivial baseline you must beat.
- **Peer-group normalization required.** Filer rankings without peer-relative
  normalization score low on L1 because industry-structure persistence
  dominates raw leverage levels (utilities always high, tech always low).
- **Trajectory-slope estimation required.** Filer rankings on leverage LEVELS
  score low because levels are highly persistent. Rolling-window slopes
  capture genuine capital-structure momentum.
- **Subset scoring on L5.** InterestExpense is reported by only ~21% of the
  universe. L5 lane scores only on the scoreable subset.

## Reproduction

The bundle was generated deterministically from `seed/grounding.yaml` and
`seed/recompute.py` in the Mephisto repository. Two independent recompute
runs produce byte-identical bundle contents (verified by SHA-256 comparison).
