# Deliverables Guide — courtlistener_appellate_disposition_timing_calibration

Submit exactly three files to `/home/workspace/` before your session ends:

1. **`appellate_timing.py`** — your time-to-disposition solver.
2. **`requirements.txt`** — pinned dependencies (`numpy`, `pandas`; no Bloomberg,
   Yahoo, Kaggle, `hmmlearn`, direct-BLS, per-case-outcome sources).
3. **`timing_results.json`** — the JSON artifact keyed by CourtListener docket id.

## Solver CLI contract

Your `appellate_timing.py` MUST support two subcommands:

```
python3 appellate_timing.py --train    <input_dir> <state_json>
python3 appellate_timing.py --backtest <input_dir> <state_json> <output_json>
```

Where:

- `<input_dir>` — directory containing the flat-layout CSVs
  (`dockets_train.csv`, `dockets_test.csv`) plus `test_case_ids.json` listing
  the case ids you must produce predictions for.
- `<state_json>` — path to write (train) or read (backtest) your persistent
  state artifact (your fitted per-circuit medians, regime baselines, etc.).
- `<output_json>` — where `--backtest` writes your `timing_results.json`.

The judge invokes your `--backtest` mode on the hidden test window; you are
also responsible for producing `timing_results.json` at your working turn (via
`--train` then `--backtest` yourself) so the judge can read it as a static
artifact.

## Output schema (timing_results.json)

Root object:

```json
{
  "task_id": "courtlistener_appellate_disposition_timing_calibration",
  "bundle_uuid": "74a90894-392e-58cd-a714-5a31e8ac1322",
  "per_case": [ /* one entry per case_id in test_case_ids.json */ ],
  "circuit_month_regime": {
    "ca1|2025-04": "moderate_complexity",
    "ca2|2025-04": "elevated_complexity"
    /* keyed by 'court_id|YYYY-MM' */
  },
  "self_reported_metrics": { /* your best-effort lane-level estimates */ }
}
```

Each `per_case` entry:

- `case_id` — CourtListener docket id (integer as string).
- `court_id` — one of `{ca1..ca11, cadc, cafc}`.
- `case_type_bucket` — one of `{civil_general, criminal, prisoner_petition,
  administrative_agency, immigration, labor_erisa, ip_patent, tax, other}`.
- `regime_label` — one of `{low_complexity, moderate_complexity,
  elevated_complexity, backlog_pressure}`.
- `predicted_days_to_disposition` — float ≥ 0.
- `predicted_disposition_date` — ISO `YYYY-MM-DD`.
- `stall_probability` — float in `[0, 1]` (>1yr no-motion likelihood).
- `stall_flag` — boolean.
- `predicted_motion_count` — float ≥ 0 (expected motions across case life).
- `case_type_rank_key` — string `"court_id|case_type_bucket"` used for
  per-group ordering in L4 lane.
- `self_reported_certainty` — float in `[0, 1]`.
- `age_at_boundary_days` — int, days between date_filed and 2026-01-01.

## Self-reported metrics

Populate `self_reported_metrics` with your best-effort estimate of each lane's
score for your submission. The judge compares against its own recompute; any
field deviating beyond ±0.20 zeros the anti-fabrication lane (L7, 5 pts).

Recommended fields:

- `L1_timing_rmse_lane_est` — expected `1.0 − (RMSE_ratio − 0.30) / 0.70`.
- `L2_circuit_regime_classification_est` — expected 4-class accuracy.
- `L3_stall_detection_est` — expected F1.
- `L4_case_type_ordering_est` — expected mean Spearman rho.
- `L5_motion_count_regression_est` — expected R².
- `L6_disposition_timing_pnl_est` — expected Sharpe / 1.5.
- `L8_cross_month_stability_est` — expected mean-monthly-normalized performance.

## Submission conventions

- Do not read any file outside `/home/workspace/` at solve time.
- All numeric fields must be finite (no `NaN`, no `inf`).
- Do not fabricate `self_reported_metrics` — the anti-fabrication gate zeros L7
  if your self-report deviates from judge-recompute by more than 0.20.
- Ensure `timing_results.json` covers every case id in `test_case_ids.json`.
  Missing entries are treated as zero prediction.
