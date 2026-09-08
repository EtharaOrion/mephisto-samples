# d3cd6658-d997-5f26-89e3-97e5443046b4

Build a cross-sectional capital-structure trajectory projection book over the top-1000 US SEC
filers ranked by Assets. The agent acts as the head of a quantitative-credit desk and produces,
for a hidden CY2025Q1-CY2026Q1 test window (5 quarters x ~1000 filers, ~5,000 filer-quarter
observations), a composite trajectory score, peer-conditional and global rank percentiles, a
three-class refinancing-risk direction call with confidence, an extreme-mover probability with
decile flags, and a signed positioning book sized with a rate-cycle overlay. The window spans
the observed CY2025 rate hike-plateau-to-cutting-cycle turning point, so the book must adapt
to a live macro regime change rather than a stationary backdrop.

## System requirements

Three internal components are mandatory:

- **Historical panel model** - fits on the pre-CY2025 SEC EDGAR XBRL panel (CY2018Q1-CY2024Q4,
  ~28,000 filer-quarters) plus an aligned FRED monthly rate/curve panel (DGS10, DGS2, DFF,
  T10Y2Y), learning per-quarter cross-sectional rank transforms of leverage ratio,
  net-debt-to-assets, and interest-coverage rolling-window slopes, aggregated into a single
  composite with documented Spearman rank correlation against realized outcomes.
- **Cross-quarter direction-and-extremes projector** - reads a filer's own 4-8 preceding prints
  plus current-quarter signals and the prevailing rate anchors, and projects the refinancing-risk
  direction call and extreme-mover probability with self-reported confidences.
- **Backtest harness** - `python3 leverage_trajectory.py --train <input_dir> <state_json>` and
  `--backtest <input_dir> <state_json> <output_json>`, reading `train/` and `test/` JSONL panels
  plus `test/test_filer_quarters.json` for the `(cik, period)` pairs to predict.

The judge never invokes the submitted Python at grade time - it reads `trajectory_results.json`
as a static artifact and independently recomputes every metric against the hidden test truth.
Fabricated self-reported numbers are caught by the L7 anti-fabrication lane and zero the
affected lane.

## Scoring

Eight lanes plus a leverage-cycle bonus, 0-110 total. The book is graded on the realized
post-print capital-structure outcomes of the hidden window - composite rank quality, direction
classification, extreme-mover calibration, and positioning-book performance each carry their own
lane, with anti-fabrication cross-checks tying the self-reported metrics to the judge's
independent recomputation.

Data provenance is fully public-domain: SEC EDGAR XBRL frames (US Government public disclosure
per 17 CFR 232.301) and FRED rate series, both US Government work with no copyright restriction.

## Environment

Work and judge run in separate pinned Docker images (digests in `task.toml`) with
`network_mode = "no-network"` and workdir `/home/workspace`. Agent timeout is 43,200 s; the
verifier gets 3,600 s. Submission artifacts are `leverage_trajectory.py`, `requirements.txt`,
and `trajectory_results.json`, packaged via the sforge structured-JSON parser with
score-first selection, maximized.

## Layout

```
task.toml                    task contract; work and judge images pinned by digest
instruction.md               agent-facing specification: requirements, lanes, harness CLI
environment/                 work image context and training-window attachments
tests/                       judge image context and hidden-window truth
solution/                    private oracle tree for the task
trajectory/                  recorded agent run against the shipped judge
```
