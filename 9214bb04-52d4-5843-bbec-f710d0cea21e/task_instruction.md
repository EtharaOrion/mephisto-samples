# Task: SEC Operating Margin Expansion Book

## Role

You are a corporate-financial-margin analyst. Rank 2799 SEC filers by their expected realized sector-relative change in operating margin from CY2025Q1 to CY2026Q1. The graded target is the sign and magnitude of the sector-adjusted YoY Delta of `us-gaap:OperatingIncomeLoss / us-gaap:Revenues` (in percentage points), computed on a consolidated (no-dimension) basis with ASC 606 revenue tag union, sector-residualized at SIC-2.

## Universe (2799 CIKs)

Enumerated in `/home/workspace/data/universe_p3gamma_2026.csv`. Every submitted row must map to a CIK in this file; every CIK must appear exactly once in your submission.

CIK format: 10-digit zero-padded string (e.g. `0000320193` for Apple).

## Rank convention

- Rank **1** = MOST margin EXPANSION (largest POSITIVE sector-relative Delta operating margin in pp, biggest positive percentage-point change vs CY2025Q1 baseline).
- Rank **2799** = MOST margin COMPRESSION (largest NEGATIVE sector-relative Delta).
- Ranks are a permutation of [1, 2799]; every integer used exactly once.
- Ties in your raw signal must be broken by cik ascending.

## Deliverable

Write your submission to:

  `/home/workspace/submission/opmargin_change_ranks.csv`

With EXACTLY these 2 columns:

  `cik,opmargin_change_rank`

2799 data rows + 1 header row. CIK zero-padded 10-digit string; rank an integer in [1, 2799].

## Provided inputs (under `/home/workspace/data/`)

- `universe_p3gamma_2026.csv` (2799 rows + header) — the graded universe. Single column `cik`.
- `sec_xbrl_panel_stripped.csv` (2799 rows + header) — SEC EDGAR XBRL panel with these columns:
  - `cik` (10-digit zero-padded)
  - `sic2` (Standard Industrial Classification 2-digit sector code)
  - `op_income_loss_cy2025q1` (USD, us-gaap:OperatingIncomeLoss, prior year Q1 baseline)
  - `revenues_cy2025q1`, `revenues_cy2026q1` (USD, us-gaap:Revenues with ASC 606 tag union when base tag missing)
  - `opmargin_cy2025q1_level` (dimensionless ratio, op_income_loss_cy2025q1 / revenues_cy2025q1)
  - `prior_year_opmargin_level_rank` (float, sector-residualized rank of CY2025Q1 operating margin level)
  - `gross_profit_cy2025q1`, `gross_profit_cy2026q1` (USD, us-gaap:GrossProfit, may be blank when filer omits tag)
  - `ocf_cy2025q1`, `ocf_cy2026q1` (USD, us-gaap:NetCashProvidedByUsedInOperatingActivities, may be blank)
  - `assets_cy2024q4i`, `assets_cy2025q1i`, `assets_cy2025q4i`, `assets_cy2026q1i` (USD, us-gaap:Assets, instant balances for TTM asset averaging, may be blank)
  - NOTE: `op_income_loss_cy2026q1` (the graded numerator) is intentionally REMOVED from this panel. You must predict; you do not have the realized value.
- `sec_sector_taxonomy.csv` (2799 rows + header) — columns `cik`, `sic`, `sic2` for sector context.
- `regulatory_text_bundle.tar.gz` — URL index stub referencing ASC 606, XBRL US DQC_0150 segment-axis guidance, and SEC Rule 12b-25 filing deadlines. Not required for the task.

## Public library

`/home/workspace/p3gamma_lib.py` names every scoring constant (lane point values, K constants, thresholds) and every scoring function that will be applied by the judge. Study it. Nothing about the scorer is hidden.

## Scoring (0-100 total)

- **L1 structural (10 pts)**: cascade to 0 on any structural failure (wrong row count, missing/extra cik, duplicate cik, duplicate rank, rank out of [1, 2799], header mismatch).
- **L2 spearman_rank_threshold (30 pts)**: `30 * max(0, (rho - 0.5) / (1 - 0.5))` where rho is Spearman correlation between your predicted ranks and the realized sector-relative Delta ranks. Zero if rho <= 0.5.
- **L3 top_k_worst (25 pts)**: `25 * |your_top_100 intersect realized_top_100| / 100`, where top_100 = 100 filers with LARGEST ranks (most-compression cohort).
- **L4 decile_calibration_tightness (20 pts)**: `20 * max(0, 1 - sum|bin_mean_realized - bin_expected_center| / MAE_naive)` over 10 equal-count bins ordered by your rank.
- **L5 cross_sibling_consistency (15 pts, bonus)**: `15 * mean(max(0, partial_spearman(your_ranks, sibling_i | prior_year_opmargin_level_rank)))` across 4 sibling measures held by the judge.

## Notes on approaches

- Predicting the persistence of `prior_year_opmargin_level_rank` (i.e. ranking by the visible boundary column) alone yields Spearman rho well below the L2 threshold of 0.5 and earns near-zero on L5 by partial-correlation construction. Screen wave 2026-07-18 measured rho +0.248 for this shortcut; measured control-ladder total on 2026-08-08 was 14.012 out of 100 - lands below the Stage-2b HARD KILL floor of 24.
- A uniformly-random permutation earns ~10 out of 100 (L1 only).
- An honest analyst method using the 8 raw sibling columns (Gross Profit, OCF, Assets 4-quarter, Revenues) to compute sector-residualized change signals lands in the 20-45 range depending on weight choice.
- Full 100 is unreachable by design; L5 cross-sibling partial correlation is empirically bounded by literature (~2-4 out of 15 even at hindsight perfection).

## Submission

You may submit up to 400 times. A 120-second cooldown applies between submissions. The verifier emits, per submission, 5 aggregate lane scalars (L1-L5) + structural feedback + your submitted rank vector's distributional shape (min, max, mean, stddev). No per-cik feedback of any kind.

## Network isolation

Your environment has NO network access. All data required for the task is present under `/home/workspace/data/`.
