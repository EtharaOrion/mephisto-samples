## Iterative Evaluation Mode

You are working with iterative test feedback. After implementing code, you can submit your work for evaluation at any time to see which tests pass and which fail, then iterate based on the results.

### How to Test Your Code

- Run `sforge-submit` to submit your current code for evaluation. It will package the files, send them to the judge server, and return results showing score, pass rate, and a summary of findings.
- Run `sforge-submit --details` to submit and see detailed per-test results.
- Run `sforge-submit --list` to view all previous submissions and their scores for this run.

You should use these regularly to check your progress and identify issues.

### Submitted Files

Only the following paths are submitted for evaluation: `curve_positioning.py`, `requirements.txt`, `positioning_results.json`

**Keep these files in a compilable/runnable state at all times.** A background process periodically auto-evaluates your code — if the submitted files are broken, incomplete, or contain syntax errors at that moment, the auto-evaluation will fail. Write changes to disk promptly and ensure the submitted files always represent your current best solution.

### Submission Limits

- You have a **limited number of submissions (300 total)**. Plan carefully and validate locally before submitting.
- There is a **minimum interval of 120s** between submissions.

### Network Environment

**This environment has NO internet access.** Only the judge server and the AI API are reachable. Do not attempt to download packages, fetch remote resources, or access external URLs — all dependencies are pre-installed in the workspace.

### Strategy

- **Implement incrementally**: Complete one module/project at a time
- **Read test feedback carefully**: Failed test names often hint at what's broken
- **Iterate**: Fix failing tests based on the feedback, then submit again

### Scoring

- Your **best score** across all submissions is your final score
- You don't lose points for failed attempts — experimentation is encouraged

---

## Title

Dynamic US Treasury Yield-Curve Positioning Book

## Task Requirements

You are the lead strategist of a fixed-income relative-value fund. Your desk runs a book of directional and butterfly positions across US Treasury tenors (2Y / 5Y / 10Y / 30Y) sized by DV01 (dollar duration per basis point). The portfolio manager has asked you to build a positioning system that (a) reads the current shape of the daily Treasury curve, (b) adapts allocation to the prevailing macro state, (c) generates a daily target position vector under an institutional constraint stack, and (d) survives repeated re-execution on unseen held-out windows without hindsight leakage.

Traditional fixed-income desks that pick a single duration view and hold it through a regime change get run over. Your task is to build a positioning system that dynamically shrinks or extends exposure by tenor, respects tenor-specific DV01 caps and butterfly limits, and is disciplined about turnover so that transaction costs do not consume the carry+rolldown edge.

The system MUST include:

1. **Curve model.** A module that reads the daily US Treasury yield curve (thirteen tenor points, 1M through 30Y) and extracts a compact representation of level / slope / curvature. It MUST be fit on training data and MUST NOT read any data from beyond the current decision boundary at runtime.
2. **Regime-aware position generator.** A module that maps the current curve state plus the current macro state (2Y and 10Y yield levels, 10Y-2Y spread, Fed funds rate, USD/EUR spot) to a target DV01 allocation across the 2Y / 5Y / 10Y / 30Y buckets and to two butterfly exposures (2s5s10s and 5s10s30s). It MUST detect the prevailing macro state without receiving explicit state labels — labels are hidden from the agent at all times.
3. **Execution-cost-aware rebalancer.** A module that computes the day-to-day position adjustment under a turnover penalty. The rebalancer should trade only when expected carry + rolldown materially exceeds transaction cost (0.02% per rebalance on each traded notional).
4. **Multi-window backtest harness.** The system MUST support invocation as `python3 curve_positioning.py --backtest --window-start=YYYY-MM-DD --window-end=YYYY-MM-DD`, producing a `positioning_results.json` for that window. The judge will invoke your script independently on each of many held-out 3-week windows.

## Optimization Objectives (in priority order)

Your positioning book is scored per window on eight lanes, then aggregated across all held-out windows with a cross-window stability penalty and a regime-shift detection bonus.

1. **Risk-adjusted return (25 pts).** Target annualized Sharpe ratio ≥ 1.0 per window; full marks at ≥ 2.0. Curve trading Sharpe is thinner than equity — 2.0 is the institutional-frontier cap.
2. **Directional accuracy (20 pts).** Hit rate on curve steepen / flatten calls. Target ≥ 55%; full marks at ≥ 65%. A window in which you correctly predicted the direction of 10Y-2Y spread change scores full for this lane.
3. **Duration precision (15 pts).** RMSE of realized portfolio duration versus target duration, scaled by DV01 budget. Target RMSE ≤ 0.15 years; full marks at ≤ 0.05 years.
4. **Convexity capture (15 pts).** Realized butterfly P&L versus benchmark equal-DV01 exposure. Positive convexity capture on ≥ 60% of windows earns full marks.
5. **Drawdown control (10 pts).** Target max within-window drawdown ≤ 6%; full marks at ≤ 3%. Exceeding 10% zeros the lane.
6. **Turnover discipline (5 pts).** Annualized one-way turnover target 60%–100%; full marks in-band. Outside this band scores 0 for this lane.
7. **Anti-fabrication integrity (5 pts).** The judge independently recomputes NAV, DV01, and turnover from your raw daily positions and the realized curve. Deviations of more than 0.2 Sharpe or 2 percentage points of drawdown or 50% of turnover zero out this lane and additionally zero the primary lane for that window.
8. **Cross-window stability (5 pts, aggregated).** Applied after per-window scores are computed: variance of per-window primary-lane scores versus a variance baseline. Low variance earns full marks; a single lucky window carrying the score is penalized.

**Regime-shift bonus (+10 pts, aggregated).** If your regime-detection component identifies a genuine regime shift (defined in the held-out test data — the answer key is not shown to you) with a curve-state change of ≥ 25 bps at any two consecutive tenors within 3 trading days of the true event, your book receives a +10 bonus. This must be a general detection mechanism, not date-hardcoding.

## Benchmark composition

Equal-DV01 allocation across 2Y, 5Y, 10Y, 30Y (25% of DV01 budget each). Your book is scored on excess carry+rolldown P&L over this benchmark per window.

## Provided Data and Materials

All files below live in the `attachments/` directory.

| File | Format | Description |
| --- | --- | --- |
| `attachments/treasury_curve_daily.csv` | CSV (utf-8) | Daily US Treasury yield curve 2010-01-01 through 2024-12-31. Columns: `Date, 1 Mo, 2 Mo, 3 Mo, 6 Mo, 1 Yr, 2 Yr, 3 Yr, 5 Yr, 7 Yr, 10 Yr, 20 Yr, 30 Yr`. Yields in percent (e.g. `4.25` = 4.25%). Missing tenors coded as blank. |
| `attachments/macro_indicators.csv` | CSV (utf-8) | Daily macro indicators 2010-01-01 through 2024-12-31. Columns: `date, DGS10, DGS2, DFF, T10Y2Y, DEXUSEU`. All series from the Federal Reserve Bank of St. Louis clean-series set. Values forward-filled across weekends and holidays. |
| `attachments/tenor_info.csv` | CSV | Tenor codes, maturity buckets, DV01 conventions per $100 notional, rebalance bucket, liquidity tier. |
| `attachments/train_period.txt` | text | `2010-01-01,2023-12-31`. Use this window to fit your curve model and calibrate any macro-adaptive component. |
| `attachments/valid_period.txt` | text | `2024-01-01,2024-12-31`. Use this window for hyperparameter selection and strategy validation. Iterative refinement is allowed within this window. |
| `attachments/deliverables_guide.docx` | docx | Positioning-vector schema + JSON output specification. |
| `attachments/requirements.txt` | text | Python package dependencies you MAY install. |

## Constraints

- Single-tenor DV01 cap: 25% of DV01 budget.
- Butterfly exposure cap: 30% of DV01 budget, split across the two butterflies.
- Total leverage cap: |gross DV01| / DV01 budget ≤ 2.0.
- Transaction cost: 0.02% per rebalance on each traded notional. Deducted from realized P&L.
- Rebalance windowing: minimum interval 3 trading days between rebalances.
- No future data. At decision date `t`, your solver may only read data with `date ≤ t`.
- No network. All computation is offline.
- No cross-directory reads. Training/validation data (`attachments/`) is physically separated from held-out test data. Your `--backtest` invocation is given a window range and must operate exclusively on data within `attachments/` plus what the judge injects at invocation time.
- Per-window `--backtest` runtime ≤ 5 minutes.

## Final Deliverables

- `curve_positioning.py` — a directly runnable Python script that accepts `--train` (fits on `attachments/` data, writes a persistent state artifact `reference_state.json`) and `--backtest --window-start=YYYY-MM-DD --window-end=YYYY-MM-DD` (reads `reference_state.json` + the window's data, writes `positioning_results.json` to stdout or to `positioning_results.json`).
- `requirements.txt` — dependency list.
- `positioning_results.json` — generated by your script when invoked in `--backtest` mode. Schema:

```
{
  "window_start": "YYYY-MM-DD",
  "window_end":   "YYYY-MM-DD",
  "daily_positions": [
    {
      "date": "YYYY-MM-DD",
      "dv01_by_tenor": {"2Y": <float>, "5Y": <float>, "10Y": <float>, "30Y": <float>},
      "butterfly_exposure": {"2s5s10s": <float>, "5s10s30s": <float>},
      "notional_by_tenor": {"2Y": <float>, "5Y": <float>, "10Y": <float>, "30Y": <float>}
    },
    ...
  ],
  "self_reported_metrics": {
    "sharpe": <float>,
    "max_drawdown": <float>,
    "hit_rate_flatten_steepen": <float>,
    "duration_precision_rmse": <float>,
    "convexity_capture_pnl": <float>,
    "turnover_annualized": <float>
  },
  "rebalance_history": [
    {"date": "YYYY-MM-DD", "trigger": "scheduled|regime_change|initial", "notes": "..."}
  ]
}
```

## Special Notes

1. The held-out test set contains at least one regime-shift event. If your regime-detection component correctly identifies a curve-state change of ≥ 25 bps at any two consecutive tenors within 3 trading days of the event, your book earns +10 bonus points. The detection mechanism MUST be a general method (a data-driven detector), not a date-hardcoded rule.
2. Training data covers zero-rate regime (2010-2015), taper tantrum (2013), rate-hike cycle (2015-2019), COVID emergency easing (2020-2021), rapid hiking cycle (2022-2023), and disinflation levelling (2024). Your positioning system must remain robust across all regimes.
3. At judge time, your `curve_positioning.py` is executed in an isolated evaluation directory. Held-out test data is injected under `/home/workspace/` for each window; training/validation data is NOT provided at judge time. Your code must switch modes explicitly on `--backtest` argument.
4. The judge invokes your script per window with explicit `--window-start` and `--window-end` arguments. Your script MUST honor these arguments and produce a `positioning_results.json` covering exactly that window.
5. Data authenticity requirement. All values in your `positioning_results.json` must genuinely reflect execution. The judge independently recomputes NAV, DV01, and turnover from your raw positions and compares against your self-reported metrics. Deviations trigger anti-fabrication gates that zero out that window's score. Fabricated data has led to entire-window disqualification in prior evaluations.

## Task Input Description

The following input files are provided with the task, all located in the `attachments/` directory:

| File | Format | Description |
| --- | --- | --- |
| `attachments/treasury_curve_daily.csv` | `.csv`, `utf-8` | Daily Treasury yield curve, 2010-01-01 through 2024-12-31. |
| `attachments/macro_indicators.csv` | `.csv`, `utf-8` | Daily FRED clean-series macro indicators (DGS10, DGS2, DFF, T10Y2Y, DEXUSEU), 2010-01-01 through 2024-12-31. |
| `attachments/tenor_info.csv` | `.csv`, `utf-8` | Tenor codes, maturity buckets, DV01 conventions. |
| `attachments/train_period.txt` | `.txt`, `utf-8` | Training period, format: `2010-01-01,2023-12-31`. |
| `attachments/valid_period.txt` | `.txt`, `utf-8` | Validation period, format: `2024-01-01,2024-12-31`. |

Reference document: `attachments/deliverables_guide.docx`.

## Deliverable Requirements

- `curve_positioning.py` | Python source file
- `requirements.txt` | plain text
- `positioning_results.json` | JSON (per-window output produced by `--backtest`)
