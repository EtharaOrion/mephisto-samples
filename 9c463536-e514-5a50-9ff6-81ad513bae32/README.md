# treasury_liquidity_provisioning_book

- **UUID**: `9c463536-e514-5a50-9ff6-81ad513bae32`
- **Task ID**: `treasury_liquidity_provisioning_book`
- **Family**: Professional Knowledge Work — Finance (short-end Treasury / cash allocation)
- **Score range**: 0–110

## What This Task Is About

The agent runs a **daily-cadence 6-bin cross-sectional cash-mix book** across the Treasury bill maturity spread (**4W / 8W / 13W / 26W bills, O/N RRP, IORB proxy**) with SOFR / RRP / TGA funding-condition overlays. For each of ~395 rebalance dates in the hidden **2025-01-01 → 2026-07-31** window it emits:

1. A per-day 6-bin cash allocation
2. A 4-class funding-condition label
3. An extreme-stress flag
4. A weekly issuance-direction call
5. A composite positioning book

The window spans the observed **QT normalization → potential-cutting-cycle transition**.

## Deliverables

Written to `/home/workspace/` by the agent:

| File | Purpose |
|---|---|
| `treasury_liquidity.py` | The agent's solver |
| `requirements.txt` | Python deps |
| `positioning_results.json` | Structured predictions consumed by the scorer |

## Test Cadence

~395 daily rebalance dates in 2025-01-01 → 2026-07-31.

## Directory Layout

```
9c463536-…/
├── task.toml               # schema 1.4 — images, timeouts, artifacts, provenance
├── instruction.md          # Terse pointer read by the agent
├── environment/            # Agent-side (work) container
│   ├── Dockerfile
│   └── attachments/        # Copied into /home/workspace (task_instruction.md + input data)
├── solution/               # Reference implementation (NOT shipped to the agent)
│   ├── treasury_liquidity_reference.py
│   ├── solve.sh
│   └── TRUTH.md
└── tests/                  # Judge-side (verifier) container
    ├── Dockerfile
    ├── test.sh
    ├── hidden_test_data/   # Held-out inputs / labels
    └── scoring/            # Scorer — emits 0–110
```

## Data Source & License

- **Source**: NY Fed Markets (`markets.newyorkfed.org`) + FRED (`fred.stlouisfed.org`) + `fiscaldata.treasury.gov` + TreasuryDirect (`treasurydirect.gov`) + `home.treasury.gov`.
- **License**: US Government work, public domain (`us-gov-public-domain`, confidence: high).

## Container Images

| Role | Image tag | Platform |
|---|---|---|
| Work | `edgebench.work.treasury_liquidity_provisioning_book:03a5d353` | `linux/amd64,linux/arm64` |
| Judge | `edgebench.judge.treasury_liquidity_provisioning_book:99341f5f` | `linux/amd64,linux/arm64` |

- Network: **no-network** on both containers
- Agent timeout: **43 200 s** (12 h)
- Verifier timeout: **3 600 s** (1 h)
