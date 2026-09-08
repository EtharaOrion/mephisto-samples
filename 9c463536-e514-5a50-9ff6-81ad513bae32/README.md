# 9c463536-e514-5a50-9ff6-81ad513bae32

US Treasury short-end cash allocation book. The agent acts as the head of the short-end
liquidity desk at a Treasury-focused money-market fund and publishes a daily positioning
book that allocates cash across the Treasury bill maturity ladder plus overnight liquidity
backstops. The hidden window runs 2025-01-01 to 2026-07-31 on the business-day calendar,
approximately 395 rebalance dates, and the whole run executes with no network access inside
a pinned work image.

## Required outputs

Per rebalance date the system must produce:

- **6-bin cash-ladder allocation** — non-negative weights summing to 1.0 across
  `{b4w, b8w, b13w, b26w, rrp, iorb}`: the 4/8/13/26-week bill tenors, O/N reverse-repo,
  and the interest-on-reserve-balances proxy leg.
- **Funding regime label** — one of `{deep_qt, normal, elevated_stress, extreme_stress}`.
- **Extreme-stress flag** with a self-reported probability on `[0, 1]`, targeting the
  SOFR-IORB blowout + RRP-usage collapse coincidence.
- **Weekly bill-supply direction** — `{up, flat, down}` for forward multi-week issuance.
- **Self-reported certainty** per date on `[0, 1]`.

The book must also emit block-level `self_reported_metrics` so an anti-fabrication gate can
compare the agent's own lane estimates against judge-recomputed values.

## Scoring

Eight lanes plus a funding-cycle bonus lane, 0-110 total:

| Lane | Points | Measures |
|---|---|---|
| L1 | 20 | annualized Sharpe of the ladder book against realized short-end bill returns (cap 1.5) |
| L2 | 15 | 4-class funding-regime accuracy (full at 0.85, zero below 0.25) |
| L3 | 15 | extreme-stress detection F1 (full at 0.85, zero below 0.10) |
| L4 | 10 | 3-class issuance-direction accuracy (full at 0.85) |
| L5 | 10 | Primary Dealer position-change direction on the SBN2024-continuous subset |
| L6 | 10 | money-market PnL proxy: Sharpe of the RRP + IORB legs alone (cap 1.5) |
| L7 | 5 | anti-fabrication: self-reported metrics vs judge-recomputed, ±0.20 tolerance |
| L8 | 10 | cross-week stability |
| Bonus | 10 | funding-cycle lane |

The judge recomputes L1/L2/L3/L4/L6/L8 independently from the raw per-date predictions;
deviation beyond tolerance on any listed field zeros the anti-fabrication lane.

## Artifacts

The graded submission is `treasury_liquidity.py`, `requirements.txt` and
`positioning_results.json` from `/home/workspace`. Agent timeout is 12 hours; the verifier
runs in a separate judge image with a 1 hour budget, both pinned by digest and offline.

## Layout

```
task.toml            task contract; work and judge images pinned by digest
instruction.md       agent-facing specification
environment/         work image context
tests/               judge image: scorer and verification harness
solution/            private oracle tree
trajectory/          recorded run
```
