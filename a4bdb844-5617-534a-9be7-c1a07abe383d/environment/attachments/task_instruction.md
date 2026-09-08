## Title

CPI Nowcast + Positioning Book

## Task Requirements

You are the lead macro-rates quant at a global asset manager. Every month, your team must publish (a) forward nowcasts for the four headline US inflation prints released by BLS + BEA (headline CPI `CPIAUCSL`, core CPI `CPILFESL`, headline PCE `PCEPI`, core PCE `PCEPILFE`) and (b) a Treasury duration + breakeven-inflation positioning book for the 1-week window following each release. Your nowcasts drive the desk's forward inflation view; your positioning book determines the actual portfolio tilt.

Your job is to build a system that, for any 2025 reference month (2025-01 through 2025-12), generates per-series:

- **Nowcast**: predicted year-over-year inflation rate (percentage points) for the reference month's print.
- **Prediction interval**: [lo, hi] band capturing your uncertainty.
- **Positioning book**: signed exposures on `{duration_2y, duration_10y, breakeven_10y}` sized in unit-notional terms.
- **Detected policy regime**: label from `{cutting, holding, hiking}` inferred from observable Fed indicators.

The system MUST include:

1. **Historical monthly panel model.** A module that reads the pre-2025 FRED monthly panel (15 years, 2010-2024) of CPI + PCE + macro-supporting + Treasury-rates series and learns per-series trajectory dynamics.
2. **Macro-context conditioner.** A module that reads daily FRED macro anchors (`DGS10`, `DGS2`, `DFII10`, `DFF`, `T10Y2Y`, plus `PPIACO`, `PPIFIS`, `DCOILWTICO`, `HOUST`, `UNRATE`, `CES0500000003`) up to each reference month and conditions the nowcast on the prevailing macro cycle.
3. **Cross-series per-month projector.** For each 2025 reference month × series (48 hidden prints), produce the nowcast + prediction interval + regime label + positioning book, plus a `detected_fed_pivot_events` list.
4. **Backtest harness.** The system MUST support invocation as `python3 cpi_nowcast_book.py --backtest --data <cpi_csv> --macro <macro_csv> --rates <rates_csv> --prints <test_prints.json> --state reference_state.json --output nowcast_results.json`. The judge invokes your script once against the full held-out 2025 panel.

## Optimization Objectives (in priority order)

Your outputs are scored per print on eight lanes, then aggregated across the full 2025 panel with a cross-series stability penalty and a Fed-pivot detection bonus.

1. **Headline CPI nowcast accuracy (20 pts).** Mean absolute error (percentage points) between your predicted `CPIAUCSL` YoY and realized. Full marks: MAE ≤ 0.10 pp (10 bps). Zero: MAE ≥ 0.80 pp.
2. **Core CPI nowcast accuracy (15 pts).** MAE on `CPILFESL` YoY. Full marks: MAE ≤ 0.10 pp. Zero: MAE ≥ 0.60 pp.
3. **Headline PCE nowcast accuracy (15 pts).** MAE on `PCEPI` YoY. Full marks: MAE ≤ 0.10 pp. Zero: MAE ≥ 0.60 pp.
4. **Core PCE nowcast accuracy (10 pts).** MAE on `PCEPILFE` YoY. Full marks: MAE ≤ 0.10 pp. Zero: MAE ≥ 0.50 pp.
5. **Positioning-book PnL (15 pts).** Simulated 1-week post-print Treasury + breakeven PnL from your `positioning_book` positions against realized inflation surprise vs the naive year-ago-carry consensus. Sharpe cap 1.5 on realized monthly PnL series.
6. **Directional accuracy vs consensus (10 pts).** Fraction of prints where your nowcast has lower MAE than the naive year-ago-carry (`YoY at ref_month - 1`) baseline. Full marks: beat rate ≥ 0.65. Zero: beat rate ≤ 0.35.
7. **Anti-fabrication integrity (5 pts).** The judge independently recomputes each per-print MAE / PnL / beat-rate from your raw predictions against realized 2025 outcomes and compares against your `self_reported_metrics`. Deviations beyond `mae > 0.05 pp`, `positioning_pnl_sum > 0.020`, or `directional_beat_consensus_rate > 0.05` zero this lane AND zero the headline + core CPI lanes for the whole cycle.
8. **Cross-series stability (10 pts, aggregated).** Variance-and-mean of the four accuracy lanes (L1-L4) across `{CPIAUCSL, CPILFESL, PCEPI, PCEPILFE}`. A solver that hyper-fits one series while ignoring others is penalized.

**Fed-pivot detection bonus (+10 pts, aggregated).** If your `detected_fed_pivot_events` correctly identify hidden 2025 Fed policy pivots (defined in the judge ground truth) within a 1-month tolerance, your submission earns up to +10 bonus points; saturates at 3+ matches.

## Benchmark composition

- **Predict-last-month baseline**: predict this month's YoY = last month's YoY (naive year-ago-carry).
- **Predict-year-ago-YoY baseline**: predict this month's YoY = same month one year ago YoY.
- **Predict-training-mean baseline**: predict per-series historical mean YoY as constant.

Your submission is scored on absolute accuracy, not excess over these baselines; the baselines are informational.

## Provided Data and Materials

All files below live in the `attachments/` directory.

| File | Format | Description |
| --- | --- | --- |
| `attachments/cpi_train.csv` | CSV (utf-8) | Pre-2025 FRED monthly panel for the four inflation series: date, CPIAUCSL, CPILFESL, PCEPI, PCEPILFE. Covers 180 months, Jan-2010 through Dec-2024. |
| `attachments/macro_train.csv` | CSV (utf-8) | Pre-2025 FRED monthly supporting series: date, PPIACO (producer prices all commodities), PPIFIS (PPI final demand services), DCOILWTICO (WTI crude oil, resampled to month-end), HOUST (housing starts), UNRATE (unemployment rate), CES0500000003 (avg hourly earnings, private nonfarm). |
| `attachments/rates_train.csv` | CSV (utf-8) | Pre-2025 FRED Treasury + breakevens (daily, resampled to month-end): date, DGS10, DGS2, DFII10 (10-yr TIPS real yield), DFF (effective fed funds), T10Y2Y (10y-2y curve). |
| `attachments/train_period.txt` | text | Two dates comma-separated. Use this window to fit your models. |
| `attachments/valid_period.txt` | text | Two dates comma-separated. Reserve for hyperparameter selection / validation. Iterative refinement is allowed within this window. |
| `attachments/deliverables_guide.md` | markdown | JSON schema of `nowcast_results.json` + submission conventions. |
| `attachments/requirements.txt` | text | Python package dependencies you MAY install (numpy, pandas, scipy). |

## Constraints

- Each print's `predicted_yoy_pct` MUST be a finite float in percentage points (e.g., `2.85` for 2.85% YoY inflation).
- `prediction_interval` MUST be a 2-element list `[lo_pct, hi_pct]` with `lo <= hi`.
- `detected_regime` MUST be one of `{"cutting", "holding", "hiking"}`.
- `positioning_book` MUST contain finite floats for keys `duration_2y`, `duration_10y`, `breakeven_10y`; signed unit-notional exposures.
- **No future data.** For a print with `release_date=T`, your solver may only read data with `date <= T - 1 day`. Concretely, for a 2025-06 print (release date approximately mid-July), you may NOT read July 2025 CPI values.
- **No network.** All computation is offline.
- **No cross-directory reads.** Training data (`attachments/`) is physically separated from held-out test data. Your `--backtest` invocation reads exclusively the paths passed on `--data`, `--macro`, `--rates`, `--prints`, and `--state`.
- Per-print backtest wall time: ≤ 2 seconds; total backtest wall time over the full 2025 cycle: ≤ 30 minutes.

## Final Deliverables

- `cpi_nowcast_book.py` — a runnable Python script that accepts:
  - `--train --data <cpi_train_csv> --macro <macro_train_csv> --rates <rates_train_csv> --state <state_json>` (fits on training data, writes a persistent state artifact)
  - `--backtest --data <cpi_test_csv> --macro <macro_test_csv> --rates <rates_test_csv> --prints <test_prints_json> --state <state_json> --output <nowcast_results.json>` (reads state, iterates the 2025 panel, writes results)
- `requirements.txt` — dependency list.
- `nowcast_results.json` — the JSON produced by `--backtest`. Schema documented in `attachments/deliverables_guide.md`.

## Special Notes

1. The hidden 2025 monthly cycle includes at least one Fed policy pivot (transition among cutting / holding / hiking regimes). If your `detected_fed_pivot_events` list flags a transition within 1 month of the true event, your submission earns up to +10 bonus points (saturates at 3 matches). Detection MUST be a general data-driven rule (e.g., short-horizon change in effective-funds level or curve slope), not date-hardcoding.
2. The training period covers a full Fed policy cycle: 2010-2015 zero-lower-bound, 2015-2019 gradual hiking, 2020 emergency cutting, 2022-2023 aggressive hiking, 2024 initial cutting. Your system must remain robust across all regimes.
3. **Data authenticity requirement.** All values in `nowcast_results.json` must genuinely reflect execution. The judge independently recomputes each per-print MAE, positioning-book PnL, and directional beat rate from your raw predictions against realized 2025 outcomes and compares against your `self_reported_metrics`. Deviations beyond tolerance zero the anti-fabrication lane AND zero the headline + core CPI lanes. Fabricated outputs have caused entire-cycle disqualification in prior evaluations.
4. **Cross-series heterogeneity is intentional.** Headline CPI (energy-and-food inclusive), core CPI (excludes energy + food), headline PCE (BEA methodology + broader coverage than CPI), and core PCE (Fed's preferred inflation gauge) have fundamentally different transmission dynamics. A solver that fits one series well while ignoring the others will lose the cross-series stability lane. Treat each series with an appropriate model.
5. **Base-effect matters.** The year-over-year comparison shifts each month as the year-ago comp changes. A strong solver decomposes YoY into base-effect (year-ago-comp contribution, fully known) and sequential-change contribution (the actually-forecastable component).
6. At judge time, `cpi_nowcast_book.py` is executed in an isolated evaluation directory. Hidden test CSVs contain a 2024 lookback so the year-ago comparison is available; the scored prints are strictly the 48 hidden 2025 entries listed in `test_prints.json`. Your code MUST load fitted state exclusively from `--state <path>`.

## Task Input Description

The following input files are provided with the task, all located in the `attachments/` directory:

| File | Format | Description |
| --- | --- | --- |
| `attachments/cpi_train.csv` | `.csv`, `utf-8` | Monthly CPI + PCE panel 2010-2024. |
| `attachments/macro_train.csv` | `.csv`, `utf-8` | Monthly supporting macro series 2010-2024. |
| `attachments/rates_train.csv` | `.csv`, `utf-8` | Month-end Treasury + breakevens 2010-2024. |
| `attachments/train_period.txt` | `.txt`, `utf-8` | Training period, format: `YYYY-MM-DD,YYYY-MM-DD`. |
| `attachments/valid_period.txt` | `.txt`, `utf-8` | Validation period, format: `YYYY-MM-DD,YYYY-MM-DD`. |

Reference document: `attachments/deliverables_guide.md`.

## Deliverable Requirements

- `cpi_nowcast_book.py` | Python source file
- `requirements.txt` | plain text
- `nowcast_results.json` | JSON (per-cycle output produced by `--backtest`)
