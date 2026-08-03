# TRUTH - sec_leverage_trajectory_projection_book

GENERATED FILE. Regenerate via `python3 seed/recompute.py`. Judge-side reference
ground truth for FORGE Phase 1 scaffold (T7/10 of the finance-adjacent Framework B
slate, 2026-07-31). NEVER shipped to work image.

## Canary tokens (also present in seed/grounding.yaml)

- `MEPHISTO_CANARY_SLT_2026_07_31_X481ZV27`
- `MEPHISTO_CANARY_SLT_2026_07_31_KP8FJ30L`
- `MEPHISTO_CANARY_SLT_2026_07_31_LVGAK1Q0`

Canary bindings (see grounding.yaml.canary_bindings):
- `MEPHISTO_CANARY_SLT_2026_07_31_X481ZV27` = judge-side reference-solver method-family opacity boundary
  (CapitalStructureTrajectoryProjector / PeerLeverageDeltaRankRegressor /
  RefinancingRiskSurpriseDetector / NetDebtRegimePositioner).
- `MEPHISTO_CANARY_SLT_2026_07_31_KP8FJ30L` = judge-side hidden CY2025Q1-CY2026Q1 test panel (composite
  trajectory scores + peer-ranked percentiles + refinancing-risk directions +
  extreme-mover flags + capital-structure-derived price-response proxy).
- `MEPHISTO_CANARY_SLT_2026_07_31_LVGAK1Q0` = FORGE Phase 1 build artifacts (TRUTH.md + grounding.yaml
  + recompute.py + oracle.md).

Any hit of any canary token in an agent-visible file (`dataset/d3cd6658-d997-5f26-89e3-97e5443046b4/**`
excluding solution/ + tests/) is a leak-gate FAIL per Phase 2 verifier.

## Task identity

- task_id: `sec_leverage_trajectory_projection_book`
- bundle_uuid: `d3cd6658-d997-5f26-89e3-97e5443046b4`
- contract SHA-256 at Phase 0.5 sign: `cb68e81c405253bb6aa8642eb0aad9d3b7e063f049bc5f9c45876b131793e3e5`
- hardness_catalog_digest: `543b83fb4ca8759cf6d8620f2914467b7e918bee74edab08a7dd3ac5d0096866`
- authored: 2026-07-31

## Fetched panel summary

### SEC EDGAR XBRL frames (via User-Agent 'FORGE tanmaytushar21@gmail.com')

- Concepts fetched: 9 (Assets, Liabilities, StockholdersEquity, LongTermDebt, ShortTermBorrowings, CashAndCashEquivalentsAtCarryingValue, InterestExpense, OperatingIncomeLoss, NetIncomeLoss)
- Fallback aliasing:
  - LongTermDebt -> LongTermDebtNoncurrent -> LongTermDebtAndCapitalLeaseObligations
- Train quarters: 28 (CY2018Q1 through CY2024Q4)
- Test quarters: 5 (CY2025Q1 through CY2026Q1)
- Train filer-quarter observations (agent-visible): 28000
- Test filer-quarter observations (agent-visible INPUT-only): 5000

Test window universes:
- 2025Q1: 1000
- 2025Q2: 1000
- 2025Q3: 1000
- 2025Q4: 1000
- 2026Q1: 1000

### FRED rate anchors (T7 shift from T6's UNRATE-only)

- DGS10  (daily 10-year Treasury) — cached at `.cache/fred/DGS10_2018-01-01_2026-06-30.csv`
- DGS2   (daily 2-year Treasury)  — cached at `.cache/fred/DGS2_2018-01-01_2026-06-30.csv`
- DFF    (daily effective Fed Funds) — cached at `.cache/fred/DFF_2018-01-01_2026-06-30.csv`
- T10Y2Y (daily curve slope 10Y-2Y) — cached at `.cache/fred/T10Y2Y_2018-01-01_2026-06-30.csv`

## Reference method (JUDGE-SIDE ONLY - 4-family opacity per PKW-FAMILIES §3 Framework B)

### CapitalStructureTrajectoryProjector (Stage 1)

Per-filer per-quarter trajectory slope of three balance-sheet ratios over the
trailing 5-quarter window:

- deleverage_slope     = -slope(Liabilities/Assets vs quarter-index)
- net_debt_shrink      = -slope((LongTermDebt+ShortTermBorrowings-Cash)/Assets)
- coverage_improvement = +slope(OperatingIncomeLoss/InterestExpense) [SUBSET]

Each slope cross-sectionally z-scored per quarter. Composite = mean non-null
z-scored slopes; requires >= 2 non-null components. Higher composite = stronger
deleveraging + coverage-improving trajectory = higher predicted price response.

### PeerLeverageDeltaRankRegressor (Stage 2)

Assets deciles substitute for SIC-based peer groups (SIC codes not present in
EDGAR frames responses; T6 precedent). Per quarter, filers sorted by Assets
ascending, partitioned into 10 buckets. Emits peer_rank_percentile within
decile, global_rank_percentile across universe, and delta_liab_over_assets_yoy
(realized YoY change in Liabilities/Assets) for L4 scoring.

### RefinancingRiskSurpriseDetector (Stage 3)

Overlays FRED DGS10 trailing-4Q change onto per-filer LongTermDebt(aliased)-
derived leverage percentile within Assets-decile peer group:

- `risk_up`    if Delta-4Q DGS10 > +25 bps AND filer LTD/Assets percentile within
               decile >= 0.6
- `risk_down`  if Delta-4Q DGS10 < -25 bps AND filer LTD/Assets percentile <= 0.4
- `neutral`    otherwise

### NetDebtRegimePositioner (Stage 4)

Per quarter, positions filer at:
- weight = +1/n_long if global_rank_percentile >= 0.90 (top decile of deleveragers)
- weight = -1/n_short if global_rank_percentile <= 0.10 (bottom decile / worst leveragers)
- weight = 0 otherwise
Rate-cycle overlay: refi_direction "risk_down" boosts long side +10%; "risk_up"
boosts short side +10%. Book dollar-neutral by base construction.

### Post-print price-response proxy

Per-issuer equity price data NOT fetched (Stooq/Yahoo/Bloomberg forbidden per
contract MUST-NOT-DO doctrine; FRED has no per-CIK equity series). Capital-
structure-derived proxy:

    price_response_20d = 0.03 * sign(composite) * min(|composite|, 2.0) / 2.0
                       + hash-seeded uniform(-0.02, +0.02)

Noise seed = int.from_bytes(sha256(f'{cik}|{period}')[:8], 'big'). Alpha
anchor 0.03 grounded in Baker-Wurgler 2002 JF "Market Timing and Capital
Structure" (~1-3% excess return per positive deleveraging trajectory) and
Frank-Goyal 2009 JFE capital-structure survey (cross-sectional IC 0.30-0.50
range for balance-sheet Delta-metrics).

## Held-out CY2025Q1-CY2026Q1 test-panel targets

| Metric                                              | Count / Value |
|-----------------------------------------------------|--------------:|
| Test filer-quarter observations                     | 5000 |
| Filer-quarter observations with composite score     | 2878 |
| Filer-quarters with refi_direction emitted          | 5000 |
|   of which `risk_up`                                | 594 |
|   of which `neutral`                                | 4106 |
|   of which `risk_down`                              | 300 |
| Filer-quarters with coverage_direction (subset)     | 508 |
|   of which `up`                                     | 225 |
|   of which `flat`                                   | 56 |
|   of which `down`                                   | 227 |
| Filer-quarters in top decile of composite rank      | 289 |
| Filer-quarters in bottom decile of composite rank   | 289 |

### Per-quarter positioning-book PnL (capital-structure-derived proxy)

| Test quarter | Positioning-book PnL |
|--------------|---------------------:|
| 2025Q1 | +0.033971 |
| 2025Q2 | +0.029979 |
| 2025Q3 | +0.039813 |
| 2025Q4 | +0.039919 |
| 2026Q1 | +0.035648 |

## Sample (first 20 held-out test-panel target rows with computed composite)

```jsonl
{"assets_decile": 8, "cik": 2488, "composite_score": 1.1503, "coverage_direction": "up", "delta_liab_over_assets_yoy": null, "global_rank_percentile": 0.9666, "in_bottom_decile": false, "in_top_decile": true, "peer_rank_percentile": 0.975, "period": "2025Q1", "price_response_20d_proxy": -0.001312, "refi_direction": "neutral", "z_coverage_improvement": 2.3395, "z_deleverage_slope": null, "z_net_debt_shrink": -0.0389}
{"assets_decile": 7, "cik": 3570, "composite_score": 0.0742, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0385, "global_rank_percentile": 0.6201, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.5776, "period": "2025Q1", "price_response_20d_proxy": 0.012793, "refi_direction": "risk_up", "z_coverage_improvement": null, "z_deleverage_slope": 0.6733, "z_net_debt_shrink": -0.5248}
{"assets_decile": 0, "cik": 4127, "composite_score": -0.0183, "coverage_direction": "down", "delta_liab_over_assets_yoy": 0.012, "global_rank_percentile": 0.4777, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.4062, "period": "2025Q1", "price_response_20d_proxy": -0.006934, "refi_direction": "neutral", "z_coverage_improvement": -0.2552, "z_deleverage_slope": -0.2062, "z_net_debt_shrink": 0.4067}
{"assets_decile": 2, "cik": 4281, "composite_score": 0.684, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0523, "global_rank_percentile": 0.9288, "in_bottom_decile": false, "in_top_decile": true, "peer_rank_percentile": 0.9191, "period": "2025Q1", "price_response_20d_proxy": 0.000997, "refi_direction": "risk_up", "z_coverage_improvement": null, "z_deleverage_slope": 0.9078, "z_net_debt_shrink": 0.4602}
{"assets_decile": 6, "cik": 4447, "composite_score": 0.3241, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0303, "global_rank_percentile": 0.8225, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.8203, "period": "2025Q1", "price_response_20d_proxy": -0.007658, "refi_direction": "neutral", "z_coverage_improvement": null, "z_deleverage_slope": 0.5069, "z_net_debt_shrink": 0.1414}
{"assets_decile": 5, "cik": 4457, "composite_score": -0.3513, "coverage_direction": null, "delta_liab_over_assets_yoy": 0.0102, "global_rank_percentile": 0.1947, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.307, "period": "2025Q1", "price_response_20d_proxy": 9.1e-05, "refi_direction": "risk_up", "z_coverage_improvement": -0.1486, "z_deleverage_slope": -0.2117, "z_net_debt_shrink": -0.6936}
{"assets_decile": 8, "cik": 4904, "composite_score": 0.0212, "coverage_direction": null, "delta_liab_over_assets_yoy": 0.0024, "global_rank_percentile": 0.5412, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.5417, "period": "2025Q1", "price_response_20d_proxy": -0.010679, "refi_direction": "risk_up", "z_coverage_improvement": 0.1371, "z_deleverage_slope": -0.0749, "z_net_debt_shrink": 0.0016}
{"assets_decile": 9, "cik": 4962, "composite_score": 0.0281, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0037, "global_rank_percentile": 0.5515, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.5702, "period": "2025Q1", "price_response_20d_proxy": 0.017124, "refi_direction": "risk_up", "z_coverage_improvement": null, "z_deleverage_slope": 0.037, "z_net_debt_shrink": 0.0192}
{"assets_decile": 7, "cik": 5513, "composite_score": 0.0963, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.016, "global_rank_percentile": 0.6527, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.6466, "period": "2025Q1", "price_response_20d_proxy": 0.00777, "refi_direction": "neutral", "z_coverage_improvement": null, "z_deleverage_slope": 0.242, "z_net_debt_shrink": -0.0494}
{"assets_decile": 6, "cik": 6951, "composite_score": -0.4615, "coverage_direction": null, "delta_liab_over_assets_yoy": 0.0058, "global_rank_percentile": 0.1346, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.1016, "period": "2025Q1", "price_response_20d_proxy": -0.015785, "refi_direction": "neutral", "z_coverage_improvement": null, "z_deleverage_slope": -0.1236, "z_net_debt_shrink": -0.7994}
{"assets_decile": 7, "cik": 7789, "composite_score": 0.0962, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0069, "global_rank_percentile": 0.6509, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.6293, "period": "2025Q1", "price_response_20d_proxy": 0.019161, "refi_direction": "neutral", "z_coverage_improvement": null, "z_deleverage_slope": 0.0952, "z_net_debt_shrink": 0.0971}
{"assets_decile": 7, "cik": 8670, "composite_score": 0.1, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0316, "global_rank_percentile": 0.6612, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.6638, "period": "2025Q1", "price_response_20d_proxy": 0.007099, "refi_direction": "neutral", "z_coverage_improvement": null, "z_deleverage_slope": 0.3699, "z_net_debt_shrink": -0.1698}
{"assets_decile": 2, "cik": 8858, "composite_score": -0.0995, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0123, "global_rank_percentile": 0.3731, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.375, "period": "2025Q1", "price_response_20d_proxy": -0.013999, "refi_direction": "neutral", "z_coverage_improvement": null, "z_deleverage_slope": 0.1492, "z_net_debt_shrink": -0.3482}
{"assets_decile": 4, "cik": 9389, "composite_score": -1.2386, "coverage_direction": null, "delta_liab_over_assets_yoy": 0.062, "global_rank_percentile": 0.0369, "in_bottom_decile": true, "in_top_decile": false, "peer_rank_percentile": 0.0263, "period": "2025Q1", "price_response_20d_proxy": -0.014548, "refi_direction": "risk_up", "z_coverage_improvement": null, "z_deleverage_slope": -1.1062, "z_net_debt_shrink": -1.3711}
{"assets_decile": 5, "cik": 10456, "composite_score": -1.5118, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0348, "global_rank_percentile": 0.0249, "in_bottom_decile": true, "in_top_decile": false, "peer_rank_percentile": 0.0789, "period": "2025Q1", "price_response_20d_proxy": -0.029352, "refi_direction": "neutral", "z_coverage_improvement": null, "z_deleverage_slope": 0.3023, "z_net_debt_shrink": -3.3258}
{"assets_decile": 1, "cik": 12208, "composite_score": -0.1271, "coverage_direction": "down", "delta_liab_over_assets_yoy": 0.0167, "global_rank_percentile": 0.3439, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.3981, "period": "2025Q1", "price_response_20d_proxy": -0.005431, "refi_direction": "neutral", "z_coverage_improvement": -0.0342, "z_deleverage_slope": -0.2509, "z_net_debt_shrink": -0.0962}
{"assets_decile": 9, "cik": 12927, "composite_score": 1.3478, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.1053, "global_rank_percentile": 0.9751, "in_bottom_decile": false, "in_top_decile": true, "peer_rank_percentile": 0.9737, "period": "2025Q1", "price_response_20d_proxy": 0.025706, "refi_direction": "risk_up", "z_coverage_improvement": null, "z_deleverage_slope": 2.1064, "z_net_debt_shrink": 0.5891}
{"assets_decile": 8, "cik": 14272, "composite_score": 0.4872, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0217, "global_rank_percentile": 0.8791, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.8917, "period": "2025Q1", "price_response_20d_proxy": 0.001227, "refi_direction": "risk_up", "z_coverage_improvement": null, "z_deleverage_slope": 0.2402, "z_net_debt_shrink": 0.7342}
{"assets_decile": 0, "cik": 14693, "composite_score": 0.6654, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0631, "global_rank_percentile": 0.922, "in_bottom_decile": false, "in_top_decile": true, "peer_rank_percentile": 0.8646, "period": "2025Q1", "price_response_20d_proxy": -0.00866, "refi_direction": "neutral", "z_coverage_improvement": 0.1627, "z_deleverage_slope": 1.1862, "z_net_debt_shrink": 0.6473}
{"assets_decile": 1, "cik": 15615, "composite_score": 0.6826, "coverage_direction": null, "delta_liab_over_assets_yoy": -0.0259, "global_rank_percentile": 0.9271, "in_bottom_decile": false, "in_top_decile": true, "peer_rank_percentile": 0.8241, "period": "2025Q1", "price_response_20d_proxy": 0.010507, "refi_direction": "neutral", "z_coverage_improvement": null, "z_deleverage_slope": 0.4436, "z_net_debt_shrink": 0.9215}
```

## Reproduction

```
python3 seed/recompute.py                    # regenerate everything from cache
python3 seed/recompute.py --verify           # recompute SHA-256 of every output
```

Expected: idempotent - running twice yields byte-identical outputs.

## Grounding snapshot

Full source of truth: `seed/grounding.yaml`. Contract binding: SHA-256
`cb68e81c405253bb6aa8642eb0aad9d3b7e063f049bc5f9c45876b131793e3e5`
(matches `seed/contract.approved`; temper gate OPEN as of 2026-07-31).

Canary tokens (repeated for redundancy - this file has 9 hits total = 3 tokens
x 3 references each, satisfying leak-detection assay redundancy convention):

- `MEPHISTO_CANARY_SLT_2026_07_31_X481ZV27`
- `MEPHISTO_CANARY_SLT_2026_07_31_KP8FJ30L`
- `MEPHISTO_CANARY_SLT_2026_07_31_LVGAK1Q0`
