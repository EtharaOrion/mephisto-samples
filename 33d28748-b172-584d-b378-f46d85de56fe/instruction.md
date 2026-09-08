## Title

CFTC Futures Cross-Market Positioning Book

## Task Requirements

You run the cross-asset positioning desk at a systematic macro fund. Every
week, when the CFTC publishes the Commitments of Traders report, you deliver a
positioning book covering 25 US-regulated futures contracts across energy,
metals, grains, livestock, rates, and FX. For the hidden 2025-01-07 through
2026-07-22 window (80 weekly COT publication dates - Tuesdays, with Monday
substitution on weeks following US federal holidays per CFTC schedule), your
system must produce per-market per-week:

- **commercial_net_direction** - `up` or `down`, direction of change in the
  commercial (hedger) net position from the current published week to the
  following week
- **magnitude_bucket** - one of `{large_increase, small_increase, small_decrease, large_decrease}`,
  size of the next-week change relative to boundary-anchored quartiles
- **crowding_regime** - one of `{crowded_long, neutral, crowded_short, extreme}`,
  where the current commercial net sits relative to the market's 3-year history
- **extreme_positioning_flag** - `true` iff the current commercial net is at
  or beyond the 10th or 90th percentile of its 3-year rolling window
- **direction_probability** - float in `[0, 1]`, your calibrated confidence that
  direction is `up`
- **self_reported_certainty** - float in `[0, 1]`, your certainty on this
  particular market for this particular week

You must also emit `self_reported_metrics` - your best estimate of each scoring
lane's realized value. An anti-fabrication gate recomputes these from your raw
predictions.

## Optimization Objectives

Your outputs are scored per (market, week) on 8 lanes. Total 100 points.

1. **L1 Commercial Direction (20 pts).** 2-class accuracy across all 25
   markets over all 80 weeks. Score = `20 * clip((acc - 0.45) / 0.20, 0, 1)`.
   Copy-last-week is a genuine baseline you must beat; the persistence trap
   is severe but not full-marks.
2. **L2 Magnitude Bucket (15 pts).** 4-class accuracy. Buckets are quartiles
   of boundary-anchored last-52 week-over-week changes; agent can reproduce.
   Full 15 at accuracy 0.55.
3. **L3 Crowding Regime (15 pts).** 4-class accuracy. Regime defined by
   boundary-anchored 3-year percentile buckets. Full 15 at accuracy 0.70.
4. **L4 Extreme Positioning Flag (10 pts).** F1 of extreme flag across all
   pairs. Full 10 at F1 0.70.
5. **L5 Cross-Market Rank Correlation (10 pts).** Mean Spearman rho per week
   between your 25-market probability ranking and realized direction. Full
   10 at mean rho 0.40.
6. **L6 Rate-Regime Adaptive (10 pts).** L1 accuracy restricted to weeks
   within 5 business days of a FOMC decision or CPI release date. Awards 50%
   default when fewer than 10 eligible weeks in graded window.
7. **L7 Confidence Calibration (5 pts).** Brier score over your
   `per_item_confidence` dict (`"<mid>:<week>" -> [0,1]`) versus realized
   L1 correctness: `pts = 5 * max(0, 1 - 2 * BS)`. BS=0 -> 5 pts, BS=0.25
   (random guessing) -> 2.5 pts, BS>=0.5 -> 0. Missing or malformed field
   -> 0. See `deliverables_guide.md` for the schema.
8. **L8 Cross-Quarter Stability (15 pts).** Compute L1 mean per calendar
   quarter (Q1-Q2-Q3-Q4 2025 + Q1-Q2 2026), then
   `15 * max(0, 1 - variance / 0.04)` scaled by mean accuracy. Penalizes
   solvers that spike one quarter and collapse on others.

## Benchmark composition

- **Copy-last-week baseline.** Direction = previous week's realized direction.
  A real baseline you must beat; measurably above chance but far below full marks.
- **Uniform-up baseline.** Direction = `up` for all markets, all weeks.
  Near the directional base rate on L1; other lanes score near zero.
- **Random-classification baseline.** Random 4-class regime and magnitude.
  L2 ~0.25, L3 ~0.25.

The persistence trap is severe: weekly commercial net autocorrelation is
above 0.90. Scoring is on realized next-week direction (not on level
forecast accuracy), so copy-yesterday cannot exploit persistence at inflection
points. It IS a beatable baseline, not a trivial baseline.

## Provided Data

All files below live in `/home/workspace/attachments/` and are symlinked into
`/home/workspace/` at container start.

| File | Format | Description |
| --- | --- | --- |
| `attachments/deliverables_guide.md` | markdown | Output schema + submission conventions |
| `attachments/cftc_book_lib.py` | Python | Scoring library (identical to judge copy) |
| `attachments/cot_history_train.csv` | CSV | CFTC COT weekly training data 2022-01 to 2024-12 |
| `attachments/markets_universe.csv` | CSV | 25-market universe with CFTC codes |
| `attachments/macro_train.csv` | CSV | FRED DFF/IORB/DGS/T10Y2Y through 2024-12-31 |
| `attachments/macro_calendar.csv` | CSV | FOMC decisions + CPI releases 2025-2026 (public schedule) |
| `attachments/requirements.txt` | text | Baseline deps (numpy, pandas only) |

## Data schema

- `cot_history_train.csv` columns: `market_id, week_ending, code, comm_long, comm_short, noncomm_long, noncomm_short, open_interest, change_in_comm_long, change_in_comm_short, traders_tot`
- `markets_universe.csv` columns: `market_id, cftc_code, name`
- `macro_train.csv` columns: `date, series, value`  (long format)
- `macro_calendar.csv` columns: `event_type, date` where event_type in `{FOMC, CPI}`

## Data provenance

- **CFTC** COT Legacy Futures-Only via `publicreporting.cftc.gov/resource/6dca-aqww.json`
- **FRED** macro series via `fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`

All US Government public domain, no copyright, license-clean.

## Constraints

- Each `commercial_net_direction` MUST be one of `{up, down}`.
- Each `magnitude_bucket` MUST be one of `{large_increase, small_increase, small_decrease, large_decrease}`.
- Each `crowding_regime` MUST be one of `{crowded_long, neutral, crowded_short, extreme}`.
- `extreme_positioning_flag` MUST be `true` or `false`.
- `direction_probability` and `self_reported_certainty` MUST be floats in `[0, 1]`.
- **No future data.** For week_ending D, use only COT data with report date strictly before D.
- **No network.** All computation is offline.
- **No forbidden sources.** Do not pull from Yahoo, Bloomberg, Quandl, Kaggle, Stooq, VIXCLS, or any commercial data vendor.
- **Compute budget.** Full backtest (approximately 2,000 pairs) MUST complete in <= 30 minutes.

## Final Deliverables

Submit exactly three files to `/home/workspace/`:

- `cftc_positioning.py` - runnable Python with:
  - `python3 cftc_positioning.py --train <input_dir> <state_json>` (fit)
  - `python3 cftc_positioning.py --backtest <input_dir> <state_json> <output_json>` (predict)
- `requirements.txt` - dependency list
- `positioning_results.json` - full deliverable per output schema in deliverables_guide.md

## Special Notes

1. **Persistence trap.** Weekly commercial net autocorrelation is above 0.90.
   Copy-last-week is a real baseline but does not full-mark any lane.
   Scoring is on realized next-week direction, so persistence alone does not
   full-mark any lane, but it IS a non-trivial baseline.
2. **Boundary-anchored statistics.** Magnitude bucket thresholds (L2) and
   crowding regime percentiles (L3, L4) are computed from training data
   only. Both the agent and the judge compute them with identical logic
   via `cftc_book_lib.compute_boundary_stats`. Reproduce the same values
   from `cot_history_train.csv`.
3. **Macro calendar is public.** FOMC + CPI dates for 2025-2026 are provided
   in `macro_calendar.csv` from Federal Reserve and BLS public announcements.
4. **Cross-quarter stability matters (L8).** Overfitting one quarter and
   collapsing on others is penalized by variance-adjusted scoring.

## Reproduction

The bundle was generated deterministically. Two independent recompute
runs produce byte-identical bundle contents (verified by SHA-256).
