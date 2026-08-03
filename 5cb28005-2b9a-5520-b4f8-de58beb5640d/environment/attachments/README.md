# sec_fundamental_momentum_calibration — agent instructions

You are building a cross-sectional equity fundamental momentum system on US
SEC EDGAR filer data. Your task: for each filer-quarter in the CY2025Q1-CY2026Q1
test window (~5,000 observations from a top-1000-by-Assets US filer universe),
produce four outputs:

1. **Composite fundamental momentum score** per filer per quarter, ranked
   cross-sectionally with peer-group normalization.
2. **Earnings-surprise direction classification** per filer per quarter
   (`beat` / `in_line` / `miss`) with self-reported confidence.
3. **Extreme-filer probability** — probability that this filer-quarter lies
   in the top decile (blowout) or bottom decile (miss disaster) of composite
   rank.
4. **Positioning book** per quarter — long / short exposures with volatility
   scaling + turnover discipline.

## Bundle layout

```
5cb28005-2b9a-5520-b4f8-de58beb5640d/
    README.md                          (this file)
    train/
        fundamentals.jsonl             per-filer-quarter CY2018Q1-CY2024Q4 XBRL data (~28000 obs)
        universe.jsonl                 top-1000 filers by Assets per quarter with entry/exit flags
        macro.jsonl                    monthly DGS10, DFF, UNRATE (FRED via redistribution route)
    test/
        fundamentals.jsonl             per-filer-quarter CY2025Q1-CY2026Q1 XBRL data (~5000 obs; INPUT ONLY)
        universe.jsonl                 test-window universe membership
        macro.jsonl                    test-window macro anchors
        test_filer_quarters.json       list of (cik, period) tuples to predict
```

## Data schema (fundamentals.jsonl)

Each line is a JSON object with these keys:

- `period` — `"YYYYQq"` (e.g. `"2025Q1"`)
- `cik` — SEC Central Index Key (integer)
- `entity_name` — filer name (may be null)
- `Revenues` — flow USD, may be null if not reported (fallback aliases already resolved)
- `GrossProfit`, `OperatingIncomeLoss`, `NetIncomeLoss` — flow USD
- `EarningsPerShareDiluted` — flow USD-per-shares
- `Assets`, `StockholdersEquity`, `LongTermDebt` — stock USD (as-of quarter-end)

Missing values are `null` (not zero, not omitted key).

## Data provenance

- **SEC EDGAR XBRL frames** — https://data.sec.gov/api/xbrl/frames/us-gaap/
  Fetched at bundle build time with `User-Agent: FORGE tanmaytushar21@gmail.com`
  per SEC EDGAR fair-access policy. Frames are US Government public disclosure
  per 17 CFR § 232.301.
- **FRED (Federal Reserve Economic Data)** — DGS10 (10-year Treasury),
  DFF (effective Fed Funds), UNRATE (unemployment via redistribution route,
  not direct BLS API). All US Government public domain.

## Deliverables

- `fundamental_momentum.py` — your solver
- `requirements.txt` — pinned dependencies (any of numpy, pandas, scipy allowed;
  no Bloomberg / Yahoo / Kaggle / hmmlearn / direct-BLS)
- `momentum_results.json` — output artifact keyed by (cik, period) with:
    - `composite_score` (float)
    - `peer_rank_percentile` (0.0-1.0)
    - `surprise_direction` (one of `beat` / `in_line` / `miss`)
    - `surprise_confidence` (0.0-1.0)
    - `extreme_probability` (0.0-1.0)
    - `position_weight` (signed; positive = long, negative = short)
    - `self_reported_metrics` block matching lane names L1-L8

## Scoring lanes (0-110 total)

- L1 composite score rank correlation (20 pts, Spearman IC per quarter, avg)
- L2 earnings surprise direction (15 pts, 3-class accuracy)
- L3 extreme filer detection F1 (15 pts)
- L4 revenue growth ranking (10 pts, Spearman IC on Rev YoY)
- L5 margin expansion direction (10 pts, up/flat/down accuracy)
- L6 composite position PnL (10 pts, positive-Sharpe-only anchor, cap 1.5)
- L7 anti-fabrication (5 pts, self-report vs judge-recompute tolerance)
- L8 cross-quarter stability (10 pts, variance-and-mean across 5 test quarters)
- earnings_cycle_bonus (10 pts, CY2025 margin-compression-to-recovery precision)

## Rules

- **No network access.** All data you need is in `train/` and `test/`.
- **No hindsight on test targets.** The `test/fundamentals.jsonl` contains
  raw fundamentals only; composite scores, ranks, surprises, and price
  response are held out.
- **Persistence-disease caution.** Raw EPS CY2025Q1->CY2026Q1 persistence
  MAE 0.924 vs SD 2.571 (SD/MAE 2.78) — copy-last-quarter is a real
  temptation. Scoring is rank-based / direction-based / PnL-based, not
  level-based, so copy-last-quarter is a genuine trivial baseline you must
  beat, not a shortcut.
- **Peer-group normalization required.** Filer rankings without peer-relative
  normalization score low on L1 because size-persistence dominates raw
  fundamental levels.

## Reproduction

The bundle was generated deterministically from `seed/grounding.yaml` and
`seed/recompute.py` in the Mephisto repository. Two independent recompute
runs produce byte-identical bundle contents (verified by SHA-256 comparison).
