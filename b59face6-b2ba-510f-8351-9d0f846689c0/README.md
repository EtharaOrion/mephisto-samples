# treasury_curve_positioning_book

- **UUID**: `b59face6-b2ba-510f-8351-9d0f846689c0`
- **Task ID**: `treasury_curve_positioning_book`
- **Family**: Professional Knowledge Work — Finance (Treasury yield-curve positioning)

## What This Task Is About

The agent runs a **dynamic US Treasury yield-curve positioning book** with:

- Duration / convexity / butterfly exposure control
- Macro-regime-adaptive rebalancing
- Turnover discipline (an explicit trading-cost penalty)

Positions are scored across **20 disjoint held-out 3-week windows**, forcing generalisation across curve shapes and macro regimes.

## Deliverables

Written to `/home/workspace/` by the agent:

| File | Purpose |
|---|---|
| `curve_positioning.py` | The agent's solver |
| `requirements.txt` | Python deps |
| `positioning_results.json` | Structured predictions consumed by the scorer |

## Test Cadence

20 disjoint 3-week held-out windows.

## Directory Layout

```
b59face6-…/
├── task.toml               # schema 1.4 — images, timeouts, artifacts, provenance
├── instruction.md          # Terse pointer read by the agent
├── environment/            # Agent-side (work) container
│   ├── Dockerfile
│   └── attachments/        # Copied into /home/workspace (task_instruction.md + input data)
├── solution/               # Reference implementation (NOT shipped to the agent)
│   ├── curve_positioning_reference.py
│   ├── reference_state.json
│   ├── requirements.txt
│   ├── solve.sh
│   └── TRUTH.md
└── tests/                  # Judge-side (verifier) container
    ├── Dockerfile
    ├── test.sh
    ├── hidden_test_data/   # Held-out inputs / labels
    └── scoring/            # Scorer
```

## Data Source & License

- **Source**: US Treasury Daily Yield Curve (`home.treasury.gov`) + FRED clean-series (`fred.stlouisfed.org`).
- **License**: US Government work, public domain (`us-gov-public-domain`, confidence: high).

## Container Images

| Role | Image tag | Platform |
|---|---|---|
| Work | `edgebench.work.treasury_curve_positioning_book:f1a996a5d576` | `linux/amd64,linux/arm64` |
| Judge | `edgebench.judge.treasury_curve_positioning_book:55d9feedceba` | `linux/amd64,linux/arm64` |

- Network: **no-network** on both containers
- Agent timeout: **43 200 s** (12 h)
- Verifier timeout: **3 600 s** (1 h)
