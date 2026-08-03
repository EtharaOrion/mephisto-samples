## Title

Fed Funds Regime + Positioning Book

## Task Requirements

You are the lead rates strategist at a global asset manager. Every week, your
desk publishes (a) a forward Fed policy regime classification, (b) one-week
forward forecasts for the 2Y and 10Y Treasury yields, (c) a Treasury duration
+ curve-slope + front-end-carry positioning book sized in unit-notional terms,
and (d) around FOMC meeting dates, a forward decision-classification call
(hold / cut_XX / hike_XX in 25 bps increments).

Your job is to build a system that, for the hidden 2025Q1-2026H1 test window
covering approximately 77 weekly windows plus 12 FOMC meetings, generates
per-window:

- **Fed regime label** — one of `{hiking, on_hold_hawkish, on_hold_neutral,
  on_hold_dovish, cutting}` inferred from observable rate + macro signals.
- **2Y and 10Y yield forecasts one week ahead**, in bps (basis points).
- **Positioning book** — signed unit-notional exposures on
  `{duration_2y, duration_10y, slope_2s10s, carry_front_end}`.

And per FOMC event:

- **Predicted rate decision** — one of `{hold, cut_25, cut_50, cut_75, cut_100,
  hike_25, hike_50, hike_75, hike_100}`.

The system MUST include:

1. **Historical rate + macro panel model.** Reads the pre-2025 FRED daily/
   monthly panel (2010-2024) of Fed Funds + Treasury yields + unemployment +
   CPI and learns per-phase dynamics of rates, yields, and macro-to-rates
   pass-through.
2. **FOMC-cadence + weekly-cadence forecaster.** Reads the FRED daily rates
   panel + monthly macro panel through each test-window's Friday close +
   the hardcoded FOMC meeting calendar, and produces per-week regime label +
   yield forecasts + positioning book, plus per-FOMC-event decision prediction.
3. **Backtest harness.** The system MUST support invocation as:
     `python3 fed_funds_positioning.py --train <input_dir> <state_json>`
     `python3 fed_funds_positioning.py --backtest <input_dir> <state_json> <output_json>`
   The judge invokes your script once against the full held-out 2025Q1-2026H1
   panel. Input directory at judge time contains the hidden test CSVs +
   `test_windows_schedule.json` (list of Friday dates) + agent-visible
   `fomc_meetings_test_2025_2026.csv` (dates only, no rate decisions).

## Optimization Objectives (in priority order)

Your outputs are scored per window on eight lanes, aggregated with a
cross-cadence stability penalty and a FOMC-decision bonus.

1. **Regime classification (20 pts).** Fraction of weekly windows where your
   `predicted_regime` matches the realized regime. Full marks: accuracy = 1.00.
   Zero: accuracy ≤ 0.60.
2. **2Y yield forecast (15 pts).** MAE (bps) between your predicted next-week
   `predicted_2y_bps_next_wk` and realized. Full marks: MAE ≤ 5 bps. Zero:
   MAE ≥ 50 bps.
3. **10Y yield forecast (15 pts).** MAE (bps) on 10Y. Full marks: MAE ≤ 8 bps.
   Zero: MAE ≥ 80 bps.
4. **Duration positioning PnL (15 pts).** Realized PnL from your
   `duration_2y` + `duration_10y` positions against realized next-week yield
   changes, annualized Sharpe capped at 2.0.
5. **Slope positioning PnL (10 pts).** Sharpe of your `slope_2s10s`
   position PnL vs realized 2s10s spread changes, capped at 2.0.
6. **Carry position PnL (10 pts).** Cumulative PnL from
   `carry_front_end`. Full marks: sum ≥ +2.0. Zero: sum ≤ -2.0.
7. **Anti-fabrication (5 pts).** The judge independently recomputes each
   metric from your raw predictions against realized outcomes. Deviations
   beyond tolerance zero this lane AND zero the L1-L6 accuracy/PnL lanes for
   the whole cycle.
8. **Cross-cadence stability (10 pts, aggregated).** Variance-and-mean of the
   L1-L6 lane scores across 6-month buckets in the test window. A solver that
   hyper-fits one half of the window while missing the other is penalized.

**FOMC-decision bonus (+10 pts, aggregated).** If your `fomc_events` predicted
decisions match the true FOMC decision on each of the ~12 meetings in the test
window, your submission earns up to +10 bonus points; saturates at 3+ matches.

## Benchmark composition

- **Predict-last-regime baseline.** Predict this week's regime = previous
  week's regime. Predict yields = last observation. Positioning = zero.
- **Predict-consensus-holds baseline.** Always predict `on_hold_neutral`
  regime. Yields = last DGS2/DGS10 value. Positioning = 50/50 duration.
- **Predict-year-ago-YoY baseline.** Regime + yields + positions = same as
  12 months prior.

Your submission is scored on absolute quality, not excess over baselines;
the baselines are informational.

## Provided Data and Materials

All files below live in the `attachments/` directory.

| File | Format | Description |
| --- | --- | --- |
| `attachments/fed_funds_train.csv` | CSV | Pre-2025 daily Fed Funds series: `date, DFF, FEDFUNDS, DFEDTARU, DFEDTARL`. Covers 2010-01-01 through 2024-12-31 (~15 years). DFEDTARU/DFEDTARL are the FOMC target-range brackets. |
| `attachments/rates_train.csv` | CSV | Pre-2025 daily Treasury yields: `date, DGS2, DGS10, T10Y2Y`. Same window. |
| `attachments/macro_train.csv` | CSV | Pre-2025 monthly macro: `date, UNRATE, CPIAUCSL`. Same window. |
| `attachments/fomc_meetings_2010_2026.csv` | CSV | FOMC meeting calendar 2010-2026 (~137 events; rate_decision column is populated for pre-2025 meetings only; 2025-2026 entries have empty rate_decision — those are what you predict). |
| `attachments/train_period.txt` | text | Two dates comma-separated: `2010-01-01,2024-12-31`. |
| `attachments/valid_period.txt` | text | Two dates comma-separated: `2024-01-01,2024-12-31`. Reserved for hyperparameter selection. |
| `attachments/deliverables_guide.md` | markdown | JSON schema of `positioning_results.json` + submission conventions. |
| `attachments/requirements.txt` | text | Python dependencies (numpy, pandas, scipy). |

## Constraints

- Each weekly window's `predicted_regime` MUST be one of the 5 allowed labels.
- Each `predicted_2y_bps_next_wk` and `predicted_10y_bps_next_wk` MUST be a
  finite float in basis points.
- `positioning_book` MUST contain finite floats for keys
  `duration_2y`, `duration_10y`, `slope_2s10s`, `carry_front_end`.
- Each FOMC event's `predicted_decision` MUST be one of the allowed decision
  strings.
- **No future data.** For a weekly window at Friday date `T`, your solver may
  only read data with `date <= T`. Concretely, do not read next Friday's
  DGS2/DGS10 to inform this week's forecast.
- **No network.** All computation is offline.
- **No cross-directory reads.** Training data (`attachments/`) is physically
  separated from held-out test data. Your `--backtest` invocation reads
  exclusively the paths passed on the positional CLI arguments.
- Per-window backtest wall time: ≤ 2 seconds; total backtest wall time over
  the full test cycle: ≤ 30 minutes.

## Final Deliverables

- `fed_funds_positioning.py` — a runnable Python script that accepts:
  - `--train <input_dir> <state_json>` (fits on training data, writes state)
  - `--backtest <input_dir> <state_json> <output_json>` (reads state,
    iterates the test panel, writes results)
- `requirements.txt` — dependency list.
- `positioning_results.json` — the JSON produced by `--backtest`. Schema
  authoritatively defined below (also mirrored in
  `attachments/deliverables_guide.md`).

## Output Schema (`positioning_results.json`)

Your submission MUST produce a JSON file matching the schema below EXACTLY.
Key names, nesting, and the seven `self_reported_metrics` sub-keys are
enforced. The judge runs a schema pre-check before scoring; a missing or
misspelled top-level key emits `TOTAL_SCORE 0.00` with a machine-readable
`schema_error: <detail>` and terminates. In addition, an empty or absent
`self_reported_metrics` object triggers the L7 anti-fabrication veto,
which zeroes lanes L1-L6 (regime, both yield forecasts, and all three
positioning PnL lanes) even when your `weekly_windows` are otherwise well
formed. Emit all keys, populated with finite values, on every run.

```
{
  "generated_at":         "YYYY-MM-DDTHH:MM:SSZ",
  "weekly_window_count":  <int>,
  "weekly_windows": [
    {
      "window_date":                 "YYYY-MM-DD",
      "predicted_regime":            "hiking" | "on_hold_hawkish" | "on_hold_neutral" | "on_hold_dovish" | "cutting",
      "predicted_2y_bps_next_wk":    <float>,
      "predicted_10y_bps_next_wk":   <float>,
      "positioning_book": {
        "duration_2y":     <float>,
        "duration_10y":    <float>,
        "slope_2s10s":     <float>,
        "carry_front_end": <float>
      }
    }
  ],
  "fomc_event_count": <int>,
  "fomc_events": [
    {
      "meeting_date":       "YYYY-MM-DD",
      "predicted_decision": "hold" | "cut_25" | "cut_50" | "cut_75" | "cut_100" | "hike_25" | "hike_50" | "hike_75" | "hike_100"
    }
  ],
  "self_reported_metrics": {
    "regime_accuracy":    <float>,
    "yield_2y_mae_bps":   <float>,
    "yield_10y_mae_bps":  <float>,
    "duration_pnl_sum":   <float>,
    "slope_pnl_sum":      <float>,
    "carry_pnl_sum":      <float>,
    "fomc_hit_count":     <int>
  }
}
```

Required top-level keys: `generated_at`, `weekly_window_count`,
`weekly_windows`, `fomc_event_count`, `fomc_events`, `self_reported_metrics`.
Required `self_reported_metrics` sub-keys (all seven, all finite):
`regime_accuracy`, `yield_2y_mae_bps`, `yield_10y_mae_bps`,
`duration_pnl_sum`, `slope_pnl_sum`, `carry_pnl_sum`, `fomc_hit_count`.

## Special Notes

1. The training period spans a full Fed policy cycle: 2010-2015 zero-lower-
   bound, 2015-2019 gradual hiking, 2020 COVID emergency cutting (unscheduled
   3/3 -50 bps and 3/15 -100 bps to ZLB), 2020-2022 hold, 2022-2023
   aggressive hiking (11 hikes to 5.25-5.50%), 2024 initial cutting. Your
   system must remain robust across all regimes. Note that pre-2010 pre-GFC
   conventional policy is intentionally excluded from training since it uses
   a different operational regime (no target range, no forward guidance).
2. **Data authenticity requirement.** All values in `positioning_results.json`
   must genuinely reflect execution. The judge independently recomputes each
   metric from your raw predictions against realized outcomes and compares
   against your `self_reported_metrics`. Deviations beyond tolerance zero the
   anti-fabrication lane AND zero the L1-L6 accuracy/PnL lanes. Fabricated
   outputs have caused entire-cycle disqualification in prior evaluations.
3. **Regime-change detection matters.** The hidden test window contains an
   observed Fed hiking-plateau → cutting transition (rate held flat at ~4.33%
   Jan-Aug 2025, then cutting Sept 2025 onward). A solver that identifies
   the transition correctly earns significantly more L1 + FOMC-bonus points
   than one that always predicts "hold".
4. **Cross-cadence heterogeneity is intentional.** Weekly regime + yield
   forecasts and FOMC-event decision predictions have different information
   sources; a solver that fits one cadence well while ignoring the other
   loses the L8 stability lane.
5. **FOMC calendar is hardcoded reference metadata.** The
   `fomc_meetings_2010_2026.csv` file is agent-visible and contains all
   ~137 FOMC events 2010-2026 with populated rate_decision column for
   pre-2025 meetings only. The Federal Reserve publishes future FOMC dates
   ~2 years ahead but does NOT provide a stable CSV API — the hardcoded
   file is authoritative for meeting dates but you MUST predict the
   rate_decision for post-2024 events.
6. At judge time, `fed_funds_positioning.py` is executed in an isolated
   evaluation directory. Hidden test CSVs contain 2025-2026H1 data; the
   `test_windows_schedule.json` file specifies which Friday dates you must
   emit predictions for. Your code MUST load fitted state exclusively from
   the state_json path passed on CLI.

## Task Input Description

The following input files are provided with the task, all located in the
`attachments/` directory:

| File | Format | Description |
| --- | --- | --- |
| `attachments/fed_funds_train.csv` | `.csv`, `utf-8` | Pre-2025 daily Fed Funds panel. |
| `attachments/rates_train.csv` | `.csv`, `utf-8` | Pre-2025 daily Treasury yields. |
| `attachments/macro_train.csv` | `.csv`, `utf-8` | Pre-2025 monthly unemployment + CPI. |
| `attachments/fomc_meetings_2010_2026.csv` | `.csv`, `utf-8` | FOMC calendar (dates only for post-2024 events). |
| `attachments/train_period.txt` | `.txt`, `utf-8` | Training period, `YYYY-MM-DD,YYYY-MM-DD`. |
| `attachments/valid_period.txt` | `.txt`, `utf-8` | Validation period, `YYYY-MM-DD,YYYY-MM-DD`. |

Reference document: `attachments/deliverables_guide.md`.

## Deliverable Requirements

- `fed_funds_positioning.py` | Python source file
- `requirements.txt` | plain text
- `positioning_results.json` | JSON (per-cycle output produced by `--backtest`)
