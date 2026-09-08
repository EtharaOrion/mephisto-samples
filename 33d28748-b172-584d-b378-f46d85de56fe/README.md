# 33d28748-b172-584d-b378-f46d85de56fe

edgebench/cftc_futures_positioning_book — run the cross-asset positioning desk at a systematic
macro fund. Each week, when the CFTC publishes the Commitments of Traders report, the system
delivers a positioning book covering 25 US-regulated futures contracts across energy, metals,
grains, livestock, rates and FX. The graded window is hidden: 2025-01-07 through 2026-07-22,
80 weekly COT publication dates × 25 markets = 2,000 (market, week) pairs.

## The book

Per market per week the system produces:

- **commercial_net_direction** — `up`/`down`, the direction of next week's change in the
  commercial (hedger) net position
- **magnitude_bucket** — one of four quartile buckets for the size of the next-week change,
  anchored at the training boundary
- **crowding_regime** — `crowded_long` / `neutral` / `crowded_short` / `extreme`, where the
  current commercial net sits in the market's 3-year history
- **extreme_positioning_flag** — true iff the current net is at or beyond the 10th/90th
  percentile of its 3-year rolling window
- **direction_probability** — calibrated confidence that the direction is `up`
- **self_reported_certainty** — per-item certainty in [0, 1]

The system also emits `self_reported_metrics` — its own estimate of each lane's realized
value — which an anti-fabrication gate recomputes from the raw predictions.

## Scoring

100 points across 8 lanes:

| Lane | Points | Measures |
|---|---|---|
| L1 | 20 | commercial direction accuracy, `20·clip((acc−0.45)/0.20, 0, 1)`; copy-last-week is a genuine baseline to beat |
| L2 | 15 | 4-class magnitude bucket accuracy, full marks at 0.55 |
| L3 | 15 | 4-class crowding regime accuracy, full marks at 0.70 |
| L4 | 10 | extreme-flag F1, full marks at 0.70 |
| L5 | 10 | mean weekly Spearman rho between the 25-market probability ranking and realized direction, full marks at 0.40 |
| L6 | 10 | direction accuracy restricted to FOMC/CPI-adjacent weeks |
| L7 | 5 | Brier calibration of per-item confidence versus realized L1 correctness |
| L8 | 15 | cross-quarter stability of L1 accuracy over the six calendar quarters in the window |

## Deliverables

- `cftc_positioning.py` — the system
- `requirements.txt`
- `positioning_results.json` — the full book plus self-reported metrics

The work and judge run in separate pinned containers with no network; the agent envelope is
12 hours.

## Layout

```
task.toml            task contract; work and judge images pinned by digest
instruction.md       agent-facing specification
environment/         work image and training data
tests/               judge image and scoring entrypoint
solution/            private oracle tree
trajectories/        recorded run: opus-4-8
```
