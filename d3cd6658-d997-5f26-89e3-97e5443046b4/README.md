# sec_leverage_trajectory_projection_book

- **UUID**: `d3cd6658-d997-5f26-89e3-97e5443046b4`
- **Task ID**: `sec_leverage_trajectory_projection_book`
- **Family**: Professional Knowledge Work — Finance (SEC XBRL capital-structure trajectory)
- **Score range**: 0–110

## What This Task Is About

The agent builds a **cross-sectional capital-structure trajectory projection book** on the top-1000 US SEC filers (ranked by Assets). For every filer-quarter in a hidden **CY2025Q1 → CY2026Q1** window (5 quarters × ~1000 filers ≈ 5000 observations) it emits:

1. A composite capital-structure trajectory score
2. A peer-conditional rank
3. A refinancing-risk direction classification
4. An extreme-mover probability
5. A positioning-book weight

The window spans the observed **CY2025 rate-hike-plateau-to-cutting-cycle turning point**, so the solution must adapt to that regime pivot rather than fit a static leverage model.

## Deliverables

Written to `/home/workspace/` by the agent:

| File | Purpose |
|---|---|
| `leverage_trajectory.py` | The agent's solver |
| `requirements.txt` | Python deps |
| `trajectory_results.json` | Structured predictions consumed by the scorer |

## Test Cadence

5 quarters × ~1000 filers = ~5000 filer-quarter observations, all held out.

## Directory Layout

```
d3cd6658-…/
├── task.toml               # schema 1.4 — images, timeouts, artifacts, provenance
├── instruction.md          # Terse pointer read by the agent
├── environment/            # Agent-side (work) container
│   ├── Dockerfile
│   └── attachments/        # Copied into /home/workspace (task_instruction.md + input data)
├── solution/               # Reference implementation (NOT shipped to the agent)
│   ├── leverage_trajectory_reference.py
│   ├── solve.sh
│   └── TRUTH.md
└── tests/                  # Judge-side (verifier) container
    ├── Dockerfile
    ├── test.sh
    ├── hidden_test_data/   # Held-out inputs / labels
    └── scoring/            # Scorer — emits 0–110
```

## Data Source & License

- **Source**: SEC EDGAR XBRL frames (`data.sec.gov/api/xbrl/frames/us-gaap/`) per 17 CFR 232.301, plus FRED redistribution route (`fred.stlouisfed.org`) for DGS10, DGS2, DFF, T10Y2Y.
- **License**: US Government work, public domain (`us-gov-public-domain`, confidence: high).

## Container Images

| Role | Image tag | Platform |
|---|---|---|
| Work | `edgebench.work.sec_leverage_trajectory_projection_book:e1f1d886633e` | `linux/amd64,linux/arm64` |
| Judge | `edgebench.judge.sec_leverage_trajectory_projection_book:9251fda55c0f` | `linux/amd64,linux/arm64` |

- Network: **no-network** on both containers
- Agent timeout: **43 200 s** (12 h)
- Verifier timeout: **3 600 s** (1 h)
