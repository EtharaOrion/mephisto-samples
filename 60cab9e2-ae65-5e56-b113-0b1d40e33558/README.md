# 60cab9e2-ae65-5e56-b113-0b1d40e33558

Fed funds regime labelling plus a Treasury positioning book. The agent acts as the lead rates
strategist at a global asset manager and builds a system that publishes, every week, a forward
Fed policy regime classification, one-week-ahead forecasts for the 2Y and 10Y Treasury yields,
and a duration + curve-slope + front-end-carry positioning book in unit-notional terms - plus a
forward decision call around each FOMC meeting. The judge grades against a hidden 2025Q1-2026H1
window covering approximately 77 weekly windows and 12 FOMC meetings, spanning the observed Fed
hiking-plateau to cutting transition.

## What the system must produce

Per weekly window on the hidden panel:

- **Fed regime label** - one of `{hiking, on_hold_hawkish, on_hold_neutral, on_hold_dovish,
  cutting}` inferred from observable rate and macro signals
- **2Y and 10Y yield forecasts** one week ahead, in basis points
- **Positioning book** - signed unit-notional exposures on `{duration_2y, duration_10y,
  slope_2s10s, carry_front_end}`

Per FOMC event:

- **Predicted rate decision** - `hold`, or a cut/hike in 25 bps increments up to 100 bps

The system trains on the pre-2025 FRED daily/monthly panel (2010-2024) of Fed Funds, Treasury
yields, unemployment and CPI, and must support `--train` and `--backtest` invocation of
`fed_funds_positioning.py`. At judge time the input directory contains the hidden test CSVs, the
weekly window schedule, and the FOMC meeting calendar (dates only, no decisions).

## Scoring

0-110 points: eight graded lanes aggregated with a cross-cadence stability penalty plus a
FOMC-decision bonus. The lanes include regime classification accuracy (20 pts, full marks at
1.00, zero at <= 0.60), 2Y yield MAE (15 pts, full at <= 5 bps, zero at >= 50 bps), 10Y yield
MAE (15 pts, full at <= 8 bps, zero at >= 80 bps), and duration positioning PnL (15 pts), with
the remaining lanes covering the slope and carry books and reporting discipline.

## Environment

- Work and judge run as pinned Docker images (digests in `task.toml`), both `no-network`
- Agent timeout 12 h; verifier timeout 1 h, `environment_mode = "separate"`
- Graded artifacts: `fed_funds_positioning.py`, `requirements.txt`, `positioning_results.json`

## Layout

```
task.toml                    task contract; images pinned by digest
instruction.md               agent-facing specification
environment/                 work image context and pre-2025 FRED training panel
tests/                       judge image: Dockerfile, scoring/, test.sh
tests/hidden_test_data       hidden 2025Q1-2026H1 evaluation panel
solution/                    private oracle tree: TRUTH.md,
                             fed_funds_positioning_reference.py,
                             reference_state.json, requirements.txt, solve.sh
trajectory/                  recorded run
```
