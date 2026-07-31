## Title

FDIC Bank Capital Projection Book

## Task Requirements

You are the lead regulatory-capital-risk quant at a US bank supervisory advisory desk. Every quarter your team must produce forward-looking projections of key capital, earnings, and asset-quality metrics for the full population of US FDIC-insured commercial banks (~4,000 active institutions). Your projections drive stress-test dashboards, peer-comparison reports, and early-warning alerts for institutions drifting toward regulatory capital-adequacy thresholds. Your job is to build a system that, for any 2025 quarterly reporting date (2025-03-31, 2025-06-30, 2025-09-30, 2025-12-31), generates per-institution forward projections for:

- **Regulatory capital ratios**: CET1 (`IDT1CER`), Tier-1 risk-based (`IDT1RWAJR`), Tier-1 leverage (`RBC1AAJ`), total risk-based capital (`RBCRWAJ`).
- **Earnings metrics**: net interest margin (`NIMYQ`), return on assets (`ROAQ`), return on equity (`ROEQ`).
- **Asset-quality metrics**: nonperforming assets to assets (`NPERFV`), net charge-offs to loans (`NCLNLSR`), loan-loss reserve ratio (`LNATRESR`).
- **PCA capital-adequacy zone**: categorical label from `{well_capitalized, adequately_capitalized, undercapitalized, significantly_under, critically_under}` per 12 CFR § 6.4.
- **Growth-rate projections**: quarterly asset growth and domestic deposit growth.

The system MUST include:

1. **Historical panel model.** A module that reads the pre-2025 FDIC quarterly panel (~108,000 institution-quarter records across 24 quarters and ~4,500 institutions) and learns institution-specific + industry-wide trajectories for each target metric.
2. **Macro-context conditioner.** A module that reads daily FRED macro anchors (`DGS10`, `DFF`, `T10Y2Y`, `UNRATE`, `GDPC1`) up to each quarter-end and adjusts the projection to the prevailing macro cycle. Cycle labels are hidden.
3. **Cross-sectional projector.** For each 2025 institution-quarter observation (identified by `CERT` + `REPDTE`), produce the metric projections + PCA-zone classification + growth-rate projections, plus per-observation `size_bucket` label (`community` / `mid` / `regional` / `large`).
4. **Backtest harness.** The system MUST support invocation as `python3 bank_capital_projection.py --backtest --data <hidden_csv> --macro <hidden_macro_csv> --institutions <test_institutions.json> --state reference_state.json --output projection_results.json`. The judge invokes your script once against the full held-out 2025 panel.

## Optimization Objectives (in priority order)

Your projections are scored per institution-quarter on eight lanes, then aggregated across the full 2025 panel with a cross-size-bucket stability penalty and a PCA-zone-transition detection bonus.

1. **Capital-ratio projection accuracy (25 pts).** Mean absolute error (in percentage points) across the four capital ratios (CET1 + Tier-1 risk-based + Tier-1 leverage + total risk-based). Full marks: MAE ≤ 0.4 pp. Zero: MAE ≥ 3.5 pp.
2. **Earnings projection accuracy (15 pts).** Mean absolute percentage error across NIM + ROA + ROE. Full marks: MAPE ≤ 10%. Zero: MAPE ≥ 50%.
3. **Tail-risk control (15 pts).** Mean absolute error (percentage points) across nonperforming-assets ratio + net charge-off ratio. Full marks: MAE ≤ 0.10 pp. Zero: MAE ≥ 1.0 pp.
4. **PCA-zone classification accuracy (10 pts).** Categorical accuracy on the 5-zone PCA capital-adequacy classification per institution-quarter. Full marks: accuracy ≥ 80%. Zero: accuracy ≤ 20%.
5. **Asset-growth projection (10 pts).** Mean absolute error on quarterly asset-growth rate. Full marks: MAE ≤ 0.010. Zero: MAE ≥ 0.080.
6. **Deposit-stability projection (10 pts).** Mean absolute error on domestic-deposit growth rate. Full marks: MAE ≤ 0.012. Zero: MAE ≥ 0.080.
7. **Anti-fabrication integrity (5 pts).** The judge independently recomputes each per-institution-quarter metric from your projected values against the realized 2025 call-report outcomes and compares against your `self_reported_metrics` (MAE / MAPE / classification-accuracy roll-ups). Deviations beyond `capital_ratio_mae > 0.05 pp`, `earnings_mape > 0.02`, `tail_mae > 0.05 pp`, `asset_growth_mae > 0.010`, `deposit_growth_mae > 0.010`, or `pca_zone_accuracy > 0.10` zero this lane AND zero the capital-ratio and earnings lanes for the whole cycle.
8. **Cross-size-bucket stability (10 pts, aggregated).** Variance of the capital-ratio lane across the four size buckets. Low variance = high score; a single size class carrying the score is penalized.

**PCA-zone-transition detection bonus (+10 pts, aggregated).** If your `detected_pca_zone_events` correctly identify hidden 2025 quarter-over-quarter PCA-zone transitions on stressed institutions (defined in the judge ground truth) within a 1-quarter tolerance, your submission earns up to +10 bonus points; saturates at 3+ matches.

## Benchmark composition

- Predict-last-quarter baseline: use each institution's most-recent 2024Q4 reported values as the entire 2025 forecast.
- Predict-size-bucket-mean baseline: use per-size-bucket historical means as the constant forecast.
- Linear-extrapolation baseline: continue each institution's Q3-to-Q4 change into 2025.

Your submission is scored on absolute performance, not excess over these baselines; the baselines are informational.

## Provided Data and Materials

All files below live in the `attachments/` directory.

| File | Format | Description |
| --- | --- | --- |
| `attachments/financials_train.csv` | CSV (utf-8) | Pre-2025 FDIC BankFind Financials quarterly panel: CERT, NAME, STNAME, ZIP, ASSET, REPDTE, IDT1CER, IDT1RWAJR, RBC1AAJ, RBCRWAJ, TFRA, ROAQ, ROEQ, NIMYQ, NETINC, EQV, DEPDOM, NPERFV, LNATRESR, NCLNLSR, LNLSDEPR, INTINC, INTINCY, P3ASSET, LNLSNET. Covers 24 quarters 2019Q1 through 2024Q4 across all active insured commercial banks. ~108,000 institution-quarter rows. |
| `attachments/institutions_reference.csv` | CSV (utf-8) | FDIC BankFind Institutions metadata: CERT, NAME, STNAME, ZIP, ASSET, CHARTER, MUTUAL, INSAGNT1, STALP, BKCLASS, SUBCHAPS, OAKAR, OTSREGNM, REGAGNT, OFFDOM. ~4,255 active institutions as of 2026-07 snapshot. |
| `attachments/macro_indicators_train.csv` | CSV (utf-8) | Daily FRED macro anchors (DGS10, DFF, T10Y2Y, UNRATE, GDPC1) forward-filled across weekends and holidays, ending 2024-12-31. |
| `attachments/size_bucket_definitions.csv` | CSV (utf-8) | Reference table: bucket, asset_thousands_lo, asset_thousands_hi, description. |
| `attachments/pca_zone_thresholds.csv` | CSV (utf-8) | Reference table: zone, total_rbc_pct_ge, tier1_rwa_pct_ge, tier1_leverage_pct_ge, regulatory_reference. (12 CFR § 6.4 constants.) |
| `attachments/train_period.txt` | text | Two dates comma-separated. Use this window to fit your models. |
| `attachments/valid_period.txt` | text | Two dates comma-separated. Reserve for hyperparameter selection / strategy validation. Iterative refinement is allowed within this window. |
| `attachments/deliverables_guide.md` | markdown | JSON schema of `projection_results.json` + submission conventions. |
| `attachments/requirements.txt` | text | Python package dependencies you MAY install. |

## Constraints

- Each `predicted_metrics` sub-dict MUST include all of `IDT1CER`, `IDT1RWAJR`, `RBC1AAJ`, `RBCRWAJ`, `ROAQ`, `ROEQ`, `NIMYQ`, `NPERFV`, `NCLNLSR`, `LNATRESR`, `EQV`, `LNLSDEPR` as finite floats.
- `predicted_pca_zone` MUST be one of the five 12-CFR-§-6.4 categorical labels.
- `predicted_asset_growth_rate` and `predicted_deposit_growth_rate` MUST be finite floats (dimensionless quarterly rates).
- No future data. At quarter-end date `t`, your solver may only read data with `date ≤ t − 1` (macro anchors at the day before the reporting date).
- No network. All computation is offline.
- No cross-directory reads. Training data (`attachments/`) is physically separated from held-out test data. Your `--backtest` invocation reads exclusively the paths passed on `--data`, `--macro`, `--institutions`, and `--state`.
- Per-observation backtest wall time: ≤ 0.5 seconds; total backtest wall time over the full test cycle: ≤ 45 minutes.

## Final Deliverables

- `bank_capital_projection.py` — a runnable Python script that accepts:
  - `--train --data <train_csv> --macro <macro_csv> --state <state_json>` (fits on training data, writes a persistent state artifact)
  - `--backtest --data <test_csv> --macro <macro_csv> --institutions <institutions_json> --state <state_json> --output <projection_results.json>` (reads state, iterates the 2025 panel, writes projections)
- `requirements.txt` — dependency list.
- `projection_results.json` — the JSON produced by `--backtest`. Schema is documented in `attachments/deliverables_guide.md`.

## Special Notes

1. The hidden 2025 quarterly cycle includes at least one PCA-zone transition on a stressed institution (institution drops from `well_capitalized` to `adequately_capitalized` or lower between reporting quarters). If your `detected_pca_zone_events` list flags a transition within 1 quarter of the true event and correctly identifies the CERT, your submission earns up to +10 bonus points (saturates at 3 matches). The detection mechanism MUST be a general data-driven rule (metric-trajectory threshold crossing), not CERT-hardcoding.
2. The training period covers Fed policy full cycle (2019 mid-hiking, 2020 emergency cutting, zero-lower-bound, 2022-2024 hiking back to restrictive) plus COVID-19 credit stress. Your system must remain robust across all regimes.
3. Data authenticity requirement. All values in `projection_results.json` must genuinely reflect execution. The judge independently recomputes each per-institution-quarter metric from your projected values against realized 2025 call-report outcomes and compares against your `self_reported_metrics`. Deviations beyond tolerance zero the anti-fabrication lane AND zero the capital-ratio and earnings lanes. Fabricated outputs have caused entire-cycle disqualification in prior evaluations.
4. Institution heterogeneity is intentional. Community banks (<$1B), mid-size ($1B-$10B), regional ($10B-$100B), and large / SIFI banks (>$100B) have fundamentally different capital dynamics — a solver that hyper-fits large-bank behavior while ignoring community-bank dynamics will lose the cross-size-bucket stability lane. Treat each size class with an appropriate model.
5. Regulatory PCA thresholds (12 CFR § 6.4) are HARD boundaries. Your projections should respect these thresholds as classification decision surfaces, not smooth-through them.
6. At judge time, `bank_capital_projection.py` is executed in an isolated evaluation directory. Hidden test data is passed via CLI paths; training `attachments/` are NOT re-attached. Your code MUST load fitted state exclusively from `--state <path>`.

## Task Input Description

The following input files are provided with the task, all located in the `attachments/` directory:

| File | Format | Description |
| --- | --- | --- |
| `attachments/financials_train.csv` | `.csv`, `utf-8` | Pre-2025 quarterly FDIC panel. |
| `attachments/institutions_reference.csv` | `.csv`, `utf-8` | FDIC BankFind Institutions metadata. |
| `attachments/macro_indicators_train.csv` | `.csv`, `utf-8` | Daily FRED macro anchors up to 2024-12-31. |
| `attachments/size_bucket_definitions.csv` | `.csv`, `utf-8` | Size-class definitions. |
| `attachments/pca_zone_thresholds.csv` | `.csv`, `utf-8` | 12 CFR § 6.4 PCA capital-adequacy thresholds. |
| `attachments/train_period.txt` | `.txt`, `utf-8` | Training period, format: `YYYY-MM-DD,YYYY-MM-DD`. |
| `attachments/valid_period.txt` | `.txt`, `utf-8` | Validation period, format: `YYYY-MM-DD,YYYY-MM-DD`. |

Reference document: `attachments/deliverables_guide.md`.

## Deliverable Requirements

- `bank_capital_projection.py` | Python source file
- `requirements.txt` | plain text
- `projection_results.json` | JSON (per-cycle output produced by `--backtest`)
