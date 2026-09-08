# Deliverables Guide — CPI Nowcast + Positioning Book

## Files you MUST submit

1. `cpi_nowcast_book.py` — a runnable Python script with two modes:
   - `python3 cpi_nowcast_book.py --train --data attachments/cpi_train.csv --macro attachments/macro_train.csv --rates attachments/rates_train.csv --state reference_state.json`
   - `python3 cpi_nowcast_book.py --backtest --data <cpi_csv> --macro <macro_csv> --rates <rates_csv> --prints <test_prints_json> --state reference_state.json --output nowcast_results.json`
2. `requirements.txt` — pip dependency list (numpy, pandas, scipy).
3. `nowcast_results.json` — the JSON produced by your script when invoked in `--backtest` mode over the judge-injected 2025 monthly panel.

## `nowcast_results.json` schema

```
{
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "print_count": <int>,
  "prints": [
    {
      "series":                       "CPIAUCSL" | "CPILFESL" | "PCEPI" | "PCEPILFE",
      "ref_month":                    "YYYY-MM",
      "release_date":                 "YYYY-MM-DD",
      "predicted_yoy_pct":            <float>,    /* your nowcast of YoY inflation for this print, in percentage points */
      "predicted_value":              <float>,    /* your predicted CPI/PCE index level (optional; derived from YoY x year-ago) */
      "prediction_interval":          [<float>, <float>],
      "detected_regime":              "cutting" | "holding" | "hiking",
      "positioning_book": {
        "duration_2y":    <float>,   /* signed 2-yr duration exposure, unit-notional */
        "duration_10y":   <float>,   /* signed 10-yr duration exposure, unit-notional */
        "breakeven_10y":  <float>    /* signed 10-yr breakeven position (long = long inflation) */
      },
      "naive_year_ago_carry_yoy_pct": <float>    /* prior-month YoY that would have been the naive baseline */
    },
    ...
  ],
  "self_reported_metrics": {
    "headline_cpi_mae_pp":             <float>,
    "core_cpi_mae_pp":                 <float>,
    "pce_mae_pp":                      <float>,
    "core_pce_mae_pp":                 <float>,
    "positioning_pnl_sum":             <float>,
    "directional_beat_consensus_rate": <float>
  },
  "detected_fed_pivot_events": [
    {"event_date": "YYYY-MM-DD", "event_month": "YYYY-MM", "kind": "holding_to_cutting" | "..."}
  ]
}
```

## Field semantics

| Field                                       | Units | Notes |
|---------------------------------------------|-------|-------|
| `predicted_yoy_pct`                         | %     | Year-over-year inflation rate. E.g., `2.85` means +2.85% YoY. |
| `predicted_value`                           | index | Optional. The CPI/PCE index level implied by your YoY prediction + year-ago value. Judge scores YoY only. |
| `prediction_interval`                       | %     | [lo, hi] two-element list, half-width representing your uncertainty. Not scored but must be well-formed. |
| `detected_regime`                           | enum  | Fed policy regime label at print time. |
| `positioning_book.duration_2y`              | dim   | Signed 2-yr Treasury duration exposure in unit notional. Positive = long duration (bet on lower yields). |
| `positioning_book.duration_10y`             | dim   | Signed 10-yr Treasury duration exposure in unit notional. |
| `positioning_book.breakeven_10y`            | dim   | Signed 10-yr breakeven inflation position. Positive = long inflation (bet on rising breakevens). |
| `naive_year_ago_carry_yoy_pct`              | %     | The naive baseline (prior month's YoY carried forward) used for judging the beat-rate lane. Judge recomputes this independently; report yours for tie-breaks. |
| `detected_fed_pivot_events`                 | list  | Fed policy pivots your system flagged inside the 2025 test period. See `attachments/deliverables_guide.md` §Bonus. |

## Constraints

- All floats: use standard JSON representation, not `Infinity`/`NaN`.
- Every entry in `prints` MUST correspond to an entry in the judge's `test_prints.json` (matched by `(series, ref_month)`). Missing prints score 0 on the covered lane.
- `predicted_yoy_pct` MUST be finite. Non-finite values are treated as 0% YoY (scoring you into the zero anchor).
- `detected_regime` MUST be one of the three allowed labels.
- All numeric predictions must be consistent with your submitted `self_reported_metrics` (the judge recomputes each metric independently and vetoes on divergence beyond tolerance).
- Do NOT emit any field not in the schema; extras are ignored but may inflate submission size.

## Judge scoring — output metrics you are graded on

The judge scores your submission on eight lanes over the hidden 2025 monthly panel:

1. **Headline CPI nowcast accuracy (20 pts)** — MAE (pp) on CPIAUCSL YoY.
2. **Core CPI nowcast accuracy (15 pts)** — MAE (pp) on CPILFESL YoY.
3. **Headline PCE nowcast accuracy (15 pts)** — MAE (pp) on PCEPI YoY.
4. **Core PCE nowcast accuracy (10 pts)** — MAE (pp) on PCEPILFE YoY.
5. **Positioning-book PnL (15 pts)** — Simulated 1-week post-print PnL from your `positioning_book` positions; Sharpe cap 1.5.
6. **Directional accuracy vs consensus (10 pts)** — Fraction of prints beating the naive year-ago-carry.
7. **Anti-fabrication integrity (5 pts)** — Self-report vs judge-recompute agreement (HARD VETO on divergence: zeros headline + core CPI lanes).
8. **Cross-series stability (10 pts, aggregated)** — Variance-and-mean of the four accuracy lanes across CPI/Core-CPI/PCE/Core-PCE.

Plus **Fed-pivot detection bonus (+10 pts, aggregated)** for correctly identifying hidden 2025 Fed policy pivots (`cutting <-> holding <-> hiking` transitions) within 1-month tolerance, saturating at 3+ matches.
