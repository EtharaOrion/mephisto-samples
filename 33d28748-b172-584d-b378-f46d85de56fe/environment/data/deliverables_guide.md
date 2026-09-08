# Deliverables Guide

## Files to submit

Submit these three files to `/home/workspace/`:

1. `cftc_positioning.py` - runnable Python with two CLI modes:
   - `python3 cftc_positioning.py --train <input_dir> <state_json>` (fit)
   - `python3 cftc_positioning.py --backtest <input_dir> <state_json> <output_json>` (predict)
2. `requirements.txt` - dependency list (numpy, pandas, stdlib only)
3. `positioning_results.json` - full deliverable per output schema

## Output schema

```json
{
  "task_id": "cftc_futures_positioning_book",
  "bundle_uuid": "<uuid>",
  "per_week": [
    {
      "week_ending": "2025-01-07",
      "per_market": [
        {
          "market_id": "CL",
          "commercial_net_direction": "up",
          "magnitude_bucket": "small_increase",
          "crowding_regime": "neutral",
          "extreme_positioning_flag": false,
          "direction_probability": 0.55,
          "self_reported_certainty": 0.6
        }
      ]
    }
  ],
  "self_reported_metrics": {
    "L1_commercial_direction_est": 0.58,
    "L2_magnitude_bucket_est": 0.32,
    "L3_crowding_regime_est": 0.45,
    "L4_extreme_flag_f1_est": 0.42,
    "L5_rank_correlation_est": 0.15
  },
  "per_item_confidence": {
    "CL:2025-01-07": 0.62,
    "NG:2025-01-07": 0.55
  }
}
```

The `per_item_confidence` dict maps `"<market_id>:<week_ending>"` keys to a
float in `[0, 1]` expressing your confidence that the corresponding
`commercial_net_direction` prediction is correct. Feeds the L7 lane below.

## Constraint reminders

- Values in `per_market` MUST use exactly the vocabulary in `cftc_book_lib.py`:
  `VALID_DIRECTIONS`, `VALID_MAGNITUDES`, `VALID_REGIMES`.
- `direction_probability` and `self_reported_certainty` are floats on `[0, 1]`.
- No future data: for week_ending D, use only COT data with report_date < D.
- No network: `network_mode = no-network`.
- Per-observation budget: full backtest MUST complete in <= 30 minutes.

## L7 confidence calibration (Brier)

The judge computes a Brier score over your `per_item_confidence` versus the
realized correctness of each L1 direction prediction:

    BS = mean_i (confidence_i - correct_i)^2

where `correct_i = 1` if your direction matched reality else `0`. Points:

    pts = 5 * max(0, 1 - 2 * BS)

BS=0 -> 5 pts, BS=0.25 -> 2.5 pts, BS>=0.5 -> 0 pts. Random 0.5 confidence
on a 50/50 base rate yields BS=0.25 (calibration break-even). Missing or
malformed `per_item_confidence` -> 0 pts. `self_reported_metrics` is retained
for informational use but no longer gates L7.
