# courtlistener_appellate_disposition_timing_calibration

- **UUID**: `74a90894-392e-58cd-a714-5a31e8ac1322`
- **Task ID**: `courtlistener_appellate_disposition_timing_calibration`
- **Family**: Professional Knowledge Work — Legal (US federal appellate analytics)
- **Score range**: 0–110

## What This Task Is About

The agent builds a **disposition-timing calibration book** for US federal appellate cases pending at the **Jan-2026 boundary** across all 13 circuits (`ca1..ca11`, `cadc`, `cafc`). For each of ~2 500–5 000 pending cases resolved in the hidden **2025-01-01 → 2026-07-31** test window, it emits:

1. Predicted days-to-disposition
2. A 4-class circuit-procedural-complexity regime label
3. A stall flag (>1 year with no motion activity)
4. Case-type rank ordering
5. Motion-count regression
6. A composite positioning score

## Deliverables

Written to `/home/workspace/` by the agent:

| File | Purpose |
|---|---|
| `appellate_timing.py` | The agent's solver |
| `requirements.txt` | Python deps |
| `timing_results.json` | Structured predictions consumed by the scorer |

## Test Cadence

~2 500 – 5 000 held-out cases; test window 2025-01-01 → 2026-07-31.

## Directory Layout

```
74a90894-…/
├── task.toml               # schema 1.4 — images, timeouts, artifacts, provenance
├── instruction.md          # Terse pointer read by the agent
├── environment/            # Agent-side (work) container
│   ├── Dockerfile
│   └── attachments/        # Copied into /home/workspace (task_instruction.md + input data)
├── solution/               # Reference implementation (NOT shipped to the agent)
│   ├── appellate_timing_reference.py
│   ├── solve.sh
│   └── TRUTH.md
└── tests/                  # Judge-side (verifier) container
    ├── Dockerfile
    ├── test.sh
    ├── hidden_test_data/   # Held-out inputs / labels
    └── scoring/            # Scorer — emits 0–110
```

## Data Source & License

- **Source**: CourtListener BULK bucket (`storage.courtlistener.com/bulk-data/`) — unauthenticated S3 mirror, 36 dated snapshots back to 2022 per `CARRIERS.md:37`.
- **License**: CC PD Mark 1.0 (`cc-pd-mark-1`, confidence: high) — free of known copyright restrictions.

## Container Images

| Role | Image tag | Platform |
|---|---|---|
| Work | `edgebench.work.courtlistener_appellate_disposition_timing_calibration:041080d0` | `linux/amd64,linux/arm64` |
| Judge | `edgebench.judge.courtlistener_appellate_disposition_timing_calibration:7a5fb32d` | `linux/amd64,linux/arm64` |

- Network: **no-network** on both containers
- Agent timeout: **43 200 s** (12 h)
- Verifier timeout: **3 600 s** (1 h)
