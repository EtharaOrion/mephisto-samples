# cpi_nowcast_positioning_book

- **UUID**: `a4bdb844-5617-534a-9be7-c1a07abe383d`
- **Task ID**: `cpi_nowcast_positioning_book`
- **Family**: Professional Knowledge Work — Finance (macro inflation nowcast + rates positioning)

## What This Task Is About

The agent produces **monthly forward nowcasts** for four US inflation series — **headline CPI (CPIAUCSL), core CPI (CPILFESL), headline PCE (PCEPI), core PCE (PCEPILFE)** — and pairs each with a **Treasury duration + breakeven-inflation positioning book** covering the 1-week window immediately after the print, plus a **Fed policy-regime label**.

Scoring uses realised 2025 BLS/BEA releases and the 1-week post-print market response.

## Deliverables

Written to `/home/workspace/` by the agent:

| File | Purpose |
|---|---|
| `cpi_nowcast_book.py` | The agent's solver |
| `requirements.txt` | Python deps |
| `nowcast_results.json` | Structured predictions consumed by the scorer |

## Test Cadence

12 months × 4 series = **48 hidden prints**.

## Directory Layout

```
a4bdb844-…/
├── task.toml               # schema 1.4 — images, timeouts, artifacts, provenance
├── instruction.md          # Terse pointer read by the agent
├── environment/            # Agent-side (work) container
│   ├── Dockerfile
│   └── attachments/        # Copied into /home/workspace (task_instruction.md + input data)
├── solution/               # Reference implementation (NOT shipped to the agent)
│   ├── cpi_nowcast_reference.py
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

- **Source**: FRED (`fred.stlouisfed.org`) — BLS CPI (CPIAUCSL, CPILFESL), BEA PCE (PCEPI, PCEPILFE), BLS PPI + wages (PPIACO, PPIFIS, CES0500000003, UNRATE), EIA WTI (DCOILWTICO), Census HOUST, and Federal Reserve H.15 rates + breakevens (DGS10, DGS2, DFII10, DFF, T10Y2Y).
- **License**: US Government work, public domain (`us-gov-public-domain`, confidence: high).

## Container Images

| Role | Image tag | Platform |
|---|---|---|
| Work | `edgebench.work.cpi_nowcast_positioning_book:cb487cbd68ee` | `linux/amd64,linux/arm64` |
| Judge | `edgebench.judge.cpi_nowcast_positioning_book:1b5c0da32fcd` | `linux/amd64,linux/arm64` |

- Network: **no-network** on both containers
- Agent timeout: **43 200 s** (12 h)
- Verifier timeout: **3 600 s** (1 h)
