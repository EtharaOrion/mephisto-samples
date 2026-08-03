# Deliverables Guide — Cross-Sectional SEC Capital-Structure Trajectory Projection Book

## Files you MUST submit

1. `leverage_trajectory.py` — a runnable Python script with two modes:
   - `python3 leverage_trajectory.py --train <input_dir> <state_json>`
   - `python3 leverage_trajectory.py --backtest <input_dir> <state_json> <output_json>`

   Where `<input_dir>` at your working turn holds `train/` and `test/`
   subdirectories containing the XBRL + universe + macro JSONL panels plus
   `test/test_filer_quarters.json` listing the `(cik, period)` pairs to
   predict. The judge does NOT invoke this CLI at grade time — it reads
   the static `trajectory_results.json` you produce.

2. `requirements.txt` — pip dependency list (any of numpy, pandas, scipy
   allowed; no Bloomberg / Yahoo / Kaggle / hmmlearn / direct-BLS).

3. `trajectory_results.json` — the JSON artifact produced by your script
   at your working turn (before submission).

## `trajectory_results.json` schema

```
{
  "task_id": "sec_leverage_trajectory_projection_book",
  "bundle_uuid": "d3cd6658-d997-5f26-89e3-97e5443046b4",
  "per_filer_quarter": [
    {
      "cik":                       <int>,     /* SEC Central Index Key */
      "period":                    "YYYYQq",  /* e.g. "2025Q1" */
      "composite_score":           <float>,   /* capital-structure trajectory composite; null only when the underlying XBRL row is all-null */
      "peer_rank_percentile":      <float>,   /* [0.0, 1.0] percentile within size-and-sector peer group */
      "global_rank_percentile":    <float>,   /* [0.0, 1.0] percentile across the full universe for the quarter */
      "refi_direction":            "risk_up" | "neutral" | "risk_down",
      "refi_confidence":           <float>,   /* [0.0, 1.0] self-reported confidence on the direction call */
      "extreme_probability":       <float>,   /* [0.0, 1.0] probability of falling in top OR bottom decile of realized composite rank */
      "in_top_decile":             <bool>,    /* best deleveragers flag */
      "in_bottom_decile":          <bool>,    /* worst leverage-uppers flag */
      "position_weight":           <float>,   /* signed unit exposure; positive = long, negative = short, zero = flat */
      "price_response_20d_proxy":  <float>    /* your capital-structure-derived estimate of 20-trading-day post-print price response */
    },
    ...
  ],
  "self_reported_metrics": {
    "L1_composite_trajectory_rank_correlation_est": <float>,  /* per-quarter Spearman IC vs your own estimate of truth's post-print response proxy */
    "L2_refinancing_risk_direction_accuracy_est":   <float>,  /* 3-class direction accuracy on your own truth estimate */
    "L3_extreme_mover_detection_f1_est":            <float>,  /* F1 of your extreme flags vs your own truth estimate */
    "L4_delta_liabilities_growth_ranking_ic_est":   <float>,  /* per-quarter Spearman IC on your peer-rank vs your own realized Delta-Liab estimate */
    "L5_interest_coverage_direction_accuracy_est":  <float>   /* 3-class direction accuracy on the InterestExpense-reporting subset */
  }
}
```

## Field semantics

| Field | Units | Notes |
|-------|-------|-------|
| `cik` | int | SEC Central Index Key; matches the CIK column in `test_filer_quarters.json`. |
| `period` | enum | Calendar-quarter string `"YYYYQq"` matching the `period` column. |
| `composite_score` | dim | Aggregated multi-quarter rolling-window slope signal on the leverage ratio + net-debt-to-assets + interest-coverage; rank-transformed cross-sectionally. |
| `peer_rank_percentile` | [0,1] | Size-and-sector-normalized percentile of `composite_score` within the peer group. |
| `global_rank_percentile` | [0,1] | Cross-sectional percentile of `composite_score` across the full universe for the quarter. |
| `refi_direction` | enum | 3-class refinancing-risk direction over the next four quarters given the FRED rate-cycle overlay and the filer's own long-term-debt maturity proxy. |
| `refi_confidence` | [0,1] | Self-reported confidence on the direction call. |
| `extreme_probability` | [0,1] | Probability that this observation falls in the top decile (best deleveragers) OR bottom decile (worst leverage-uppers) of realized composite trajectory rank. |
| `in_top_decile` / `in_bottom_decile` | bool | Binary indicators derived from `extreme_probability`. |
| `position_weight` | dim | Signed unit-notional position; positive = long low-leverage / long deleveraging, negative = short high-leverage / short leveraging-up. |
| `price_response_20d_proxy` | dim | Your capital-structure-derived estimate of the 20-trading-day post-print price response, on the same rank scale as `composite_score`. |

## Constraints

- All floats: standard JSON representation, no `Infinity`/`NaN`.
- Every `(cik, period)` pair in `test_filer_quarters.json` MUST appear as
  a distinct object in `per_filer_quarter`. Missing entries score 0 on
  covered lanes.
- `refi_direction` MUST be one of `risk_up`, `neutral`, `risk_down`.
- `composite_score` MAY be null only when the underlying XBRL row has
  all-null keys (dropped from L1 scoring).
- `peer_rank_percentile`, `global_rank_percentile`, `refi_confidence`,
  and `extreme_probability` MUST be on `[0.0, 1.0]`.
- All numeric predictions must be internally consistent with your
  submitted `self_reported_metrics` (the judge recomputes each metric
  independently; deviation beyond ±0.15 on any of L1-L5 zeros the L7
  anti-fabrication lane).
- Position exposures are soft-capped via a positive-Sharpe-only anchor on
  L6; the judge applies a Sharpe cap of 5.0 against realized moves.

## Judge scoring — output metrics you are graded on

Your submission is scored on eight lanes plus a leverage-cycle bonus,
aggregated across the full CY2025Q1-CY2026Q1 test window:

1. **Composite trajectory rank correlation (20 pts)** — per-quarter
   Spearman IC of `composite_score` vs truth's capital-structure-derived
   post-print price-response proxy, averaged across 5 quarters.
2. **Refinancing-risk direction (15 pts)** — 3-class classification
   accuracy of `refi_direction`.
3. **Extreme-mover detection F1 (15 pts)** — F1 of
   `in_top_decile OR in_bottom_decile` flags.
4. **Delta-liabilities growth ranking (10 pts)** — per-quarter Spearman
   IC of `peer_rank_percentile` vs realized Delta-Liabilities/Assets YoY.
5. **Interest-coverage direction (10 pts, subset)** — 3-class up/flat/down
   direction accuracy on the InterestExpense-reporting subset.
6. **Composite position PnL (10 pts)** — cross-quarter Sharpe of the
   positioning book vs truth's post-print response proxy, capped at 5.0.
7. **Anti-fabrication (5 pts)** — self-reported vs judge-recomputed L1-L5
   agreement within ±0.15.
8. **Cross-quarter stability (10 pts)** — mean per-quarter normalized
   performance across L1-L6, discounted by variance across 5 quarters.

**Leverage-cycle bonus (+10 pts, aggregated).** Precision of detection
for filers whose leverage peaked during the CY2024Q4-CY2025Q2 rate-hike
plateau and deleveraged during the CY2025Q3-CY2026Q1 cutting cycle;
saturates at precision >= 0.85.

## Provided data (agent-visible)

All files in the `attachments/` directory (symlinked to `/home/workspace/`
at container start; both `attachments/train/*` and `train/*` resolve to
the same files).

| File | Description |
|------|-------------|
| `attachments/train/xbrl.jsonl` | CY2018Q1-CY2024Q4 XBRL balance-sheet + flow signals per filer-quarter (~28,000 obs). |
| `attachments/train/universe.jsonl` | Top-1000 filers by Assets per training quarter with entry/exit flags. |
| `attachments/train/macro.jsonl` | Monthly DGS10, DGS2, DFF, T10Y2Y aligned to the quarterly filer grid. |
| `attachments/test/xbrl.jsonl` | CY2025Q1-CY2026Q1 XBRL panel (INPUT-ONLY). |
| `attachments/test/universe.jsonl` | Test-window universe membership. |
| `attachments/test/macro.jsonl` | Test-window macro anchors. |
| `attachments/test/test_filer_quarters.json` | List of `(cik, period)` pairs your submission MUST cover. |
| `attachments/requirements.txt` | Baseline dependencies (numpy, pandas). |
| `attachments/README.md` | Bundle overview + schema + rules. |

Composite scores, peer ranks, direction labels, extreme-mover truth flags,
and realized post-print price responses are held out on the judge side.
