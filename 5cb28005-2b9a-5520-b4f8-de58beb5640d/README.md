# sec_fundamental_momentum_calibration

- **UUID**: `5cb28005-2b9a-5520-b4f8-de58beb5640d`
- **Task ID**: `sec_fundamental_momentum_calibration`
- **Family**: Professional Knowledge Work — Finance (SEC XBRL fundamental panel)
- **Score range**: 0–110

## What This Task Is About

The agent builds a **cross-sectional fundamental-momentum book** over the top-1000 US SEC filers (ranked by Assets) using EDGAR XBRL frames. For every filer-quarter in a hidden **CY2025Q1 → CY2026Q1** window (5 quarters × ~1000 filers ≈ 5000 observations), it must emit:

1. A composite momentum score
2. A peer-conditional rank
3. An earnings-surprise classification
4. An extreme-filer probability
5. A positioning-book weight

The window spans the observed post-2022-hike **margin-compression-to-recovery regime shift**, so a good solution must adapt to that cycle rather than fit a static factor model.

## Deliverables

Written to `/home/workspace/` by the agent:

| File | Purpose |
|---|---|
| `fundamental_momentum.py` | The agent's solver (executed by the judge to reproduce outputs) |
| `requirements.txt` | Python deps needed to run the solver |
| `momentum_results.json` | Structured predictions consumed by the scorer |

## Test Cadence

5 quarters × ~1000 filers = ~5000 filer-quarter observations, all held out.

## Directory Layout

```
5cb28005-…/
├── task.toml               # schema 1.4 — images, timeouts, artifacts, provenance
├── instruction.md          # Terse pointer read by the agent inside the work container
├── environment/            # Agent-side (work) container
│   ├── Dockerfile          # Builds the work image
│   └── attachments/        # Copied into /home/workspace before the agent starts
│                           # (includes task_instruction.md — the full spec — plus input data)
├── solution/               # Reference implementation (NOT shipped to the agent)
│   ├── fundamental_momentum_reference.py   # Author's reference solver
│   ├── solve.sh                            # Runs the reference against the work image
│   └── TRUTH.md
└── tests/                  # Judge-side (verifier) container
    ├── Dockerfile          # Builds the judge image
    ├── test.sh             # Judge entrypoint
    ├── hidden_test_data/   # Held-out inputs / labels — never exposed to the agent
    └── scoring/            # Scorer that emits the 0–110 score
```

## Data Source & License

- **Source**: SEC EDGAR XBRL frames (`data.sec.gov/api/xbrl/frames/us-gaap/`) per 17 CFR 232.301, plus FRED redistribution route (`fred.stlouisfed.org`) for DGS10, DFF, UNRATE.
- **License**: US Government work, public domain (`us-gov-public-domain`, confidence: high).

## Container Images

| Role | Image tag | Platform |
|---|---|---|
| Work | `edgebench.work.sec_fundamental_momentum_calibration:e6bd619657c5` | `linux/amd64,linux/arm64` |
| Judge | `edgebench.judge.sec_fundamental_momentum_calibration:53ac6a9d48c9` | `linux/amd64,linux/arm64` |

- Network: **no-network** on both containers
- Agent timeout: **43 200 s** (12 h)
- Verifier timeout: **3 600 s** (1 h)
