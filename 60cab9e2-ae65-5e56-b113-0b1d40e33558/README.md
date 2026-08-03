# fed_funds_regime_positioning_book

- **UUID**: `60cab9e2-ae65-5e56-b113-0b1d40e33558`
- **Task ID**: `fed_funds_regime_positioning_book`
- **Family**: Professional Knowledge Work — Finance (Fed policy phase + rates positioning)
- **Score range**: 0–110

## What This Task Is About

The agent runs a **Fed-policy-phase labeler and Treasury duration / curve-slope / front-end-carry positioning book**. For every week in a hidden **2025Q1 → 2026H1** window (77 weekly windows) plus every FOMC meeting in that window (12 meetings), it emits:

1. A per-week policy-phase label
2. 2Y and 10Y yield forecasts
3. A positioning-book weight set
4. A per-FOMC-event decision prediction

The window covers the observed **Fed hiking-plateau → cutting transition**, so the solution must recognise and adapt to the regime pivot.

## Deliverables

Written to `/home/workspace/` by the agent:

| File | Purpose |
|---|---|
| `fed_funds_positioning.py` | The agent's solver |
| `requirements.txt` | Python deps |
| `positioning_results.json` | Structured predictions consumed by the scorer |

## Test Cadence

77 weekly windows + 12 FOMC events = **89 held-out events**.

## Directory Layout

```
60cab9e2-…/
├── task.toml               # schema 1.4 — images, timeouts, artifacts, provenance
├── instruction.md          # Terse pointer read by the agent
├── environment/            # Agent-side (work) container
│   ├── Dockerfile
│   └── attachments/        # Copied into /home/workspace (task_instruction.md + input data)
├── solution/               # Reference implementation (NOT shipped to the agent)
│   ├── fed_funds_positioning_reference.py
│   ├── reference_state.json
│   ├── requirements.txt
│   ├── solve.sh
│   └── TRUTH.md
└── tests/                  # Judge-side (verifier) container
    ├── Dockerfile
    ├── test.sh
    ├── hidden_test_data/   # Held-out inputs / labels
    └── scoring/            # Scorer — emits 0–110
```

## Data Source & License

- **Source**: FRED (`fred.stlouisfed.org`) — Federal Reserve H.15 (DFF, FEDFUNDS, DFEDTARU, DFEDTARL, DGS2, DGS10, T10Y2Y), BLS (UNRATE, CPIAUCSL), and the FOMC calendar (`federalreserve.gov`).
- **License**: US Government work, public domain (`us-gov-public-domain`, confidence: high).

## Container Images

| Role | Image tag | Platform |
|---|---|---|
| Work | `edgebench.work.fed_funds_regime_positioning_book:2ee6ed8d89f5` | `linux/amd64` |
| Judge | `edgebench.judge.fed_funds_regime_positioning_book:121ab7cfd189` | `linux/amd64` |

- Network: **no-network** on both containers
- Agent timeout: **43 200 s** (12 h)
- Verifier timeout: **3 600 s** (1 h)
