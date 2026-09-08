## Title

US Federal Appellate Case Disposition-Timing Calibration Book

## Task Requirements

You are a senior legal analyst on the appellate-timing desk of a litigation
analytics firm. Your job is to publish a calibration book that predicts how
long each currently-pending US federal appellate case will take to reach a
disposition. For the hidden 2025-01-01 to 2026-07-31 window (approximately
2500-5000 test cases across 13 US federal circuits), your system must
produce per pending case:

- **Time-to-disposition** — predicted days from Jan-2026 boundary to reach
  disposition, as `predicted_days_to_disposition` (float) and derived
  `predicted_disposition_date` (ISO date).
- **Circuit-procedural-complexity regime** — one of `{low_complexity,
  moderate_complexity, elevated_complexity, backlog_pressure}` describing
  the case's circuit's current procedural regime.
- **Stall detection** — `stall_probability` on `[0, 1]` (>1yr no-motion
  likelihood) and boolean `stall_flag`.
- **Case-type disposition ordering** — a rank key `case_type_rank_key`
  (`"court_id|case_type_bucket"`) so the judge can compute
  per-(circuit, case-type) rank orderings.
- **Motion-count regression** — `predicted_motion_count` (expected motions
  across case life; used against the realized-motion regressor lane).
- **Self-reported certainty** on `[0, 1]`.

You are also required to emit a per-(court_id, month) `circuit_month_regime`
map used for L2 regime classification, and block-level
`self_reported_metrics` used for the anti-fabrication gate.

## Optimization Objectives (in priority order)

Your outputs are scored per-case on eight lanes plus a timing-calibration
bonus lane:

1. **Timing RMSE lane (20 pts).** RMSE of your `predicted_days_to_disposition`
   against the realized disposition date, expressed as ratio to the median
   true days-to-disposition. Full 20 at ratio ≤ 0.30, zero at ratio ≥ 1.00.
2. **Circuit-regime classification (15 pts).** 4-class accuracy of your
   per-(court, month) regime label. Full 15 at accuracy 0.85, zero below 0.25.
3. **Stall detection (15 pts).** F1 of your `stall_flag` against realized
   >1yr no-motion binary. Full 15 at F1 1.00, zero below 0.10.
4. **Case-type ordering (10 pts).** Mean Spearman rho of your predicted-days
   rank against realized-days rank, computed per `case_type_rank_key` group.
   Full 10 at rho 0.50, zero below 0.00.
5. **Motion count regression (10 pts).** R² of `predicted_motion_count`
   against realized motions across the case life. Full 10 at R² 0.50.
6. **Disposition timing PnL (10 pts).** Sharpe of certainty-weighted timing
   PnL vs equal-weight baseline. Cap 1.5.
7. **Anti-fabrication (5 pts).** Judge independently recomputes L1/L2/L3/L4/L5/L6/L8
   metrics from your raw per-case predictions and compares against your
   `self_reported_metrics`. Deviation beyond ±0.20 on any tolerance-listed
   field zeros this lane.
8. **Cross-month stability (10 pts, aggregated).** Awards up to 10 pts based
   on mean-monthly-error-normalized performance, discounted by variance across
   the 19 test months.

**Timing-calibration bonus (+10 pts).** Backlog-clearing precision on the
2025-Q2 court-operations normalization regime-transition cases (empirical
anchor event: continued court operations normalization post-COVID-era pending
buildup). Saturates at 0.75.

## Benchmark composition

- **Naive median-per-circuit baseline.** Every case gets its circuit's
  training median days-to-disposition + regime `moderate_complexity` fixed.
  This is a genuine trivial baseline you must beat.
- **Naive constant mean baseline.** Every case gets 400 days + regime
  `moderate_complexity` fixed.
- **Naive random days baseline.** Uniform random in [30, 1500] days;
  random regime.

The persistence axis for appellate cases: age-at-boundary is highly
autocorrelated with itself (cases age 1 day per day), but the scoring lanes
grade RESIDUALS from circuit-conditional expected values (predicted minus
realized), regime CLASSIFICATION (not raw levels), stall PROBABILITY (not
raw times), and cross-month stability (penalizes single-month lucky calls).
This design deliberately BYPASSES the two prior CourtListener kills:
`legal_case_outcome_book` (naive-affirm stub beats frontier) is bypassed
because timing is continuous with no trivial-affirm baseline;
`legal_authority_influence_book` (95% zero-inflation on citation influence)
is bypassed because time-to-disposition is continuous non-sparse with
circuit as an expected feature (not accidental leak).

## Provided Data and Materials

All files below live in the `attachments/` directory and are symlinked to
`/home/workspace/` at container start.

| File | Format | Description |
| --- | --- | --- |
| `attachments/deliverables_guide.md` | markdown | Output schema + submission conventions. |
| `attachments/requirements.txt` | text | Baseline Python dependencies (numpy, pandas). |
| `attachments/dockets_train.csv` | CSV | 2018-01-01 to 2024-12-31 pre-boundary appellate docket panel across 13 US federal circuits. |
| `attachments/case_type_taxonomy.csv` | CSV | Case-type bucket definitions + example NOS mappings. |
| `attachments/circuit_metadata.csv` | CSV | Per-circuit judgeship count, typical panel size, seat city. |
| `attachments/train_period.txt` | text | Training-window bounds. |
| `attachments/valid_period.txt` | text | Optional train-side validation window. |
| `attachments/task_instruction.md` | markdown | This document. |

## Data schema (`dockets_train.csv`)

Columns extracted from the CourtListener BULK bucket `dockets-*.csv.bz2`
snapshot, filtered to the 13 US federal appellate circuits:

- `id` — CourtListener docket_id (use as `case_id`).
- `date_filed`, `date_terminated`, `date_argued`, `date_last_filing` — ISO dates.
- `court_id` — one of `{ca1..ca11, cadc, cafc}`.
- `case_name`, `case_name_short`, `docket_number` — display strings.
- `nature_of_suit`, `cause`, `jury_demand`, `jurisdiction_type` — case-type
  signals used to bucket into taxonomy.
- `appellate_fee_status`, `appellate_case_type_information` — appellate-specific.
- `appeal_from_str`, `assigned_to_str`, `panel_str` — panel/lineage strings.

Missing values are empty strings.

## Data provenance

- **CourtListener BULK bucket** — snapshot pair
  `dockets-2024-12-31.csv.bz2` (pre-boundary train partition) +
  `dockets-2026-06-30.csv.bz2` (post-boundary test partition, judge-side only)
  via `storage.courtlistener.com/bulk-data/{table}-{YYYY-MM-DD}.csv.bz2`.
- **License** — CC PD Mark 1.0 (public domain, free of known copyright
  restrictions) per CARRIERS.md:37.
- **User-Agent for fetch** — `FORGE tanmaytushar21@gmail.com`.

## Constraints

- Each `case_id` in `test_case_ids.json` MUST have a corresponding entry in
  your `per_case` list.
- Each `court_id` MUST be one of `{ca1..ca11, cadc, cafc}`.
- Each `case_type_bucket` MUST be one of `{civil_general, criminal,
  prisoner_petition, administrative_agency, immigration, labor_erisa,
  ip_patent, tax, other}`.
- Each `regime_label` MUST be one of `{low_complexity, moderate_complexity,
  elevated_complexity, backlog_pressure}`.
- Each `stall_probability` and `self_reported_certainty` MUST be on `[0, 1]`.
- **No future data.** For a test case, your solver may read only pre-boundary
  data (date_filed ≤ 2024-12-31 for training features). Do not read
  post-boundary docket entries.
- **No hindsight on test targets.** The `dockets_test.csv` (input-only at
  judge time) contains realized date_terminated but the reference solver's
  training pipeline extracts only pre-boundary features; grading uses hidden
  `true_disposition_days.json` + `true_stall_flags.json` labels.
- **No network.** All computation is offline.
- **No forbidden data sources.** Do not pull from CourtListener REST API
  (auth-walled per CARRIERS.md:37), Yahoo, Kaggle, Bloomberg, direct BLS,
  `hmmlearn`, SP500, VIXCLS, Stooq, NCUA, CRSP, per-CUSIP prices,
  per-case-outcome sources, or any commercial data vendor.
- **Per-observation compute budget.** Full backtest (~2500-5000 test cases)
  MUST complete in ≤ 30 minutes on the agent hardware.

## Final Deliverables

Submit exactly three files to `/home/workspace/`:

- `appellate_timing.py` — a runnable Python script supporting these CLI modes:
    - `python3 appellate_timing.py --train <input_dir> <state_json>`
    - `python3 appellate_timing.py --backtest <input_dir> <state_json> <output_json>`
- `requirements.txt` — dependency list.
- `timing_results.json` — the JSON artifact keyed by CourtListener docket id
  with the schema documented above.

## Special Notes

1. **Continuous-target design bypasses prior CourtListener kills.**
   Time-to-disposition is continuous non-sparse; trivial-affirm baselines
   from outcome-prediction (kill S34) do not exist here, and circuit is an
   expected feature (bypasses the sort-by-court leak class from
   authority-influence kill S41).
2. **Circuit-procedural-complexity regime is the primary signal-formation
   axis.** The 4-state regime is inferred from raw docket-entry cadence +
   case-name-length proxy + panel-composition-availability across
   pre-boundary training data, without hindsight regime labels.
3. **Cross-month stability is intentional.** Predicting well in just one
   test month is not enough — the L8 lane penalizes single-month lucky calls
   with variance-adjusted scoring across the 19 test months.
4. **PACER/RECAP coverage gap.** Pre-2018 appellate cases are undercovered
   in RECAP volunteer uploads and biased toward controversial cases;
   training window 2018-01-01 forward avoids this gap. Coverage still varies
   across circuits (ca9 largest, cafc smallest).
5. **Federal Circuit is specialized.** The Federal Circuit (cafc) handles
   only patent, federal-employee, and specialized cases; timing distribution
   differs materially from generalist regional circuits.

## Reproduction

The bundle was generated deterministically from
`seed/build/courtlistener_appellate_disposition_timing_calibration/grounding.yaml`
and `seed/build/courtlistener_appellate_disposition_timing_calibration/recompute.py`
in the Mephisto repository. Two independent recompute runs produce byte-identical
bundle contents (verified by SHA-256 comparison).
