# Deliverables Guide — FDIC Bank Capital Projection Book

## Files you MUST submit

1. `bank_capital_projection.py` — a runnable Python script with two modes:
   - `python3 bank_capital_projection.py --train --data attachments/financials_train.csv --macro attachments/macro_indicators_train.csv --state reference_state.json`
   - `python3 bank_capital_projection.py --backtest --data <financials_csv> --macro <macro_csv> --institutions <institutions_json> --state reference_state.json --output projection_results.json`
2. `requirements.txt` — pip dependency list (numpy, pandas, scipy).
3. `projection_results.json` — the JSON produced by your script when invoked in `--backtest` mode over the judge-injected 2025 quarterly panel.

## `projection_results.json` schema

```
{
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "observation_count": <int>,
  "observations": [
    {
      "institution_id":         "fdicXXXXXXX",
      "cert":                   <int>,
      "name":                   "<institution name>",
      "repdte":                 "YYYYMMDD",
      "size_bucket":            "community" | "mid" | "regional" | "large",

      "detected_macro_regime":  "hiking" | "cutting" | "on_hold",
      "detected_buffer_regime": "buffer_comfortable" | "buffer_eroding" | "buffer_critical",
      "predicted_pca_zone":     "well_capitalized" | "adequately_capitalized" | "undercapitalized" | "significantly_under" | "critically_under",

      "predicted_metrics": {
        "IDT1CER":   <float>,   "IDT1RWAJR": <float>,
        "RBC1AAJ":   <float>,   "RBCRWAJ":   <float>,
        "ROAQ":      <float>,   "ROEQ":      <float>,   "NIMYQ": <float>,
        "NPERFV":    <float>,   "NCLNLSR":   <float>,   "LNATRESR": <float>,
        "EQV":       <float>,   "LNLSDEPR":  <float>
      },

      "predicted_asset_growth_rate":   <float>,
      "predicted_deposit_growth_rate": <float>
    },
    ...
  ],
  "self_reported_metrics": {
    "mean_capital_ratio_mae_pp":      <float>,
    "mean_earnings_mape":             <float>,
    "mean_tail_bound_mae_pp":         <float>,
    "mean_asset_growth_mae":          <float>,
    "mean_deposit_growth_mae":        <float>,
    "pca_zone_accuracy":              <float>
  },
  "detected_pca_zone_events": [
    {"event_date": "YYYYMMDD", "cert": <int>, "kind": "well_capitalized_to_adequately_capitalized", "predicted_zone": "adequately_capitalized"}
  ]
}
```

## Field semantics

| Field                                   | Units  | Notes |
|-----------------------------------------|--------|-------|
| `predicted_metrics.IDT1CER`             | %      | Common Equity Tier 1 ratio (Basel III). Reported to 4-decimal precision. |
| `predicted_metrics.IDT1RWAJR`           | %      | Tier-1 risk-based capital ratio. |
| `predicted_metrics.RBC1AAJ`             | %      | Tier-1 leverage ratio (average assets denominator). |
| `predicted_metrics.RBCRWAJ`             | %      | Total risk-based capital ratio. |
| `predicted_metrics.ROAQ`                | %      | Return on assets, annualized quarterly. |
| `predicted_metrics.ROEQ`                | %      | Return on equity, annualized quarterly. |
| `predicted_metrics.NIMYQ`               | %      | Net interest margin, annualized quarterly. |
| `predicted_metrics.NPERFV`              | %      | Nonperforming assets to total assets. |
| `predicted_metrics.NCLNLSR`             | %      | Net charge-offs to loans & leases. |
| `predicted_metrics.LNATRESR`            | %      | Loan-loss reserve ratio. |
| `predicted_metrics.EQV`                 | %      | Equity to assets ratio. |
| `predicted_metrics.LNLSDEPR`            | %      | Loans + leases to deposits ratio. |
| `predicted_pca_zone`                    | enum   | Categorical label per 12 CFR § 6.4 PCA capital-adequacy zone. |
| `predicted_asset_growth_rate`           | ratio  | (`ASSET_t` - `ASSET_{t-1}`) / `ASSET_{t-1}`. Quarterly, unannualized. |
| `predicted_deposit_growth_rate`         | ratio  | (`DEPDOM_t` - `DEPDOM_{t-1}`) / `DEPDOM_{t-1}`. Quarterly, unannualized. |
| `detected_pca_zone_events`              | list   | PCA-zone transitions your system flagged inside the test period. |

## Constraints

- All floats: use standard JSON representation, not `Infinity`/`NaN`.
- `predicted_metrics` MUST contain all listed keys as finite floats for every observation.
- `predicted_pca_zone` MUST be one of the five 12-CFR-§-6.4 categorical labels.
- All numeric predictions must be consistent with your submitted `self_reported_metrics` (the judge recomputes each metric independently and vetoes on divergence beyond tolerance).
- Do NOT emit any field not in the schema; extras are ignored but may inflate submission size.

## Judge scoring — output metrics you are graded on

The judge scores your submission on eight lanes over the hidden 2025 quarterly panel:

1. **Capital-ratio projection accuracy (25 pts)** — MAE across the four capital ratios.
2. **Earnings projection accuracy (15 pts)** — MAPE across NIM + ROA + ROE.
3. **Tail-risk control (15 pts)** — MAE across nonperforming + net charge-offs.
4. **PCA-zone classification accuracy (10 pts)** — categorical accuracy on 5-zone classification.
5. **Asset-growth projection (10 pts)** — MAE on quarterly ASSET growth rate.
6. **Deposit-stability projection (10 pts)** — MAE on DEPDOM growth rate.
7. **Anti-fabrication integrity (5 pts)** — self-report vs judge-recompute agreement.
8. **Cross-size-bucket stability (10 pts, aggregated)** — variance of capital-ratio lane across the four size buckets.

Plus **PCA-zone-transition detection bonus (+10 pts, aggregated)** for correctly identifying hidden 2025 quarter-over-quarter zone transitions on stressed institutions, saturating at 3+ matches within 1-quarter tolerance.
