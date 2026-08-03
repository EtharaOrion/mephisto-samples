## Title

Cross-Sectional SEC Fundamental Momentum Calibration

## Task Requirements

You are the head of the quantitative-equity fundamentals desk at a
long/short US equity fund. Every quarter, your desk publishes a
cross-sectional book on the top-1000 US SEC filers (ranked by Assets)
that consists of (a) a per-filer per-quarter composite fundamental
momentum score with peer-conditional normalization, (b) a three-class
earnings-surprise classification per filer per quarter with a self-
reported confidence, (c) an extreme-filer probability that the observation
falls in the top or bottom decile of composite rank, and (d) a per-quarter
positioning book — signed unit-exposure long/short weights across the
universe — sized for volatility and turnover discipline.

Your job is to build a system that, for the hidden CY2025Q1-CY2026Q1
test window (5 quarters × ~1000 filers = ~5,000 filer-quarter
observations), generates per filer-quarter:

- **Composite fundamental momentum score** — a scalar per filer-quarter
  aggregating profitability, growth, margin, and quality signals from the
  quarterly XBRL print, rank-transformed cross-sectionally.
- **Peer-conditional rank percentile** — the composite's percentile
  within the peer group after size-and-sector-adjacent normalization,
  expressed on [0.0, 1.0].
- **Global rank percentile** — the composite's percentile across the
  entire universe for the same quarter.
- **Earnings-surprise direction** — one of `{beat, in_line, miss}`
  reflecting the expected sign of realized earnings vs the analyst /
  cross-quarter consensus surface.
- **Surprise confidence** — self-reported [0.0, 1.0] scalar over the
  direction call.
- **Extreme-filer probability** — [0.0, 1.0] probability that this
  filer-quarter falls in the top decile (blowout) OR bottom decile
  (disappointment) of realized composite rank.
- **Top-decile / bottom-decile flags** — binary indicators derived from
  the extreme-filer probability.
- **Position weight** — signed unit exposure (positive = long,
  negative = short) sized for cross-quarter volatility and turnover
  discipline.

The system MUST include four internal method families, described here by
objective (implementation names are yours; the reference names are held
out of the agent-visible surface for opacity discipline):

1. **Composite scoring family.** Reads the pre-CY2025 XBRL training
   panel (CY2018Q1-CY2024Q4, ~28,000 filer-quarters) and learns per-
   quarter cross-sectional rank transforms of the primary fundamental
   signals — profitability (return on assets, return on equity),
   growth (revenue YoY, gross profit YoY), margin (gross margin,
   operating margin), and quality (asset turnover, leverage discipline).
   Aggregates the standardized signals into a single composite that has
   documented cross-sectional Spearman rank correlation with realized
   post-print outcomes on the training window. This is graded on L1.
2. **Peer-conditional ranking family.** Uses universe membership + size
   bucket to define peer groups and produces a rank percentile that
   corrects for size-persistence and sector persistence. This is the
   L4-graded surface — raw fundamental levels are dominated by size
   effects, so unadjusted ranks score low.
3. **Cross-quarter surprise-direction family.** Reads a filer's own
   4-8 preceding quarterly prints plus the current quarter's fundamental
   signals to project a three-class earnings-surprise call
   (`beat` / `in_line` / `miss`) with self-reported confidence. This is
   the L2 lane; direction accuracy is graded, not magnitude.
4. **Positioning family.** Consumes the composite + surprise call +
   extreme-filer probability to produce cross-sectional long/short
   position weights per quarter, sized for realized cross-quarter
   volatility and turnover discipline. This is the L6 lane, graded on
   the positive-Sharpe-anchored realized PnL vs the truth's post-print
   response proxy.

### Backtest harness

The judge invokes your system once against the held-out CY2025Q1-CY2026Q1
panel and reads the produced `momentum_results.json` — you produce the
output artifact at agent turn time, before submitting the deliverable.
Concretely, during your working turn you MUST:

1. Read `train/fundamentals.jsonl`, `train/universe.jsonl`,
   `train/macro.jsonl` from `/home/workspace/` (symlinked at container
   start; `attachments/` is the physical location).
2. Fit your composite scorer + peer-ranking + surprise-detection +
   positioning families on the training window.
3. Read `test/fundamentals.jsonl`, `test/universe.jsonl`,
   `test/macro.jsonl`, and `test/test_filer_quarters.json`.
4. Produce per-filer-quarter predictions for every `(cik, period)` pair
   listed in `test_filer_quarters.json`.
5. Emit `momentum_results.json` alongside `fundamental_momentum.py` and
   `requirements.txt` in `/home/workspace/`.

The judge does NOT invoke your Python at grade time — it reads your
`momentum_results.json` as a static artifact and independently recomputes
each metric on the hidden test truth. Fabricated numbers are detected via
L7 anti-fabrication and zero the affected lanes.

## Optimization Objectives (in priority order)

Your outputs are scored per-quarter on eight lanes, aggregated with a
cross-quarter stability lane and an earnings-cycle bonus lane.

1. **Composite score rank correlation (20 pts).** Per-quarter Spearman
   rank correlation between your `composite_score` and the truth's
   fundamentals-derived post-print price response proxy, averaged across
   the 5 test quarters. Full marks: IC ≥ 0.50. Zero: IC ≤ 0.00.
2. **Earnings surprise direction (15 pts).** Three-class classification
   accuracy of your `surprise_direction` (`beat` / `in_line` / `miss`) vs
   truth across all test filer-quarters. Full marks: accuracy = 1.00.
   Zero: accuracy ≤ 0.33 (three-class random baseline).
3. **Extreme filer detection F1 (15 pts).** F1 of your
   `in_top_decile OR in_bottom_decile` flags vs truth (rare-event binary
   classification, 20% positive rate). Full marks: F1 = 1.00. Zero:
   F1 ≤ 0.10.
4. **Revenue growth ranking (10 pts).** Per-quarter Spearman IC between
   your `peer_rank_percentile` and truth's realized Revenues YoY growth
   ratio. Full marks: IC ≥ 0.70. Zero: IC ≤ 0.00.
5. **Margin expansion direction (10 pts).** Three-class direction
   accuracy (up / flat / down) of your composite's direction as a
   predictor of truth's realized YoY margin change. Full marks:
   accuracy ≥ 0.70. Zero: accuracy ≤ 0.33.
6. **Composite position PnL (10 pts).** Cross-quarter Sharpe ratio of
   your positioning book realized against truth's post-print response
   proxy, capped at 1.5 (positive-Sharpe-only anchor). Full marks:
   Sharpe ≥ 5.00. Zero: Sharpe ≤ 0.00.
7. **Anti-fabrication (5 pts).** The judge independently recomputes L1,
   L2, L3, L4, and L5 from your raw per-filer-quarter predictions
   against truth and compares against your `self_reported_metrics`.
   Deviation beyond ±0.15 on any of the five metrics zeros this lane
   (standalone, not cross-lane vetoing in this variant).
8. **Cross-quarter stability (10 pts, aggregated).** Awards up to 10
   pts based on the mean per-quarter normalized performance across
   L1-L6, discounted by variance across the 5 test quarters. A solver
   that hyper-fits one quarter and misses the rest is penalized;
   copy-last-quarter is stable but low-mean.

**Earnings-cycle bonus (+10 pts, aggregated).** Awards up to +10
additive points for detection precision of filers whose
`OperatingIncomeLoss / Revenues` bottomed in CY2024Q4-CY2025Q2 and
recovered CY2025Q3-CY2026Q1 (the post-2022-hike margin-compression-to-
recovery regime shift). Saturates at precision ≥ 0.85.

## Benchmark composition

- **Copy-last-quarter baseline.** Composite = previous quarter's
  composite for the same filer; surprise = `in_line` fixed; position = 0.
  This is a genuine trivial baseline you must beat, not a shortcut.
  Because scoring is rank-based / direction-based / PnL-based, copy-
  last-quarter earns positive but non-full marks on the persistent lanes
  (L4 revenue growth ranking) and near-zero on the direction/PnL lanes.
- **Predict-consensus-in-line baseline.** Always predict `in_line`
  direction with 0.33 confidence, composite = 0, position = 0. Scores
  L2 at random-class accuracy, L1/L4/L6 near zero.
- **Random-classification baseline.** Composites uniformly random from
  training-window distribution, directions uniformly random. Scores near
  the anchor floors on every lane.

Your submission is scored on absolute quality against the anchors, not
excess over the baselines; the baselines are informational.

## Provided Data and Materials

All files below live in the `attachments/` directory and are symlinked
to `/home/workspace/` at container start (so both `train/...` and
`attachments/train/...` resolve to the same file).

| File | Format | Description |
| --- | --- | --- |
| `attachments/README.md` | markdown | Bundle overview, schema, and rules (this file's counterpart). |
| `attachments/requirements.txt` | text | Baseline Python dependencies (numpy, pandas) pre-installed at image build. |
| `attachments/train/fundamentals.jsonl` | JSONL | CY2018Q1-CY2024Q4 XBRL flow + stock signals per filer-quarter (~28,000 obs). |
| `attachments/train/universe.jsonl` | JSONL | Top-1000 filers by Assets per training quarter with entry/exit flags. |
| `attachments/train/macro.jsonl` | JSONL | Monthly DGS10 + DFF + UNRATE aligned to the quarterly filer grid. |
| `attachments/test/fundamentals.jsonl` | JSONL | CY2025Q1-CY2026Q1 XBRL flow + stock signals — INPUT-ONLY. Composite scores, surprise labels, and price responses are held out on the judge side. |
| `attachments/test/universe.jsonl` | JSONL | Test-window universe membership. |
| `attachments/test/macro.jsonl` | JSONL | Test-window macro anchors. |
| `attachments/test/test_filer_quarters.json` | JSON | List of `(cik, period)` pairs your submission MUST cover. |

## Data schema (fundamentals.jsonl)

Each line is a JSON object with these keys:

- `period` — quarter identifier `"YYYYQq"` (e.g. `"2025Q1"`)
- `cik` — SEC Central Index Key (integer)
- `entity_name` — filer name (may be null)
- `Revenues` — flow USD, may be null if not reported (fallback aliases
  already resolved at bundle build time)
- `GrossProfit`, `OperatingIncomeLoss`, `NetIncomeLoss` — flow USD per
  quarter
- `EarningsPerShareDiluted` — flow USD per share per quarter
- `Assets`, `StockholdersEquity`, `LongTermDebt` — stock USD as-of
  quarter-end

Missing values are `null` (never zero, never omitted key).

## Data schema (universe.jsonl)

Each line has:

- `period` — `"YYYYQq"`
- `cik` — integer SEC CIK
- `rank` — 1..1000 rank by Assets within the quarter
- `entered` / `exited` — boolean flags for entry/exit vs previous
  quarter

## Data schema (macro.jsonl)

Each line has:

- `date` — ISO date string (monthly cadence)
- `DGS10`, `DFF`, `UNRATE` — floats (may be null for the trailing month
  if the release date is beyond the bundle build)

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
your `momentum_results.json`.

## Data provenance

- **SEC EDGAR XBRL frames** — `https://data.sec.gov/api/xbrl/frames/us-gaap/`
  Fetched at bundle build time with an EDGAR-fair-access-compliant
  User-Agent per 17 CFR § 232.301. Frames are US Government public
  disclosure.
- **FRED (Federal Reserve Economic Data)** — DGS10 (10-year Treasury),
  DFF (effective Fed Funds), UNRATE (unemployment via redistribution
  route, not direct BLS API). All US Government public domain.

## Constraints

- Each `composite_score` MUST be a finite float (or null only if the
  underlying fundamentals row has all-null keys, in which case the
  observation is dropped from L1 scoring).
- Each `peer_rank_percentile` and `global_rank_percentile` MUST be on
  [0.0, 1.0].
- Each `surprise_direction` MUST be one of `beat`, `in_line`, `miss`.
- Each `surprise_confidence` and `extreme_probability` MUST be on
  [0.0, 1.0].
- `in_top_decile` and `in_bottom_decile` MUST be booleans.
- Each `position_weight` MUST be a finite float (positive = long,
  negative = short, zero = flat).
- **No future data.** For a filer-quarter observation at period `T`,
  your solver may only read fundamentals for periods `<= T`. Do not
  read next quarter's Revenues to inform this quarter's composite.
- **No hindsight on test targets.** The `test/fundamentals.jsonl` file
  contains the raw quarterly XBRL flow + stock signals only. Composite
  scores, peer ranks, surprise labels, and realized post-print price
  responses are NEVER present in the agent-visible data — they live
  exclusively on the judge side.
- **No network.** All computation is offline.
- **No forbidden data sources.** Per contract, do not pull from
  Yahoo Finance, Kaggle, Bloomberg, direct BLS API, `hmmlearn`, per-
  issuer equity prices, SP500, VIXCLS, Stooq, or NCUA. All the data
  your solver needs is in `train/` and `test/`.
- **No cross-directory reads at test time.** Training data
  (`train/`) is separated from held-out test data (`test/`); your
  system should not condition test-window predictions on test-window
  labels (they are absent by construction).
- **Per-filer-quarter compute budget.** Aggregate wall time for the
  full ~5,000-observation predict-write cycle MUST be ≤ 30 minutes on
  the agent hardware.

## Final Deliverables

Submit exactly three files to `/home/workspace/`:

- `fundamental_momentum.py` — a runnable Python script that produces
  `momentum_results.json` when invoked at agent turn time. You choose
  its CLI shape; the judge does not invoke it — the judge reads the
  static JSON output.
- `requirements.txt` — dependency list (numpy, pandas, scipy allowed;
  no forbidden packages per Constraints).
- `momentum_results.json` — the JSON artifact keyed by `(cik, period)`
  with the schema documented in the following section.

## Output schema (momentum_results.json)

```
{
  "task_id": "sec_fundamental_momentum_calibration",
  "bundle_uuid": "5cb28005-2b9a-5520-b4f8-de58beb5640d",
  "per_filer_quarter": [
    {
      "cik": 320193,
      "period": "2025Q1",
      "composite_score": 0.734,
      "peer_rank_percentile": 0.812,
      "global_rank_percentile": 0.824,
      "surprise_direction": "beat",
      "surprise_confidence": 0.62,
      "extreme_probability": 0.19,
      "in_top_decile": true,
      "in_bottom_decile": false,
      "position_weight": 0.0043,
      "price_response_20d_proxy": 0.021
    },
    ...
  ],
  "self_reported_metrics": {
    "L1_composite_score_rank_correlation_est": 0.34,
    "L2_earnings_surprise_direction_accuracy_est": 0.61,
    "L3_extreme_filer_detection_f1_est": 0.42,
    "L4_revenue_growth_ranking_ic_est": 0.51,
    "L5_margin_expansion_direction_accuracy_est": 0.58
  }
}
```

`price_response_20d_proxy` is your best fundamentals-derived estimate of
the 20-trading-day post-print price response. It is graded on L6
against the truth's own post-print response proxy — you do not have to
match the exact truth value (which is held out), but a positive-sign
alignment with your composite's rank ordering is what earns L6 points.

## Special Notes

1. **Peer-group normalization matters.** Raw fundamental levels are
   dominated by size persistence — the biggest filers stay biggest,
   trivially. A ranking system that does not peer-normalize scores low
   on L1 and L4 because the size-persistence trivial baseline explains
   most of the raw signal variance.
2. **Persistence-disease caution.** Raw EPS CY2025Q1→CY2026Q1
   persistence has MAE 0.924 vs SD 2.571 (SD/MAE ratio 2.78) — copy-
   last-quarter is a real temptation. But scoring is rank / direction /
   PnL-based, not level-based, so copy-last-quarter is a trivial
   baseline you must beat, not a shortcut. See "Benchmark composition"
   above.
3. **Regime shift matters.** The hidden CY2025 window contains an
   observed post-2022-hike margin-compression-to-recovery regime shift:
   filers whose Operating margin bottomed in CY2024Q4-CY2025Q2 and
   recovered CY2025Q3-CY2026Q1 form the earnings-cycle-bonus positive
   class. A solver that ignores the cycle scores near zero on the bonus
   lane (worth up to +10 pts additive over 100).
4. **Cross-cadence stability is intentional.** The 5 test quarters
   are graded independently and then aggregated with variance discount.
   A solver that fits one quarter well and misses the rest loses the L8
   stability lane.
5. **Anti-fabrication is a real gate.** The judge independently
   recomputes L1-L5 from your raw per-filer-quarter predictions against
   truth. If your `self_reported_metrics` deviate from the recomputed
   values by more than ±0.15 on any of the five metrics, L7 zeros to 0
   (5 pts lost). In this variant L7 does not cross-lane veto, but it
   remains a clear signal of fabrication and is treated as a hard
   diagnostic by the grader.
6. **Universe entry/exit is real.** Filers can enter or exit the
   top-1000 universe between quarters. `universe.jsonl` carries the
   entry/exit flags. Handle out-of-universe observations correctly:
   filer-quarter pairs listed in `test_filer_quarters.json` are always
   in-universe for that quarter.

## Task Input Description

The following input files are provided with the task and are located
in the `attachments/` directory. Both `attachments/train/*` and
`train/*` resolve to the same files via container-start symlinks.

| File | Format | Description |
| --- | --- | --- |
| `attachments/README.md` | `.md`, `utf-8` | Bundle overview. |
| `attachments/train/fundamentals.jsonl` | `.jsonl`, `utf-8` | Pre-CY2025 XBRL panel. |
| `attachments/train/universe.jsonl` | `.jsonl`, `utf-8` | Training-window universe. |
| `attachments/train/macro.jsonl` | `.jsonl`, `utf-8` | Training-window macro. |
| `attachments/test/fundamentals.jsonl` | `.jsonl`, `utf-8` | Test-window XBRL panel (input-only). |
| `attachments/test/universe.jsonl` | `.jsonl`, `utf-8` | Test-window universe. |
| `attachments/test/macro.jsonl` | `.jsonl`, `utf-8` | Test-window macro. |
| `attachments/test/test_filer_quarters.json` | `.json`, `utf-8` | List of `(cik, period)` pairs to predict. |
| `attachments/requirements.txt` | `.txt`, `utf-8` | Baseline dependencies (numpy, pandas). |

## Deliverable Requirements

- `fundamental_momentum.py` | Python source file
- `requirements.txt` | plain text
- `momentum_results.json` | JSON artifact matching the "Output schema"
  section above
