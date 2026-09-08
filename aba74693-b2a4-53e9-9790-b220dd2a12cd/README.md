# treasury_auction_bidding_calibration

- **UUID**: `aba74693-b2a4-53e9-9790-b220dd2a12cd`
- **Task ID**: `treasury_auction_bidding_calibration`
- **Family**: Professional Knowledge Work — Finance (Treasury primary-market microstructure)

## What This Task Is About

The agent calibrates **per-auction bid ladders across the Treasury note/bond product mix** and predicts the clearing metrics that come out of each auction:

1. Bid-to-cover ratio
2. Tail (stop-out minus WI)
3. Indirect / direct bidder allocation share
4. Overall allocation share
5. Pre-auction reference-yield dislocation

Scoring is done across the held-out **2025 auction cycle**, so a good solution has to generalise across issuance sizes and rate regimes.

## Deliverables

Written to `/home/workspace/` by the agent:

| File | Purpose |
|---|---|
| `auction_bidding.py` | The agent's solver |
| `requirements.txt` | Python deps |
| `bidding_results.json` | Structured predictions consumed by the scorer |

## Test Cadence

Held-out 2025 auction cycle (per-auction aggregation).

## Directory Layout

```
aba74693-…/
├── task.toml               # schema 1.4 — images, timeouts, artifacts, provenance
├── instruction.md          # Terse pointer read by the agent
├── environment/            # Agent-side (work) container
│   ├── Dockerfile
│   └── attachments/        # Copied into /home/workspace (task_instruction.md + input data)
├── solution/               # Reference implementation (NOT shipped to the agent)
│   ├── auction_bidding_reference.py
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

- **Source**: US Treasury Auction Results (`treasurydirect.gov` TA_WS/securities/{Bill|Note|Bond}) + FRED clean-series (`fred.stlouisfed.org`).
- **License**: US Government work, public domain (`us-gov-public-domain`, confidence: high).

## Container Images

| Role | Image tag | Platform |
|---|---|---|
| Work | `edgebench.work.treasury_auction_bidding_calibration:adde5ba60862` | `linux/amd64,linux/arm64` |
| Judge | `edgebench.judge.treasury_auction_bidding_calibration:29bbbfe34182` | `linux/amd64,linux/arm64` |

- Network: **no-network** on both containers
- Agent timeout: **43 200 s** (12 h)
- Verifier timeout: **3 600 s** (1 h)
