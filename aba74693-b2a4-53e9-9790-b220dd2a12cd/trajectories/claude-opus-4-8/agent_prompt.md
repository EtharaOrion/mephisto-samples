## Iterative Evaluation Mode

You are working with iterative test feedback. After implementing code, you can submit your work for evaluation at any time to see which tests pass and which fail, then iterate based on the results.

### How to Test Your Code

- Run `sforge-submit` to submit your current code for evaluation. It will package the files, send them to the judge server, and return results showing score, pass rate, and a summary of findings.
- Run `sforge-submit --details` to submit and see detailed per-test results.
- Run `sforge-submit --list` to view all previous submissions and their scores for this run.

You should use these regularly to check your progress and identify issues.

### Submitted Files

Only the following paths are submitted for evaluation: `auction_bidding.py`, `requirements.txt`, `bidding_results.json`

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

Treasury Auction Bidding Calibration

## Task Requirements

You are the lead rates strategist at a Treasury bidding desk. On every US Treasury auction day the desk must place a bid ladder — a schedule of `{yield, quantity}` rungs — that trades off two forces: too tight and the desk gets a small allocation; too loose and the desk overpays. Your job is to build a system that, for any 2025 Treasury auction across the bill / note / bond product mix, generates a calibrated bid ladder plus predictions for the realized clearing metrics.

The system MUST include:

1. **Auction demand model.** A module that reads the pre-2025 auction history (cusip-level fields: `bidToCoverRatio`, `highYield`, `averageMedianYield`, `allocationPercentage`, `competitiveTendered`, `competitiveAccepted`, `directBidderAccepted`, `indirectBidderAccepted`, `fimaNoncompetitiveAccepted`, plus tenor metadata) and learns a per-tenor prior over demand dispersion.
2. **Macro-context conditioner.** A module that reads daily FRED macro anchors on the eve of each auction (`DGS1MO`, `DGS3MO`, `DGS2`, `DGS10`, `DGS30`, `DFF`, `T10Y2Y`) and adapts the demand-side prior to the current rate regime. Regime labels are hidden from you.
3. **Bid ladder generator.** For each 2025 auction (`cusip`, `auctionDate`, `securityType`, `securityTerm`, `tenor_years`), produce a 5–15-rung ladder plus per-auction predictions: `predicted_bidToCover`, `predicted_tail_bps` (`highYield − averageMedianYield`), `predicted_indirect_share`, `predicted_direct_share`, `predicted_allocation_share`, `predicted_reference_dislocation_bps` (auction `highYield` vs FRED reference yield at auction eve).
4. **Backtest harness.** The system MUST support invocation as `python3 auction_bidding.py --backtest --data <hidden_csv> --macro <hidden_macro_csv> --state reference_state.json --output bidding_results.json`. The judge invokes your script once against the full held-out 2025 auction cycle.

## Optimization Objectives (in priority order)

Your bid ladder is scored per auction on eight lanes, then aggregated across the full 2025 auction cycle with a cross-product-mix stability penalty and a rate-regime-shift detection bonus.

1. **Bid-ladder accuracy (25 pts).** How closely your predicted cumulative bid-quantity curve matches the realized cumulative accepted-quantity curve. Full marks: alignment within 5 bps at every rung. Zero: flat/random ladder.
2. **`bidToCover` prediction (15 pts).** Mean absolute percentage error of `predicted_bidToCover` vs realized `bidToCoverRatio`. Full marks: MAPE ≤ 8%. Zero: MAPE ≥ 40%.
3. **Tail control (15 pts).** RMSE of `predicted_tail_bps` vs realized tail (`highYield − averageMedianYield`) in basis points, calibrated per tenor bucket. Full marks: RMSE ≤ 1 bp (bills) / 2 bps (notes+bonds). Zero: RMSE ≥ 10 bps.
4. **Allocation-share calibration (10 pts).** Mean absolute error of `predicted_allocation_share` vs realized `allocationPercentage/100`, per tenor. Full marks: MAE ≤ 0.03.
5. **Indirect / direct share (10 pts).** Combined MAE of `predicted_indirect_share` and `predicted_direct_share` vs realized values. Full marks: joint MAE ≤ 0.05.
6. **Reference-yield dislocation (10 pts).** MAE of `predicted_reference_dislocation_bps` vs realized dislocation (auction `highYield` vs FRED reference yield at auction eve), with directional-accuracy weighting.
7. **Anti-fabrication integrity (5 pts).** The judge independently recomputes each per-auction metric from your raw ladder plus predictions and compares against your `self_reported_metrics` (mean MAPE / RMSE / MAE roll-ups). Deviations beyond `bidToCover MAPE > 0.5%`, `tail RMSE > 2 bps`, `indirect_share MAE > 0.02`, or `allocation_share MAE > 0.02` zero this lane AND zero the bid-ladder lane (L1) for that auction.
8. **Cross-product-mix stability (10 pts, aggregated).** Variance of L1 scores across the bill / note / bond buckets. Low variance = high score; a single product class carrying the score is penalized.

**Rate-regime-shift bonus (+10 pts, aggregated).** If your `detected_regime_events` correctly identify hidden 2025 rate-regime transitions (FOMC-decision-driven or curve-shape-driven, defined in judge ground truth) within 3 calendar days of the true event, your submission earns up to +10 bonus points; saturates at 3+ matches.

## Benchmark composition

- Flat-ladder baseline: single-rung ladder at the historical average yield for that tenor.
- Copy-last-auction baseline: predict this auction's outcomes as the last realized values for the same tenor.
- Equal-quantity baseline: uniform quantities across a fixed grid of rungs.

Your submission is scored on absolute performance, not excess over these baselines; the baselines are informational.

## Provided Data and Materials

All files below live in the `attachments/` directory.

| File | Format | Description |
| --- | --- | --- |
| `attachments/auction_history_train.csv` | CSV (utf-8) | Pre-2025 Treasury auction records: cusip, auctionDate, issueDate, securityType (Bill|Note|Bond), securityTerm, highYield, highDiscountRate, averageMedianYield, bidToCoverRatio, allocationPercentage, competitiveTendered, competitiveAccepted, directBidderAccepted/Tendered, indirectBidderAccepted/Tendered, fimaNoncompetitiveAccepted/Tendered, primaryDealerAccepted/Tendered, noncompetitiveAccepted/Tendered, offeringAmount, totalAccepted, totalTendered. |
| `attachments/macro_indicators_train.csv` | CSV (utf-8) | Daily FRED macro anchors (DGS1MO, DGS3MO, DGS2, DGS10, DGS30, DFF, T10Y2Y) forward-filled across weekends and holidays, ending 2024-12-31. |
| `attachments/auction_schedule_reference.csv` | CSV (utf-8) | Pre-2025 auction schedule metadata for pattern learning: cusip, auctionDate, issueDate, securityType, securityTerm, tenor_years, offeringAmount, totalAccepted, totalTendered. |
| `attachments/tenor_info.csv` | CSV (utf-8) | Reference table: securityType, securityTerm, tenor_years, calendar_conventions, day_count_convention, coupon_frequency, is_discount. |
| `attachments/train_period.txt` | text | Two dates comma-separated. Use this window to fit your demand model and macro conditioner. |
| `attachments/valid_period.txt` | text | Two dates comma-separated. Reserve for hyperparameter selection / strategy validation. Iterative refinement is allowed within this window. |
| `attachments/deliverables_guide.md` | markdown | JSON schema of `bidding_results.json` + submission conventions. |
| `attachments/requirements.txt` | text | Python package dependencies you MAY install. |

## Constraints

- Each rung of `predicted_bid_ladder` MUST be `{yield_bps: int, quantity_pct: float}` with monotone-non-decreasing `yield_bps` AND monotone-non-decreasing `quantity_pct`; the final `quantity_pct` MUST be 100.0.
- 5 ≤ `len(predicted_bid_ladder)` ≤ 15 per auction.
- `predicted_indirect_share + predicted_direct_share + predicted_primary_share ≤ 1.0` (primary_share is inferred and not required; but overlap constraint must hold).
- `predicted_bidToCover` MUST be finite, positive, and consistent with your predicted ladder (see below).
- No future data. At auction date `t`, your solver may only read data with `date ≤ t − 1` (auction-eve close is the last permitted timestamp).
- No network. All computation is offline.
- No cross-directory reads. Training/validation data (`attachments/`) is physically separated from held-out test data. Your `--backtest` invocation reads exclusively the paths passed on `--data`, `--macro`, and `--state`.
- Per-auction backtest wall time: ≤ 2 seconds; total backtest wall time over the full test cycle: ≤ 45 minutes.

## Final Deliverables

- `auction_bidding.py` — a runnable Python script that accepts:
  - `--train --data <train_csv> --macro <macro_csv> --state <state_json>` (fits on training data, writes a persistent state artifact)
  - `--backtest --data <test_csv> --macro <macro_csv> --state <state_json> --output <bidding_results.json>` (reads state, iterates auctions in `--data`, writes bid ladders + predictions)
- `requirements.txt` — dependency list.
- `bidding_results.json` — the JSON produced by `--backtest`. Schema is documented in `attachments/deliverables_guide.md`.

## Special Notes

1. The hidden 2025 auction cycle includes at least one rate-regime-shift event (FOMC-decision-driven or curve-shape-driven). If your `detected_regime_events` list flags a transition within 3 calendar days of the true event, your submission earns up to +10 bonus points (saturates at 3 matches). The detection mechanism MUST be a general data-driven rule (macro-signal transition, not date-hardcoding).
2. The training period covers zero-rate era (2010–2015), taper tantrum (2013), rate-hike cycle (2015–2019), COVID easing (2020–2021), rapid hiking (2022–2023), and 2024 disinflation. Your system must remain robust across all regimes.
3. Data authenticity requirement. All values in `bidding_results.json` must genuinely reflect execution. The judge independently recomputes each per-auction metric from your raw ladder + predictions and compares against your `self_reported_metrics`. Deviations beyond tolerance zero the anti-fabrication lane AND zero the bid-ladder lane (L1) for that auction. Fabricated outputs have caused entire-cycle disqualification in prior evaluations.
4. Product-mix heterogeneity is intentional. Bills, notes, and bonds have fundamentally different demand micro-structure — a solver that hyper-fits the note book while ignoring bill dynamics will lose the cross-product-mix stability lane. Treat each product class with an appropriate per-tenor tail model.
5. At judge time, `auction_bidding.py` is executed in an isolated evaluation directory. Hidden test data is passed via CLI paths; training/validation `attachments/` are NOT re-attached. Your code MUST load fitted state exclusively from `--state <path>`.

## Task Input Description

The following input files are provided with the task, all located in the `attachments/` directory:

| File | Format | Description |
| --- | --- | --- |
| `attachments/auction_history_train.csv` | `.csv`, `utf-8` | Pre-2025 Treasury auction records across bill / note / bond product mix. |
| `attachments/macro_indicators_train.csv` | `.csv`, `utf-8` | Daily FRED macro anchors (DGS1MO, DGS3MO, DGS2, DGS10, DGS30, DFF, T10Y2Y) up to 2024-12-31. |
| `attachments/auction_schedule_reference.csv` | `.csv`, `utf-8` | Pre-2025 auction schedule metadata for pattern learning. |
| `attachments/tenor_info.csv` | `.csv`, `utf-8` | Reference tenor / calendar convention table. |
| `attachments/train_period.txt` | `.txt`, `utf-8` | Training period, format: `YYYY-MM-DD,YYYY-MM-DD`. |
| `attachments/valid_period.txt` | `.txt`, `utf-8` | Validation period, format: `YYYY-MM-DD,YYYY-MM-DD`. |

Reference document: `attachments/deliverables_guide.md`.

## Deliverable Requirements

- `auction_bidding.py` | Python source file
- `requirements.txt` | plain text
- `bidding_results.json` | JSON (per-cycle output produced by `--backtest`)
