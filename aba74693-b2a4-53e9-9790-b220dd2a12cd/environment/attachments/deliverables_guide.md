# Deliverables Guide — Treasury Auction Bidding Calibration

## Files you MUST submit

1. `auction_bidding.py` — a runnable Python script with two modes:
   - `python3 auction_bidding.py --train --data attachments/auction_history_train.csv --macro attachments/macro_indicators_train.csv --state reference_state.json`
   - `python3 auction_bidding.py --backtest --data <auction_history_csv> --macro <macro_csv> --state reference_state.json --output bidding_results.json`
2. `requirements.txt` — pip dependency list (numpy, pandas, scipy).
3. `bidding_results.json` — the JSON produced by your script when invoked in `--backtest` mode over the judge-injected 2025 auction cycle.

## `bidding_results.json` schema

```
{
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "auction_count": <int>,
  "auctions": [
    {
      "auction_id":         "a0001",
      "cusip":              "912796XXX",
      "auctionDate":        "YYYY-MM-DD",
      "securityType":       "Bill" | "Note" | "Bond",
      "securityTerm":       "13-Week" | "10-Year" | ...,
      "tenor_years":        <float>,

      "predicted_bid_ladder": [
        {"yield_bps": <int>, "quantity_pct": <float>},
        ...
      ],

      "predicted_bidToCover":       <float>,
      "predicted_tail_bps":         <float>,
      "predicted_indirect_share":   <float>,
      "predicted_direct_share":     <float>,
      "predicted_allocation_share": <float>,
      "predicted_reference_yield":  <float>,
      "predicted_reference_dislocation_bps": <float>,

      "detected_regime":            "hiking" | "cutting" | "on_hold" | "transition"
    },
    ...
  ],
  "self_reported_metrics": {
    "mean_bidToCover_mape":            <float>,
    "mean_tail_rmse_bps":              <float>,
    "mean_indirect_share_mae":         <float>,
    "mean_allocation_share_mae":       <float>,
    "mean_reference_dislocation_mae_bps": <float>
  },
  "detected_regime_events": [
    {"event_date": "YYYY-MM-DD", "kind": "hiking_to_hold", "notes": "..."}
  ]
}
```

## Field semantics

| Field                                    | Units  | Notes |
|------------------------------------------|--------|-------|
| `predicted_bid_ladder`                   | list   | 5-15 rungs. `yield_bps` = predicted clearing yield in basis points (integer, e.g. 425 = 4.25%). For discount bills use the equivalent investment-rate yield in bps. `quantity_pct` = share of total tender at or below this yield (monotone-cumulative, ends at 100.0). |
| `predicted_bidToCover`                   | ratio  | Predicted `bidToCoverRatio` = total tenders / accepted. Typical realized range 1.8–3.2. |
| `predicted_tail_bps`                     | bps    | Predicted `highYield − averageMedianYield` in bps. Positive tail = weak auction. |
| `predicted_indirect_share`               | 0..1   | Predicted `indirectBidderAccepted / totalAccepted`. |
| `predicted_direct_share`                 | 0..1   | Predicted `directBidderAccepted / totalAccepted`. |
| `predicted_allocation_share`             | 0..1   | Predicted `allocationPercentage / 100`. |
| `predicted_reference_yield`              | %      | Your pre-auction reference yield (from public curve). |
| `predicted_reference_dislocation_bps`    | bps    | Predicted `auction highYield − reference yield` at auction eve. |
| `detected_regime`                        | enum   | Rate-cycle label at the auction date from your macro-context module. |
| `detected_regime_events`                 | list   | Regime transitions your system flagged inside the test period. |

## Constraints

- All floats: use standard JSON representation, not `Infinity`/`NaN`.
- `predicted_bid_ladder` must have monotone-non-decreasing `yield_bps` and monotone-non-decreasing `quantity_pct` (a cumulative curve).
- All numeric predictions must be finite and consistent with your submitted `self_reported_metrics` (the judge recomputes each metric independently and vetoes on divergence beyond tolerance).
- Do NOT emit any field not in the schema; extras are ignored but may inflate submission size.

## Judge scoring — output metrics you are graded on

The judge scores your submission on eight lanes over the hidden 2025 auction cycle:

- accuracy of the bid-ladder against the realized cumulative accepted-quantity curve
- accuracy of `predicted_bidToCover` against the realized `bidToCoverRatio`
- accuracy of `predicted_tail_bps` against the realized tail
- accuracy of `predicted_allocation_share` against the realized allocation share
- accuracy of `predicted_indirect_share` and `predicted_direct_share`
- accuracy of `predicted_reference_dislocation_bps` at auction eve
- integrity of `self_reported_metrics` (judge recomputes from raw ladder+predictions)
- stability of scores across the bill / note / bond product mix

There is an additional +10-point rate-regime-shift bonus for `detected_regime_events` matching hidden ground truth within a tolerance window.

## Testing your submission locally

- Fit your model on `attachments/auction_history_train.csv` + `attachments/macro_indicators_train.csv` (all auctions with `auctionDate < 2025-01-01`).
- Reserve the last 6 months of training (`2024-07-01..2024-12-31`, per `attachments/valid_period.txt`) for validation.
- Judge invokes `python3 auction_bidding.py --backtest --data <hidden_csv> --macro <hidden_macro_csv> --state reference_state.json --output bidding_results.json` in an isolated container with `attachments/` NOT re-attached — your script must load state exclusively from `reference_state.json` and read auction inputs exclusively from the paths passed on the command line.
