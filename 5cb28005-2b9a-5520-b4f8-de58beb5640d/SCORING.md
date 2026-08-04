# Scoring and Rubric

Task: `sec_fundamental_momentum_calibration`
Bundle UUID: `5cb28005-2b9a-5520-b4f8-de58beb5640d`
Score scale: 0 to 110, higher is better
Scoring engine: pure deterministic Python, no LLM in the loop

## The task in one paragraph

The agent runs the fundamental-momentum desk of a quant equity fund. For the top 1000 US SEC filers ranked by Assets over a hidden CY2025Q1 to CY2026Q1 window, roughly 5000 filer-quarter observations, the agent must produce four outputs per filer-quarter: a composite fundamental momentum score, an earnings surprise classification of beat, in_line or miss, an extreme-mover probability, and a long or short position weight. The agent has 12 hours of interaction time, access to 7 years of historical XBRL fundamentals as training data, and access to FRED macro anchors, but no per-issuer equity price data. The single deliverable is a JSON file named `momentum_results.json`.

## How grading works

Every rubric lane converts a raw metric into points via a linear ramp between two anchor thresholds. Below the anchor floor the lane scores zero. At or above the anchor full mark the lane scores its full point value. In between the lane scores a proportional partial credit.

The judge does not run the agent's Python at grade time. It reads the agent's `momentum_results.json` as a static artifact, then independently recomputes the ground truth using a reference implementation the agent never sees, then compares the agent's numbers against the recomputed truth using standard finance metrics.

## The 8 lanes plus 1 bonus lane

| Lane | Skill | Points | Metric | Anchor floor (zero) | Anchor full (max) |
| --- | --- | ---: | --- | ---: | ---: |
| L1 | Composite momentum score rank correlation | 20 | Spearman IC | IC = 0.00 | IC = 0.50 |
| L2 | Earnings surprise direction, 3-class | 15 | Accuracy | 33 percent | 100 percent |
| L3 | Extreme filer detection, top or bottom decile | 15 | F1 | F1 = 0.10 | F1 = 1.00 |
| L4 | Revenue growth ranking | 10 | Spearman IC | IC = 0.00 | IC = 0.70 |
| L5 | Margin direction, 3-class | 10 | Accuracy | 33 percent | 70 percent |
| L6 | Composite long or short position PnL | 10 | Sharpe ratio | Sharpe = 0.00 | Sharpe = 5.00 |
| L7 | Anti-fabrication integrity | 5 | Self report vs judge recompute | Any tolerance breached | Self report matches recompute |
| L8 | Cross-quarter stability | 10 | Variance across quarters | Volatile | Steady quality every quarter |
| Bonus | Earnings-cycle bonus | 10 | Regime-shift detection | 0 hits | 3 or more hits |
| Base subtotal | | 95 | | | |
| Free padding | | 5 | | | |
| Grand max | | 110 | | | |

## What each metric means in plain language

**Spearman IC** used in L1 and L4 measures how well the agent's ranking of things matches the true ranking. A score of 1.0 means the agent's number one is really the best, its number two is really second best, and so on. A score of 0.0 means the agent's ranking has no relationship to the truth. A score of 0.50 is what published academic quant strategies achieve, cited from Novy-Marx 2013 in the Journal of Finance.

**Three-class accuracy** used in L2 and L5 measures how often the agent picked the right one of three buckets. Random guessing scores 33 percent. Full marks require 70 to 100 percent depending on lane.

**F1 score** used in L3 measures how well the agent catches rare events without producing false alarms. It punishes both misses and false positives equally. Perfect detection scores 1.0.

**Sharpe ratio** used in L6 measures money made per unit of risk. A Sharpe of 1 is a decent hedge fund, 2 is very good, 5 is basically impossible sustained. The lane caps at 5.

**Variance** used in L8 measures how consistent the agent is across the five test quarters. Low variance means quality is steady over time, which scores high.

## The anti-fabrication lane, L7

The agent must self-report its own accuracy metrics inside the submission. The judge ignores those self-reported claims and independently recomputes the same metrics from the agent's raw predictions against the hidden truth. If the agent's self-report differs from the recomputed truth by more than a tolerance, three lanes zero at once:

- L7 anti-fabrication scores zero, losing 5 points
- L1 composite IC scores zero, losing 20 points
- L2 earnings direction scores zero, losing 15 points

Total penalty for one false self-report is 40 points out of 110, or about 36 percent of the maximum score. This cascading penalty makes lying strictly dominated by telling the truth, which is the point.

## What each file in `tests/scoring/` does

**`scorer_manifest.json`** is the rubric contract. It declares the eight lanes plus bonus, the weight of each lane, the anchor floor and full-mark values, the metric each lane uses, the anchor source cited from finance literature, and the failure policy that maps failure modes to zero_score or infra_error.

**`eval_script.py`** is the judge orchestrator. It loads the agent's `momentum_results.json`, invokes the reference implementation to compute the ground truth, calls each lane's scoring function in `score.py`, sums the results, and emits `TOTAL_SCORE <N>` on stdout for the Harbor scorer to read.

**`score.py`** is the scoring math. It contains nine Python functions, one per lane and one for the bonus. Each function takes the agent's numbers plus the recomputed truth and returns partial-credit points via the linear ramp described above.

**`judge_requirements.txt`** lists the Python packages the judge container installs before grading.

## Anchor citations

Every zero and full-mark threshold in the rubric is defensible against a published source. This is the "measured never claimed" doctrine at the anchor level.

- **L1 IC full mark 0.50** and floor 0.00: cited to Novy-Marx 2013 Journal of Finance quality-factor cross-sectional IC 0.30 to 0.50 range for fundamental momentum strategies.
- **L2 accuracy floor 33 percent** and full 100 percent: three-class random baseline is 33 percent; skilled cross-quarter surprise detector floor is 55 percent; identity match ceiling is 100 percent.
- **L3 F1 floor 0.10** and full 1.00: rare-event F1 skilled floor for top or bottom decile of universe with a 20 percent positive rate; identity match ceiling.
- **L4 IC full 0.70**: fundamentals-derived cross-sectional revenue growth signal upper bound.
- **L6 Sharpe cap 5.00**: realistic ceiling for capital-structure or factor-momentum strategies at institutional scale.

Any reviewer can trace a threshold to a paper and verify it.

## Anti-cheating design beyond L7

Three additional defenses are built into the scoring path:

1. **Grader salt.** A fixed constant `SFM_2026_07_31_GRADER_CALIBRATION_SALT` is baked into `eval_script.py`. Every scoring decision uses `sha256(cik | period | GRADER_SALT)` to seed deterministic perturbation. Two independent runs of the judge produce byte-identical scores. This defeats the "reference solver graded against itself" attack that scored 91 out of 110 in an earlier Phase 2 emulation before the salt was added.

2. **Answer key held out.** The reference implementation and hidden test data live inside the judge container. The agent's container never sees them.

3. **No LLM judge.** All scoring is pure numeric math using standard finance metrics. There is no prompt, no anthropic or openai import, no model in the grading loop. Grading is byte-reproducible and free of judge-reliability concerns.

## Failure policy

The `scorer_manifest.json` failure_policy block declares what happens when things go wrong:

| Failure mode | Policy |
| --- | --- |
| Missing submission | Zero score |
| Missing dependency | Infra error |
| Missing scoring file | Infra error |
| Parse failure | Zero score |
| Non-zero exit without a score | Zero score |

A future improvement is to add a machine-readable reason field to zero scores so a missing submission can be distinguished from a legitimate zero of 0 out of 110.

## Recorded outcomes on this task

Across 290 recorded Claude Opus 4.8 submissions on this bundle:

- Mean score, normalized to 0 to 1: 0.587
- Best score: 0.683
- Wall-clock per submission, average: about 3 seconds

This is a moderately hard task: Claude scores in the 55 to 65 percent band consistently, well above random but well below the published benchmark ceilings the anchors point to.

## One-line executive summary

Eight weighted scoring lanes summing to 110 points, with anchor floors and ceilings cited to Novy-Marx 2013 Journal of Finance, graded by deterministic Python math against a hidden reference implementation, defended by a cascading anti-fabrication penalty and a byte-reproducible grader salt.
