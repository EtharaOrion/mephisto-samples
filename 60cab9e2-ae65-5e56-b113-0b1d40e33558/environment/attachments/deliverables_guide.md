# Deliverables Guide — Fed Funds Regime + Positioning Book

## Files you MUST submit

1. `fed_funds_positioning.py` — a runnable Python script with two modes:
   - `python3 fed_funds_positioning.py --train <input_dir> <state_json>`
   - `python3 fed_funds_positioning.py --backtest <input_dir> <state_json> <output_json>`

   Where `<input_dir>` contains: `fed_funds_*.csv`, `rates_*.csv`, `macro_*.csv`,
   `fomc_meetings_*.csv`, plus `test_windows.json` and `test_fomc_events.json`
   at judge time.

2. `requirements.txt` — pip dependency list (numpy, pandas, scipy).

3. `positioning_results.json` — the JSON produced by your script when invoked
   in `--backtest` mode over the judge-injected 2025Q1-2026H1 window.

## `positioning_results.json` schema

```
{
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "weekly_window_count": <int>,
  "weekly_windows": [
    {
      "window_date":                       "YYYY-MM-DD",    /* Friday close */
      "predicted_regime":                  "hiking" | "on_hold_hawkish" | "on_hold_neutral" | "on_hold_dovish" | "cutting",
      "predicted_2y_bps_next_wk":          <float>,          /* forecast of 2Y yield one week ahead, in bps */
      "predicted_10y_bps_next_wk":         <float>,          /* forecast of 10Y yield one week ahead, in bps */
      "positioning_book": {
        "duration_2y":    <float>,   /* signed 2Y duration exposure, unit-notional */
        "duration_10y":   <float>,   /* signed 10Y duration exposure, unit-notional */
        "slope_2s10s":    <float>,   /* signed 2s10s steepener (+) / flattener (-) exposure */
        "carry_front_end": <float>   /* signed front-end carry position (+) long-front-end carry / (-) short */
      }
    },
    ...
  ],
  "fomc_event_count": <int>,
  "fomc_events": [
    {
      "meeting_date":       "YYYY-MM-DD",
      "predicted_decision": "hold" | "cut_25" | "cut_50" | "cut_75" | "cut_100" | "hike_25" | "hike_50" | "hike_75" | "hike_100"
    },
    ...
  ],
  "self_reported_metrics": {
    "regime_accuracy":        <float>,   /* fraction correct weekly regime classifications 0-1 */
    "yield_2y_mae_bps":       <float>,   /* MAE (bps) on 2Y yield forecast */
    "yield_10y_mae_bps":      <float>,   /* MAE (bps) on 10Y yield forecast */
    "duration_pnl_sum":       <float>,   /* sum PnL from duration_2y + duration_10y positions across windows */
    "slope_pnl_sum":          <float>,   /* sum PnL from slope_2s10s positions */
    "carry_pnl_sum":          <float>,   /* sum PnL from carry_front_end positions */
    "fomc_hit_count":         <int>      /* count of FOMC decisions correctly classified */
  }
}
```

## Field semantics

| Field | Units | Notes |
|-------|-------|-------|
| `window_date` | date | Friday close date, matches judge-provided `test_windows.json` entries. |
| `predicted_regime` | enum | One of 5 Fed policy regime labels; classifier over observable rate + macro signals. |
| `predicted_2y_bps_next_wk` | bps | Predicted 2Y Treasury constant-maturity yield ONE WEEK ahead (next Friday's DGS2 × 100). |
| `predicted_10y_bps_next_wk` | bps | Predicted 10Y yield ONE WEEK ahead (next Friday's DGS10 × 100). |
| `positioning_book.duration_2y` | dim | Signed 2Y duration; +1 = long 2Y (bet on lower 2Y yield). |
| `positioning_book.duration_10y` | dim | Signed 10Y duration; +1 = long 10Y (bet on lower 10Y yield). |
| `positioning_book.slope_2s10s` | dim | Signed 2s10s spread position; +1 = steepener (bet on wider 10Y-2Y spread). |
| `positioning_book.carry_front_end` | dim | Signed front-end carry position; +1 = long front-end carry. |
| `predicted_decision` | enum | Predicted FOMC rate decision at each of ~12 meetings in the test window. |

## Constraints

- All floats: standard JSON representation, no `Infinity`/`NaN`.
- Every entry in `weekly_windows` MUST correspond to a `window_date` in the
  judge's `test_windows.json`. Missing entries score 0 on covered lanes.
- Every entry in `fomc_events` MUST correspond to a `meeting_date` in the
  judge's `test_fomc_events.json`.
- `predicted_regime` MUST be one of the 5 allowed labels.
- `predicted_decision` MUST be one of the allowed decision strings.
- All numeric predictions must be internally consistent with your submitted
  `self_reported_metrics` (the judge recomputes each metric independently
  and vetoes on divergence beyond tolerance).
- Positioning exposures are soft-capped in aggregate risk terms; the judge
  applies a Sharpe cap of 2.0 per positioning lane against realized moves.

## Judge scoring — output metrics you are graded on

Your submission is scored on eight lanes plus a FOMC-decision bonus,
aggregated across the full 2025Q1-2026H1 test window:

1. **Regime classification (20 pts)** — weekly regime accuracy vs realized regime.
2. **2Y yield forecast (15 pts)** — MAE (bps) on 2Y yield one-week-ahead forecast.
3. **10Y yield forecast (15 pts)** — MAE (bps) on 10Y yield one-week-ahead forecast.
4. **Duration positioning PnL (15 pts)** — Sharpe of weekly 2Y+10Y PnL from realized moves.
5. **Slope positioning PnL (10 pts)** — Sharpe of weekly 2s10s PnL.
6. **Carry position PnL (10 pts)** — cumulative carry-adjusted PnL over test window.
7. **Anti-fabrication (5 pts)** — self-reported metrics vs judge-recompute agreement.
8. **Cross-cadence stability (10 pts)** — variance-of-lane-scores across 6-month buckets.

**FOMC decision bonus (+10 pts, aggregated).** Precision of FOMC rate-decision
prediction across the ~12 meetings in the test window; saturates at 3+ correct.

## Provided data (agent-visible)

All files in the `attachments/` directory.

| File | Description |
|------|-------------|
| `attachments/fed_funds_train.csv` | Daily DFF + monthly FEDFUNDS + daily DFEDTARU/DFEDTARL, 2010-01-01 through 2024-12-31. |
| `attachments/rates_train.csv` | Daily DGS2/DGS10/T10Y2Y Treasury yields + slope, 2010-01-01 through 2024-12-31. |
| `attachments/macro_train.csv` | Monthly UNRATE + CPIAUCSL, 2010-01-01 through 2024-12-31. |
| `attachments/fomc_meetings_2010_2026.csv` | Full FOMC meeting calendar 2010-2026 (agent-visible metadata, ~137 events). |
| `attachments/train_period.txt` | Training window (2010-01-01,2024-12-31). |
| `attachments/valid_period.txt` | Validation window (2024-01-01,2024-12-31). |
| `attachments/requirements.txt` | Python dependencies (numpy, pandas, scipy). |

Pre-2010 data (ZLB-era) is intentionally excluded from training; post-2015 target-range regime is structurally different from pre-2008 conventional policy.
