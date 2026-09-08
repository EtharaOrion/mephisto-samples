# 5cb28005-2b9a-5520-b4f8-de58beb5640d

Cross-sectional SEC fundamental momentum calibration on US EDGAR-XBRL data. The agent acts as
the head of a quantitative-equity fundamentals desk and builds a system that publishes, for the
top-1000 US SEC filers ranked by Assets, a per-filer-quarter composite momentum score,
peer-conditional and global rank percentiles, an earnings-surprise classification with
confidence, an extreme-filer probability, and a signed long/short positioning book. The judge
grades against a hidden CY2025Q1-CY2026Q1 window - 5 quarters x ~1000 filers, roughly 5,000
filer-quarter observations - spanning the observed post-2022-hike margin-compression-to-recovery
regime shift.

## What the system must produce

Per filer-quarter on the hidden window:

- **Composite fundamental momentum score** - aggregates profitability, growth, margin and
  quality signals from the quarterly XBRL print, rank-transformed cross-sectionally
- **Peer-conditional rank percentile** - percentile within the peer group after
  size-and-sector-adjacent normalization, on [0.0, 1.0]
- **Global rank percentile** - percentile across the full universe for the quarter
- **Earnings-surprise direction** - one of `{beat, in_line, miss}` with a self-reported
  confidence scalar
- **Extreme-filer probability** - probability the observation lands in the top or bottom
  decile of realized composite rank, plus derived binary flags
- **Position weight** - signed unit exposure sized for cross-quarter volatility and turnover
  discipline

Four internal method families are required: composite scoring (trained on the pre-CY2025 XBRL
panel, CY2018Q1-CY2024Q4, ~28,000 filer-quarters), peer-conditional ranking, surprise
classification, and book construction. Reference names for the families are held out of the
agent-visible surface for opacity discipline.

## Scoring

0-110 points: eight graded lanes plus an earnings-cycle bonus. The composite scoring family is
graded on L1 and the peer-conditional ranking surface on L4; the remaining lanes cover surprise
classification, extreme-filer calibration, book PnL and discipline terms. The judge invokes the
submitted `fundamental_momentum.py` against the hidden panel in a separate no-network container.

## Environment

- Work and judge run as pinned Docker images (digests in `task.toml`), both `no-network`
- Agent timeout 12 h; verifier timeout 1 h, `environment_mode = "separate"`
- Graded artifacts: `fundamental_momentum.py`, `requirements.txt`, `momentum_results.json`

## Layout

```
task.toml                    task contract; images pinned by digest
instruction.md               agent-facing specification
environment/                 work image context and training panel
tests/                       judge image: Dockerfile, scoring/, test.sh
tests/hidden_test_data       hidden CY2025Q1-CY2026Q1 evaluation panel
solution/                    private oracle tree: TRUTH.md,
                             fundamental_momentum_reference.py, solve.sh
trajectory/                  recorded run
```
