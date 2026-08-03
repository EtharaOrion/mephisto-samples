## Iterative Evaluation Mode

You are working with iterative test feedback. After implementing code, you can submit your work for evaluation at any time to see which tests pass and which fail, then iterate based on the results.

### How to Test Your Code

- Run `sforge-submit` to submit your current code for evaluation. It will package the files, send them to the judge server, and return results showing score, pass rate, and a summary of findings.
- Run `sforge-submit --details` to submit and see detailed per-test results.
- Run `sforge-submit --list` to view all previous submissions and their scores for this run.

You should use these regularly to check your progress and identify issues.

### Submitted Files

Only the following paths are submitted for evaluation: `leverage_trajectory.py`, `requirements.txt`, `trajectory_results.json`

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

Cross-Sectional SEC Capital-Structure Trajectory Projection Book

## Task Requirements

You are the head of the quantitative-credit capital-structure desk at a
long/short US equity + credit fund. Every quarter, your desk publishes a
cross-sectional book on the top-1000 US SEC filers (ranked by Assets) that
consists of (a) a per-filer per-quarter composite capital-structure
trajectory score with peer-conditional normalization, (b) a three-class
refinancing-risk direction classification per filer per quarter with a
self-reported confidence, (c) an extreme-mover probability that the
observation falls in the top decile (best deleveragers) or bottom decile
(worst leverage-uppers) of composite trajectory rank, and (d) a per-quarter
positioning book — signed unit-exposure long/short weights across the
universe — sized with a rate-cycle overlay and turnover discipline.

Your job is to build a system that, for the hidden CY2025Q1-CY2026Q1 test
window (5 quarters x ~1000 filers = ~5,000 filer-quarter observations),
generates per filer-quarter:

- **Composite capital-structure trajectory score** — a scalar per filer-
  quarter aggregating multi-quarter rolling-window slopes on the leverage
  ratio (Total Liabilities / Assets), the net-debt-to-assets proxy, and the
  interest-coverage ratio, rank-transformed cross-sectionally.
- **Peer-conditional rank percentile** — the composite's percentile within
  the peer group after size-and-sector-adjacent normalization, expressed on
  [0.0, 1.0].
- **Global rank percentile** — the composite's percentile across the entire
  universe for the same quarter.
- **Refinancing-risk direction** — one of `{risk_up, neutral, risk_down}`
  reflecting the expected direction of refinancing pressure over the next
  four quarters given the prevailing rate-cycle overlay from FRED anchors
  (DGS10, DGS2, DFF, T10Y2Y) and the filer's own long-term-debt maturity
  proxy where reported.
- **Refinancing-risk confidence** — self-reported [0.0, 1.0] scalar over
  the direction call.
- **Extreme-mover probability** — [0.0, 1.0] probability that this filer-
  quarter falls in the top decile (best deleveragers) OR bottom decile
  (worst leverage-uppers) of realized composite trajectory rank.
- **Top-decile / bottom-decile flags** — binary indicators derived from the
  extreme-mover probability.
- **Position weight** — signed unit exposure (positive = long low-leverage
  or long deleveraging trajectory, negative = short high-leverage or short
  leveraging-up trajectory) sized for cross-quarter volatility, turnover
  discipline, and the prevailing rate cycle.

The system MUST include three internal components:

1. **Historical panel model.** Reads the pre-CY2025 SEC EDGAR XBRL panel
   (CY2018Q1-CY2024Q4, ~28,000 filer-quarters) plus the aligned FRED
   monthly rate/curve panel (DGS10, DGS2, DFF, T10Y2Y) and learns per-
   quarter cross-sectional rank transforms of the primary balance-sheet
   trajectory signals — leverage ratio, net-debt-to-assets, interest
   coverage — using multi-quarter rolling-window slopes. Aggregates the
   standardized slope signals into a single composite that has documented
   cross-sectional Spearman rank correlation with realized post-print
   capital-structure outcomes on the training window.
2. **Cross-quarter direction-and-extremes projector.** Reads a filer's own
   4-8 preceding quarterly prints plus the current-quarter balance-sheet
   signals and the prevailing rate-cycle anchors, and projects a three-
   class refinancing-risk direction call plus an extreme-mover probability
   with self-reported confidences.
3. **Backtest harness.** The system MUST support invocation as:
     `python3 leverage_trajectory.py --train <input_dir> <state_json>`
     `python3 leverage_trajectory.py --backtest <input_dir> <state_json> <output_json>`
   Where `<input_dir>` at your working turn holds `train/` and `test/`
   subdirectories containing the XBRL + universe + macro JSONL panels plus
   `test/test_filer_quarters.json` listing the `(cik, period)` pairs to
   predict. Fit your components on the training window, iterate the test
   panel, and emit `trajectory_results.json` alongside `leverage_trajectory.py`
   and `requirements.txt` in `/home/workspace/` before submission.

The judge does NOT invoke your Python at grade time — it reads your
`trajectory_results.json` as a static artifact and independently recomputes
each metric on the hidden test truth. Fabricated numbers are detected via
L7 anti-fabrication and zero the affected lane.

## Optimization Objectives (in priority order)

Your outputs are scored per-quarter on eight lanes, aggregated with a
cross-quarter stability lane and a leverage-cycle bonus lane.

1. **Composite trajectory rank correlation (20 pts).** Per-quarter Spearman
   rank correlation between your `composite_score` and the truth's
   capital-structure-derived post-print price-response proxy, averaged
   across the 5 test quarters. Full marks: IC >= 0.50. Zero: IC <= 0.00.
2. **Refinancing-risk direction (15 pts).** Three-class classification
   accuracy of your `refi_direction` (`risk_up` / `neutral` / `risk_down`)
   vs truth across all test filer-quarters. Full marks: accuracy = 1.00.
   Zero: accuracy <= 0.33 (three-class random baseline).
3. **Extreme-mover detection F1 (15 pts).** F1 of your
   `in_top_decile OR in_bottom_decile` flags vs truth (rare-event binary
   classification, 20% positive rate). Full marks: F1 = 1.00. Zero:
   F1 <= 0.10.
4. **Delta-liabilities growth ranking (10 pts).** Per-quarter Spearman IC
   between your `peer_rank_percentile` and truth's realized Delta-Liabilities
   over Assets YoY change. Full marks: IC >= 0.70. Zero: IC <= 0.00.
5. **Interest-coverage direction (10 pts, subset scoring).** Three-class
   direction accuracy (up / flat / down) of your composite's direction as a
   predictor of truth's realized YoY interest-coverage change, scored only
   on the subset (~21% of universe) where `InterestExpense` is reported.
   Full marks: accuracy >= 0.70. Zero: accuracy <= 0.33.
6. **Composite position PnL (10 pts).** Cross-quarter Sharpe ratio of your
   positioning book realized against truth's post-print response proxy,
   capped at 5.0 (positive-Sharpe-only anchor). Full marks: Sharpe >= 5.00.
   Zero: Sharpe <= 0.00.
7. **Anti-fabrication (5 pts).** The judge independently recomputes L1,
   L2, L3, L4, and L5 from your raw per-filer-quarter predictions against
   truth and compares against your `self_reported_metrics`. Deviation
   beyond ±0.15 on any of the five metrics zeros this lane (standalone,
   not cross-lane vetoing).
8. **Cross-quarter stability (10 pts, aggregated).** Awards up to 10 pts
   based on the mean per-quarter normalized performance across L1-L6,
   discounted by variance across the 5 test quarters. A solver that
   hyper-fits one quarter and misses the rest is penalized; copy-last-
   quarter is stable but low-mean.

**Leverage-cycle bonus (+10 pts, aggregated).** Awards up to +10 additive
points for detection precision of filers whose leverage trajectory turned
during the CY2025 rate-hike-to-cutting-cycle turning point (peak leverage
CY2024Q4-CY2025Q2 and deleveraging CY2025Q3-CY2026Q1, when refinancing
costs began to ease). Saturates at precision >= 0.85.

## Benchmark composition

- **Copy-last-quarter baseline.** Composite = previous quarter's composite
  for the same filer; refi direction = `neutral` fixed; position = 0. This
  is a genuine trivial baseline you must beat, not a shortcut. Because
  scoring is TRAJECTORY-SLOPE / rank-based / direction-based / PnL-based
  and NOT level-based, copy-last-quarter earns positive but non-full marks
  on the persistent lanes (L4 delta-liabilities growth ranking) and near-
  zero on the direction / PnL lanes.
- **Predict-consensus-neutral baseline.** Always predict `neutral`
  direction with 0.33 confidence, composite = 0, position = 0. Scores
  L2 at random-class accuracy, L1 / L4 / L6 near zero.
- **Random-classification baseline.** Composites uniformly random from
  training-window distribution, directions uniformly random. Scores near
  the anchor floors on every lane.

Your submission is scored on absolute quality against the anchors, not
excess over the baselines; the baselines are informational.

## Provided Data and Materials

All files below live in the `attachments/` directory and are symlinked to
`/home/workspace/` at container start (so both `train/...` and
`attachments/train/...` resolve to the same file).

| File | Format | Description |
| --- | --- | --- |
| `attachments/README.md` | markdown | Bundle overview, schema, and rules (this file's counterpart). |
| `attachments/deliverables_guide.md` | markdown | JSON schema of `trajectory_results.json` + submission conventions. |
| `attachments/requirements.txt` | text | Baseline Python dependencies (numpy, pandas) pre-installed at image build. |
| `attachments/train/xbrl.jsonl` | JSONL | CY2018Q1-CY2024Q4 XBRL balance-sheet + flow signals per filer-quarter (~28,000 obs). |
| `attachments/train/universe.jsonl` | JSONL | Top-1000 filers by Assets per training quarter with entry/exit flags. |
| `attachments/train/macro.jsonl` | JSONL | Monthly DGS10 + DGS2 + DFF + T10Y2Y aligned to the quarterly filer grid. |
| `attachments/test/xbrl.jsonl` | JSONL | CY2025Q1-CY2026Q1 XBRL balance-sheet + flow signals — INPUT-ONLY. Composite scores, direction labels, and price responses are held out on the judge side. |
| `attachments/test/universe.jsonl` | JSONL | Test-window universe membership. |
| `attachments/test/macro.jsonl` | JSONL | Test-window macro anchors. |
| `attachments/test/test_filer_quarters.json` | JSON | List of `(cik, period)` pairs your submission MUST cover. |

## Data schema (xbrl.jsonl)

Each line is a JSON object with these keys:

- `period` — quarter identifier `"YYYYQq"` (e.g. `"2025Q1"`)
- `cik` — SEC Central Index Key (integer)
- `entity_name` — filer name (may be null)
- `Assets`, `Liabilities`, `StockholdersEquity` — balance-sheet stock USD
  as-of quarter-end
- `LongTermDebt` — stock USD (fallback aliases already resolved:
  `LongTermDebtNoncurrent` / `LongTermDebtAndCapitalLeaseObligations`)
- `ShortTermBorrowings`, `CashAndCashEquivalentsAtCarryingValue` — stock USD
- `InterestExpense` — flow USD per-quarter (SUBSET, ~21% of universe
  reports)
- `OperatingIncomeLoss`, `NetIncomeLoss` — flow USD per-quarter

Missing values are `null` (never zero, never omitted key).

## Data schema (universe.jsonl)

Each line has:

- `period` — `"YYYYQq"`
- `cik` — integer SEC CIK
- `rank` — 1..1000 rank by Assets within the quarter
- `entered` / `exited` — boolean flags for entry/exit vs previous quarter

## Data schema (macro.jsonl)

Each line has:

- `month` — ISO month string `"YYYY-MM"`
- `DGS10`, `DGS2`, `DFF`, `T10Y2Y` — floats (may be null for the trailing
  month if the release date is beyond the bundle build)

## Data schema (test_filer_quarters.json)

Root is a JSON array of objects:

```
[
  {"cik": 320193, "period": "2025Q1"},
  {"cik": 320193, "period": "2025Q2"},
  ...
]
```

Each `(cik, period)` MUST appear as a key in `per_filer_quarter` inside
your `trajectory_results.json`.

## Data provenance

- **SEC EDGAR XBRL frames** — `https://data.sec.gov/api/xbrl/frames/us-gaap/`
  Fetched at bundle build time with an EDGAR-fair-access-compliant
  User-Agent per 17 CFR § 232.301. Frames are US Government public
  disclosure.
- **FRED (Federal Reserve Economic Data)** — DGS10 (10-year Treasury),
  DGS2 (2-year Treasury), DFF (effective Fed Funds), T10Y2Y (10Y-2Y curve
  slope). All US Government public domain via FRED redistribution.

## Constraints

- Each `composite_score` MUST be a finite float (or null only if the
  underlying balance-sheet row has all-null keys, in which case the
  observation is dropped from L1 scoring).
- Each `peer_rank_percentile` and `global_rank_percentile` MUST be on
  [0.0, 1.0].
- Each `refi_direction` MUST be one of `risk_up`, `neutral`, `risk_down`.
- Each `refi_confidence` and `extreme_probability` MUST be on [0.0, 1.0].
- `in_top_decile` and `in_bottom_decile` MUST be booleans.
- Each `position_weight` MUST be a finite float (positive = long,
  negative = short, zero = flat).
- **No future data.** For a filer-quarter observation at period `T`, your
  solver may only read balance-sheet + flow data for periods `<= T`. Do
  not read next quarter's `Liabilities` to inform this quarter's
  trajectory.
- **No hindsight on test targets.** The `test/xbrl.jsonl` file contains
  the raw quarterly XBRL balance-sheet + flow signals only. Composite
  scores, peer ranks, direction labels, and realized post-print price
  responses are NEVER present in the agent-visible data — they live
  exclusively on the judge side.
- **No network.** All computation is offline.
- **No forbidden data sources.** Per contract, do not pull from Yahoo
  Finance, Kaggle, Bloomberg, direct BLS API, `hmmlearn`, per-issuer
  equity prices, SP500, VIXCLS, Stooq, or NCUA. All the data your solver
  needs is in `train/` and `test/`.
- **No cross-directory reads at test time.** Training data (`train/`) is
  separated from held-out test data (`test/`); your system should not
  condition test-window predictions on test-window labels (they are
  absent by construction).
- **Per-filer-quarter compute budget.** Aggregate wall time for the full
  ~5,000-observation predict-write cycle MUST be <= 30 minutes on the
  agent hardware.

## Final Deliverables

Submit exactly three files to `/home/workspace/`:

- `leverage_trajectory.py` — a runnable Python script supporting the
  `--train <input_dir> <state_json>` and `--backtest <input_dir>
  <state_json> <output_json>` CLI modes. You are responsible for producing
  `trajectory_results.json` at your working turn; the judge reads the
  static JSON output.
- `requirements.txt` — dependency list (numpy, pandas, scipy allowed; no
  forbidden packages per Constraints).
- `trajectory_results.json` — the JSON artifact keyed by `(cik, period)`
  with the schema documented in the following section.

## Output schema (trajectory_results.json)

```
{
  "task_id": "sec_leverage_trajectory_projection_book",
  "bundle_uuid": "d3cd6658-d997-5f26-89e3-97e5443046b4",
  "per_filer_quarter": [
    {
      "cik": 320193,
      "period": "2025Q1",
      "composite_score": 0.734,
      "peer_rank_percentile": 0.812,
      "global_rank_percentile": 0.824,
      "refi_direction": "risk_down",
      "refi_confidence": 0.62,
      "extreme_probability": 0.19,
      "in_top_decile": true,
      "in_bottom_decile": false,
      "position_weight": 0.0043,
      "price_response_20d_proxy": 0.021
    },
    ...
  ],
  "self_reported_metrics": {
    "L1_composite_trajectory_rank_correlation_est": 0.34,
    "L2_refinancing_risk_direction_accuracy_est": 0.61,
    "L3_extreme_mover_detection_f1_est": 0.42,
    "L4_delta_liabilities_growth_ranking_ic_est": 0.51,
    "L5_interest_coverage_direction_accuracy_est": 0.58
  }
}
```

`price_response_20d_proxy` is your best capital-structure-derived estimate
of the 20-trading-day post-print price response. It is graded on L6 against
the truth's own post-print response proxy — you do not have to match the
exact truth value (which is held out), but a positive-sign alignment with
your composite's rank ordering is what earns L6 points.

## Special Notes

1. **Peer-group normalization matters.** Raw leverage LEVELS are dominated
   by sector persistence — utilities always run high leverage, technology
   filers always run low. A ranking system that does not peer-normalize
   scores low on L1 and L4 because industry-structure persistence explains
   most of the raw level variance.
2. **Persistence-disease caution — HIGHER SEVERITY than earnings tasks.**
   Capital structure changes require board approval, refinancing windows,
   and covenant navigation — persistence rho on raw Liabilities/Assets
   levels is typically +0.95 or higher. Copy-last-quarter is a real
   temptation. But scoring is TRAJECTORY-SLOPE / rank-based / direction-
   based / PnL-based, not level-based, so copy-last-quarter is a genuine
   trivial baseline you must beat, not a shortcut.
3. **Trajectory-slope estimation required.** Filer rankings on leverage
   LEVELS score low because levels are highly persistent. Rolling-window
   multi-quarter slopes capture genuine capital-structure momentum.
4. **Rate-cycle regime shift matters.** The hidden CY2025 window contains
   an observed hike-plateau-to-cutting-cycle turning point (rates held
   flat CY2024Q4-CY2025Q2, then cutting CY2025Q3-CY2026Q1). Filers whose
   leverage peaked during the plateau and deleveraged as refinancing costs
   eased form the leverage-cycle-bonus positive class. A solver that
   ignores the cycle scores near zero on the bonus lane (worth up to +10
   pts additive over 100).
5. **Cross-quarter stability is intentional.** The 5 test quarters are
   graded independently and then aggregated with variance discount. A
   solver that fits one quarter well and misses the rest loses the L8
   stability lane.
6. **Subset scoring on L5.** `InterestExpense` is reported by only ~21%
   of the universe. L5 lane scores only on the scoreable subset.
7. **Anti-fabrication is a real gate.** The judge independently recomputes
   L1-L5 from your raw per-filer-quarter predictions against truth. If
   your `self_reported_metrics` deviate from the recomputed values by
   more than ±0.15 on any of the five metrics, L7 zeros to 0 (5 pts lost).
   L7 does not cross-lane veto in this variant, but it remains a clear
   signal of fabrication and is treated as a hard diagnostic by the
   grader.
8. **Universe entry/exit is real.** Filers can enter or exit the top-1000
   universe between quarters. `universe.jsonl` carries the entry/exit
   flags. Handle out-of-universe observations correctly: filer-quarter
   pairs listed in `test_filer_quarters.json` are always in-universe for
   that quarter.

## Task Input Description

The following input files are provided with the task and are located in
the `attachments/` directory. Both `attachments/train/*` and `train/*`
resolve to the same files via container-start symlinks.

| File | Format | Description |
| --- | --- | --- |
| `attachments/README.md` | `.md`, `utf-8` | Bundle overview. |
| `attachments/deliverables_guide.md` | `.md`, `utf-8` | Output schema + submission conventions. |
| `attachments/train/xbrl.jsonl` | `.jsonl`, `utf-8` | Pre-CY2025 XBRL panel. |
| `attachments/train/universe.jsonl` | `.jsonl`, `utf-8` | Training-window universe. |
| `attachments/train/macro.jsonl` | `.jsonl`, `utf-8` | Training-window macro. |
| `attachments/test/xbrl.jsonl` | `.jsonl`, `utf-8` | Test-window XBRL panel (input-only). |
| `attachments/test/universe.jsonl` | `.jsonl`, `utf-8` | Test-window universe. |
| `attachments/test/macro.jsonl` | `.jsonl`, `utf-8` | Test-window macro. |
| `attachments/test/test_filer_quarters.json` | `.json`, `utf-8` | List of `(cik, period)` pairs to predict. |
| `attachments/requirements.txt` | `.txt`, `utf-8` | Baseline dependencies (numpy, pandas). |

## Deliverable Requirements

- `leverage_trajectory.py` | Python source file
- `requirements.txt` | plain text
- `trajectory_results.json` | JSON artifact matching the "Output schema"
  section above
