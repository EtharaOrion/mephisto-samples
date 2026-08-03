# Deliverables Guide — treasury_liquidity_provisioning_book

Submit exactly three files to `/home/workspace/` before your session ends:

1. **`treasury_liquidity.py`** — your positioning-book Python solver.
2. **`requirements.txt`** — pinned dependencies (`numpy`, `pandas`, `scipy` allowed;
   no Bloomberg, Yahoo, Kaggle, `hmmlearn`, direct-BLS, per-CUSIP price sources).
3. **`positioning_results.json`** — the JSON artifact keyed by rebalance date.

## Solver CLI contract

Your `treasury_liquidity.py` MUST support two subcommands:

```
python3 treasury_liquidity.py --train    <input_dir> <state_json>
python3 treasury_liquidity.py --backtest <input_dir> <state_json> <output_json>
```

Where:

- `<input_dir>` — directory containing the flat-layout CSVs
  (`sofr_train.csv`, `sofr_test.csv`, `repo_train.csv`, `repo_test.csv`,
  `tga_dts_train.csv`, `tga_dts_test.csv`, `macro_train.csv`, `macro_test.csv`,
  `bill_auctions_train.csv`, `bill_auctions_test.csv`,
  `short_end_curve_train.csv`, `short_end_curve_test.csv`,
  `pd_positions_train.csv`, `pd_positions_test.csv`) plus the
  `test_ladder_dates.json` file listing the rebalance dates.
- `<state_json>` — path to write (train) or read (backtest) your persistent state
  artifact. This is your model, keyed by hyperparameters + fitted statistics.
- `<output_json>` — where `--backtest` writes your `positioning_results.json`.

The judge invokes your `--backtest` mode on the hidden test window; you are also
responsible for producing `positioning_results.json` at your working turn (via
`--train` then `--backtest` yourself) so the judge can read it as a static
artifact.

## Output schema (positioning_results.json)

Root object:

```json
{
  "task_id": "treasury_liquidity_provisioning_book",
  "bundle_uuid": "9c463536-e514-5a50-9ff6-81ad513bae32",
  "per_date": [ /* one entry per rebalance date */ ],
  "self_reported_metrics": { /* your best-effort lane-level estimates */ }
}
```

Each `per_date` entry:

- `date` — ISO `YYYY-MM-DD`.
- `allocation` — dict with all 6 keys `{b4w, b8w, b13w, b26w, rrp, iorb}`, each
  on `[0, 1]`, summing to 1.0 ±1e-6. `b4w`..`b26w` are 4/8/13/26-week Treasury
  bill tenors; `rrp` is O/N reverse-repo; `iorb` is interest-on-reserve-balances
  proxy for cash held at the Fed.
- `regime_label` — one of `{deep_qt, normal, elevated_stress, extreme_stress}`.
- `extreme_stress_flag` — boolean.
- `extreme_stress_probability` — float in `[0, 1]`.
- `supply_direction` — one of `{up, flat, down}`.
- `self_reported_certainty` — float in `[0, 1]` reflecting your confidence in
  this observation's positioning.

## Self-reported metrics

Populate `self_reported_metrics` with your best-effort estimate of each lane's
score for your submission. The judge compares against its own recompute; any
field deviating beyond ±0.20 zeros the anti-fabrication lane (L7, 5 pts).

Recommended fields:

- `L1_ladder_return_lane_est` — expected annualized Sharpe / 1.5.
- `L2_regime_classification_est` — expected 4-class accuracy.
- `L3_extreme_stress_detection_est` — expected F1.
- `L4_supply_direction_est` — expected 3-class accuracy.
- `L6_money_market_pnl_proxy_est` — expected MM Sharpe / 1.5.
- `L8_cross_week_stability_est` — expected mean-weekly-normalized performance.

## Submission conventions

- Do not read any file outside `/home/workspace/` at solve time.
- All numeric fields must be finite (no `NaN`, no `inf`).
- Do not fabricate `self_reported_metrics` — the anti-fabrication gate zeros L7
  if your self-report deviates from judge-recompute by more than 0.20.
- Ensure `positioning_results.json` covers every date in `test_ladder_dates.json`
  under `rebalance_dates`. Missing entries are treated as zero allocation.

## Rebalance calendar

The test window contains approximately 395 rebalance dates spanning 2025-01-01
through 2026-07-31 on the business-day calendar (dates where the short-end
Treasury yield curve is present). See `test_ladder_dates.json.rebalance_dates`
for the exact list.
