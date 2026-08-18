## Iterative Evaluation Mode

You are working with iterative test feedback. After implementing code, you can submit your work for evaluation at any time to see which tests pass and which fail, then iterate based on the results.

### How to Test Your Code

- Run `sforge-submit` to submit your current code for evaluation. It will package the files, send them to the judge server, and return results showing score, pass rate, and a summary of findings.
- Run `sforge-submit --details` to submit and see detailed per-test results.
- Run `sforge-submit --list` to view all previous submissions and their scores for this run.

You should use these regularly to check your progress and identify issues.

### Submitted Files

Only the following paths are submitted for evaluation: `treasury_liquidity.py`, `requirements.txt`, `positioning_results.json`

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

US Treasury Short-End Cash Allocation Book

## Task Requirements

You are the head of the short-end liquidity desk at a Treasury-focused money-market
fund. Every business day you publish a positioning book that allocates cash across
the Treasury bill maturity ladder plus overnight liquidity backstops. For the hidden
2025-01-01 to 2026-07-31 daily window (approximately 395 rebalance dates on the
business-day calendar), your system must produce per-rebalance-date:

- **6-bin cash-ladder allocation** — non-negative weights summing to 1.0 across
  `{b4w, b8w, b13w, b26w, rrp, iorb}`, where `b4w`..`b26w` are the 4/8/13/26-week
  Treasury bill tenors, `rrp` is O/N reverse-repo, and `iorb` is the interest-on-reserve
  balances proxy leg for cash held at the Fed.
- **Regime label** — one of `{deep_qt, normal, elevated_stress, extreme_stress}`
  describing the prevailing short-end funding condition for that date.
- **Extreme-stress flag + self-reported probability** — binary flag for an
  extreme-stress observation (SOFR-IORB blowout + RRP-usage collapse coincidence)
  plus a `[0, 1]` probability.
- **Weekly bill-supply direction** — one of `{up, flat, down}` for the direction
  of forward multi-week bill issuance from the current date's information.
- **Self-reported certainty** per date on `[0, 1]`.

You are also required to emit block-level `self_reported_metrics` — your best-effort
estimate of each scoring lane's performance so an anti-fabrication gate can compare
against judge-recomputed values.

## Optimization Objectives (in priority order)

Your outputs are scored per-day on eight lanes plus a liquidity-cycle bonus lane:

1. **Ladder return lane (20 pts).** Annualized Sharpe of your ladder positioning
   book against realized short-end bill returns derived from yield-curve moves.
   Cap 1.5. Zero: Sharpe ≤ 0.
2. **Funding regime classification (15 pts).** 4-class accuracy of your
   `regime_label` against realized regime labels. Full 15 at accuracy 0.85,
   zero below 0.25.
3. **Extreme-stress detection (15 pts).** F1 of your `extreme_stress_flag` against
   realized extreme-stress binary. Full 15 at F1 0.85, zero below 0.10.
4. **Issuance direction ranking (10 pts).** 3-class accuracy of `supply_direction`
   against realized weekly bill-issuance direction. Full 10 at accuracy 0.85.
5. **PD position change (10 pts, subset scoring).** Direction accuracy on the
   subset of dates where the NY Fed Primary Dealer series is continuous across
   the SBN2024 series break. Awarded 50% default when PD series is unavailable.
6. **Money-market PnL proxy (10 pts).** Annualized Sharpe of your RRP + IORB legs
   alone against short-rate accrual. Cap 1.5.
7. **Anti-fabrication (5 pts).** Judge independently recomputes L1/L2/L3/L4/L6/L8
   metrics from your raw per-date predictions and compares against your
   `self_reported_metrics`. Deviation beyond ±0.20 on any tolerance-listed field
   zeros this lane.
8. **Cross-week stability (10 pts, aggregated).** Awards up to 10 pts based on
   mean weekly positioning-book PnL, discounted by variance across weeks.

**Liquidity-cycle bonus (+10 pts).** Combined precision on QT-regime detection
plus extreme-stress detection during 2025-2026 short-end funding-condition
transitions (QT normalization + potential Fed-cutting-cycle transition).
Saturates at 0.75.

## Benchmark composition

- **Copy-last-day baseline.** Allocation = previous day's allocation; regime =
  `normal` fixed; supply direction = `flat`. This is a genuine trivial baseline
  you must beat.
- **Equal-weight baseline.** Uniform 1/6 allocation on every bin; regime =
  `normal`; supply direction = `flat`.
- **Random-classification baseline.** Random 4-class regime labels + random
  direction calls with uniform allocation.

Persistence-disease hazard for this task is severe: SOFR / RRP / TGA
autocorrelations run 0.95+. Scoring is on realized RETURNS (ladder PnL) and
regime-label ACCURACY, never on raw-level forecast accuracy — copy-yesterday
allocation cannot generate realized-return improvements when regime shifts
occur.

## Provided Data and Materials

All files below live in the `attachments/` directory and are symlinked to
`/home/workspace/` at container start (so both `sofr_train.csv` and
`attachments/sofr_train.csv` resolve to the same file).

| File | Format | Description |
| --- | --- | --- |
| `attachments/deliverables_guide.md` | markdown | Output schema + submission conventions. |
| `attachments/requirements.txt` | text | Baseline Python dependencies (numpy, pandas). |
| `attachments/sofr_train.csv` | CSV | 2018-04-03 to 2024-12-31 daily SOFR rate + volume + percentile buckets. |
| `attachments/repo_train.csv` | CSV | Daily overnight RRP accepted amount + counterparties + award rate. |
| `attachments/pd_positions_train.csv` | CSV | Weekly Primary Dealer positions across bill/coupon tenors (subset, SBN2024 break). |
| `attachments/tga_dts_train.csv` | CSV | Daily fiscaldata DTS Treasury General Account closing balance ($B). |
| `attachments/macro_train.csv` | CSV | Daily DFF / IORB / DGS2 / DGS10 anchors + total public debt outstanding. |
| `attachments/bill_auctions_train.csv` | CSV | TreasuryDirect bill auction calendar (4W/8W/13W/26W/52W). |
| `attachments/short_end_curve_train.csv` | CSV | home.treasury.gov 1M/3M/6M/1Y yields (business daily). |
| `attachments/series_metadata.csv` | CSV | Series-level provenance & license disclosure. |
| `attachments/train_period.txt` | text | Training-window bounds. |
| `attachments/valid_period.txt` | text | Optional train-side validation window (subset of training). |

## Data schema (`*_train.csv`)

- `sofr_train.csv` columns: `date, sofr, sofr_volume_b, sofr_p1, sofr_p25, sofr_p75, sofr_p99`.
- `repo_train.csv` columns: `date, rrp_accepted_b, rrp_counterparties, rrp_rate_avg, rrp_rate_hi, rrp_rate_lo`.
- `tga_dts_train.csv` columns: `date, tga_balance_b`.
- `macro_train.csv` columns: `date, dff, iorb, dgs2, dgs10, total_public_debt_b`.
- `bill_auctions_train.csv` columns: `auction_date, issue_date, maturity_date, term, offering_amt, total_accepted, high_investment_rate, bid_to_cover, primary_dealer_accepted`.
- `short_end_curve_train.csv` columns: `date, y1m, y3m, y6m, y1y` (yields in percent).
- `pd_positions_train.csv` — weekly PD position series (columns depend on availability at authoring time; may be empty on this bundle if source is unavailable — L5 lane default-awards 50% when empty).

Missing values are empty strings.

## Data provenance

- **NY Fed Markets** — SOFR / RRP series via `markets.newyorkfed.org/api/rates/secured/sofr/*` and `.../api/rp/reverserepo/all/results/*`.
- **FRED (Federal Reserve Economic Data)** — DFF, IORB, DGS2, DGS10, DGS1MO, DGS3MO, DGS6MO, DGS1, SOFR, RRPONTSYD via `fred.stlouisfed.org/graph/fredgraph.csv`.
- **fiscaldata.treasury.gov** — Daily Treasury Statement operating cash balance + Debt to the Penny (GET on `/services/api/fiscal_service/...`).
- **TreasuryDirect** — Auctioned bills via `treasurydirect.gov/TA_WS/securities/*?type=Bill`.
- **home.treasury.gov** — Daily short-end yield curve via `/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all`.

All series are US Government works, public domain, license-clean per Federal Reserve H.15 + Treasury Bureau of the Fiscal Service transparency disclosures.

## Constraints

- Each `allocation` dict MUST have all 6 keys `{b4w, b8w, b13w, b26w, rrp, iorb}`,
  each on `[0, 1]`, summing to 1.0 ±1e-6.
- Each `regime_label` MUST be one of `{deep_qt, normal, elevated_stress, extreme_stress}`.
- Each `supply_direction` MUST be one of `{up, flat, down}`.
- Each `extreme_stress_flag` MUST be `true` or `false`.
- Each `extreme_stress_probability` and `self_reported_certainty` MUST be on `[0, 1]`.
- **No future data.** For a rebalance date `t`, your solver may read only data
  from periods `<= t`. Do not read next day's yield to inform today's positioning.
- **No hindsight on test targets.** The `test/`-side test CSVs (input-only,
  provided under `/home/workspace/scoring/dataset/` at judge time) do NOT contain
  realized ladder returns, regime labels, or extreme-stress labels — those live
  exclusively on the judge side and are used to grade your submission.
- **No network.** All computation is offline.
- **No forbidden data sources.** Do not pull from Yahoo, Kaggle, Bloomberg,
  direct BLS, `hmmlearn`, SP500, VIXCLS, Stooq, NCUA, per-CUSIP price series,
  or any commercial data vendor.
- **Per-observation compute budget.** Full backtest (~395 rebalance dates) MUST
  complete in ≤ 30 minutes on the agent hardware.

## Final Deliverables

Submit exactly three files to `/home/workspace/`:

- `treasury_liquidity.py` — a runnable Python script supporting these CLI modes:
    - `python3 treasury_liquidity.py --train <input_dir> <state_json>` — fit on
      pre-2025 data, write persistent state artifact.
    - `python3 treasury_liquidity.py --backtest <input_dir> <state_json> <output_json>` —
      run test window, emit positioning_results.json alongside.
- `requirements.txt` — dependency list.
- `positioning_results.json` — the JSON artifact keyed by rebalance `date` with
  the schema documented below.

## Output schema (positioning_results.json)

```
{
  "task_id": "treasury_liquidity_provisioning_book",
  "bundle_uuid": "9c463536-e514-5a50-9ff6-81ad513bae32",
  "per_date": [
    {
      "date": "2025-01-02",
      "allocation": {"b4w": 0.20, "b8w": 0.18, "b13w": 0.22, "b26w": 0.18, "rrp": 0.11, "iorb": 0.11},
      "regime_label": "normal",
      "extreme_stress_flag": false,
      "extreme_stress_probability": 0.08,
      "supply_direction": "up",
      "self_reported_certainty": 0.6
    }
    /* ...one entry per rebalance date... */
  ],
  "self_reported_metrics": {
    "L1_ladder_return_lane_est": 0.65,
    "L2_regime_classification_est": 0.72,
    "L3_extreme_stress_detection_est": 0.35,
    "L4_supply_direction_est": 0.68,
    "L6_money_market_pnl_proxy_est": 0.45,
    "L8_cross_week_stability_est": 0.55
  }
}
```

## Special Notes

1. **Persistence-disease trap.** SOFR / RRP / TGA autocorrelations run 0.95+.
   A copy-yesterday allocation is a genuine trivial baseline you must beat. Because
   scoring is on realized ladder PnL and regime-label accuracy (not level-forecast
   accuracy), copy-yesterday cannot exploit persistence to earn full marks — but
   it is not trivially defeated either.
2. **Regime transitions matter.** The 2025-01-01 to 2026-07-31 test window
   spans the tail of the QT normalization + potential Fed-cutting-cycle
   transitions. Filers who correctly detect regime transitions are the
   liquidity-cycle-bonus positive class.
3. **Cross-week stability is intentional.** Rebalancing weekly with high turnover
   costs money — the L8 lane penalizes hyper-fit-one-week solvers with
   variance-adjusted scoring.
4. **PD series may be unavailable.** The NY Fed Primary Dealer positions endpoint
   has intermittent authorization gates. L5 lane awards 50% default when the
   subset is empty, so missing PD data does not zero the lane.
5. **Yield-curve-derived returns.** Realized ladder returns are computed by the
   judge from home.treasury.gov short-end yield curve moves (per-CUSIP prices are
   forbidden). Your positioning is scored against a duration × yield-change +
   coupon-accrual proxy per bin.

## Reproduction

The bundle was generated deterministically from
`seed/build/treasury_liquidity_provisioning_book/grounding.yaml` and
`seed/build/treasury_liquidity_provisioning_book/recompute.py` in the Mephisto
repository. Two independent recompute runs produce byte-identical bundle
contents (verified by SHA-256 comparison).
