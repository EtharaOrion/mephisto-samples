# e5d63160-7e3a-5d55-bab1-a887c9e97be3

Build a forward-looking regulatory-capital projection system for the full population of US
FDIC-insured commercial banks (~4,000 active institutions). For each 2025 quarterly reporting
date the system projects per-institution regulatory capital ratios (CET1, Tier-1 risk-based,
Tier-1 leverage, total risk-based), earnings metrics (NIM, ROA, ROE), asset-quality metrics
(nonperforming assets, net charge-offs, loan-loss reserves), quarterly asset and deposit growth
rates, and a categorical PCA capital-adequacy zone per 12 CFR § 6.4. Grading is against the
realized 2025 quarterly call-report outcomes across all held-out institution-quarter
observations.

## System requirements

Four components are mandatory:

- **Historical panel model** - reads the pre-2025 FDIC quarterly panel (~108,000
  institution-quarter records, 24 quarters 2019Q1-2024Q4, ~4,500 institutions) and learns
  institution-specific plus industry-wide trajectories for each target metric.
- **Macro-context conditioner** - reads daily FRED anchors (DGS10, DFF, T10Y2Y, UNRATE, GDPC1)
  up to each quarter-end and adjusts projections to the prevailing macro cycle; cycle labels
  are hidden.
- **Cross-sectional projector** - per 2025 institution-quarter (CERT + REPDTE), emits the
  metric projections, PCA-zone classification, growth rates, and a size-bucket label
  (community / mid / regional / large).
- **Backtest harness** - `python3 bank_capital_projection.py --backtest --data <hidden_csv>
  --macro <hidden_macro_csv> --institutions <test_institutions.json> --state
  reference_state.json --output projection_results.json`, invoked once by the judge against
  the full held-out 2025 panel.

## Scoring

Eight lanes per institution-quarter, aggregated across the panel:

| Lane | Points | Measures |
|---|---|---|
| 1 | 25 | capital-ratio MAE across the four ratios (full at <= 0.4 pp, zero at >= 3.5 pp) |
| 2 | 15 | earnings MAPE across NIM + ROA + ROE (full at <= 10%, zero at >= 50%) |
| 3 | 15 | tail-risk MAE on NPA + net charge-off ratios (full at <= 0.10 pp, zero at >= 1.0 pp) |
| 4 | 10 | 5-zone PCA classification accuracy (full at >= 80%, zero at <= 20%) |
| 5 | 10 | asset-growth MAE (full at <= 0.010, zero at >= 0.080) |
| 6 | 10 | deposit-growth MAE (full at <= 0.012, zero at >= 0.080) |
| 7 | 5 | anti-fabrication: judge-recomputed metrics vs `self_reported_metrics` |
| 8 | 10 | cross-size-bucket stability: variance of the capital lane across the four buckets |

A **PCA-zone-transition detection bonus (+10)** rewards correct identification of hidden 2025
quarter-over-quarter zone transitions on stressed institutions within 1-quarter tolerance,
saturating at 3+ matches. Anti-fabrication deviations beyond the stated tolerances zero lane 7
and the capital-ratio and earnings lanes for the whole cycle, so honest self-reporting is
structurally enforced.

Three informational baselines frame the task - predict-last-quarter, size-bucket mean, and
linear extrapolation - but scoring is on absolute performance.

## Constraints

No future data (at quarter-end `t`, only data dated `t - 1` or earlier is readable), no
network, no cross-directory reads: training attachments are physically separated from the
held-out test panel, and the backtest reads exclusively the paths passed on its CLI flags.
Per-observation wall time <= 0.5 s; full-cycle backtest <= 45 minutes. All source data is
US Government public domain (FDIC BankFind + FRED).

## Layout

```
task.toml                    task contract; work and judge images pinned by digest
instruction.md               agent-facing specification: metrics, lanes, harness CLI
environment/                 work image context and pre-2025 training attachments
tests/                       judge image context and held-out 2025 truth
solution/                    private oracle tree for the task
trajectory/                  recorded agent run against the shipped judge
```
