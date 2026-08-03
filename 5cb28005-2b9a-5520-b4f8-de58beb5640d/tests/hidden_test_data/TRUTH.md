# TRUTH — sec_fundamental_momentum_calibration

GENERATED FILE. Regenerate via `python3 seed/recompute.py`. Judge-side reference
ground truth for FORGE Phase 1 scaffold (T6/10 of the finance-adjacent Framework B
slate, 2026-07-31). NEVER shipped to work image.

## Canary tokens (also present in seed/grounding.yaml)

- `MEPHISTO_CANARY_SFM_2026_07_31_KEMUILEJ`
- `MEPHISTO_CANARY_SFM_2026_07_31_6HUOWVQR`
- `MEPHISTO_CANARY_SFM_2026_07_31_JD6DBT7E`

Canary bindings (see grounding.yaml.canary_bindings):
- `MEPHISTO_CANARY_SFM_2026_07_31_KEMUILEJ` = judge-side reference-solver method-family opacity boundary
  (FundamentalCompositeScorer / PeerGroupRankRegressor / CrossQuarterSurpriseDetector /
  FactorMomentumPositioner).
- `MEPHISTO_CANARY_SFM_2026_07_31_6HUOWVQR` = judge-side hidden CY2025Q1-CY2026Q1 test panel (composite
  scores + peer-ranked percentiles + surprise directions + fundamentals-derived
  price-response proxy).
- `MEPHISTO_CANARY_SFM_2026_07_31_JD6DBT7E` = FORGE Phase 1 build artifacts (TRUTH.md + grounding.yaml
  + recompute.py + oracle.md).

Any hit of any canary token in an agent-visible file (`dataset/5cb28005-2b9a-5520-b4f8-de58beb5640d/**`)
is a leak-gate FAIL per Phase 2 verifier.

## Task identity

- task_id: `sec_fundamental_momentum_calibration`
- bundle_uuid: `5cb28005-2b9a-5520-b4f8-de58beb5640d`
- contract SHA-256 at Phase 0.5 sign: `103f591fb359bcbba17d91ec4c2bf702cd88d83c67dacffc3de99670a9e5ac6f`
- hardness_catalog_digest: `543b83fb4ca8759cf6d8620f2914467b7e918bee74edab08a7dd3ac5d0096866`
- authored: 2026-07-31

## Fetched panel summary

### SEC EDGAR XBRL frames (via User-Agent 'FORGE tanmaytushar21@gmail.com')

- Concepts fetched: 8 (Revenues, GrossProfit, OperatingIncomeLoss, NetIncomeLoss, EarningsPerShareDiluted, Assets, StockholdersEquity, LongTermDebt)
- Fallback aliasing:
  - Revenues -> SalesRevenueNet -> RevenueFromContractWithCustomerExcludingAssessedTax
  - LongTermDebt -> LongTermDebtNoncurrent -> LongTermDebtAndCapitalLeaseObligations
- Train quarters: 28 (CY2018Q1 through CY2024Q4)
- Test quarters: 5 (CY2025Q1 through CY2026Q1)
- Train filer-quarter observations (agent-visible): 28000
- Test filer-quarter observations (agent-visible INPUT-only): 5000

### Universe construction (top-1000 by Assets per quarter)

| Period | Universe size | Period | Universe size |
|--------|--------------:|--------|--------------:|
| 2018Q1 | 1000 | 2018Q2 | 1000 |
| 2018Q3 | 1000 | 2018Q4 | 1000 |
| 2019Q1 | 1000 | 2019Q2 | 1000 |
| 2019Q3 | 1000 | 2019Q4 | 1000 |
| 2020Q1 | 1000 | 2020Q2 | 1000 |
| 2020Q3 | 1000 | 2020Q4 | 1000 |
| 2021Q1 | 1000 | 2021Q2 | 1000 |
| 2021Q3 | 1000 | 2021Q4 | 1000 |
| 2022Q1 | 1000 | 2022Q2 | 1000 |
| 2022Q3 | 1000 | 2022Q4 | 1000 |
| 2023Q1 | 1000 | 2023Q2 | 1000 |
| 2023Q3 | 1000 | 2023Q4 | 1000 |
| 2024Q1 | 1000 | 2024Q2 | 1000 |
| 2024Q3 | 1000 | 2024Q4 | 1000 |

Test window universes:
- 2025Q1: 1000
- 2025Q2: 1000
- 2025Q3: 1000
- 2025Q4: 1000
- 2026Q1: 1000

### FRED macro anchors

- DGS10 (daily 10-year Treasury) — cached at `.cache/fred/DGS10_2018-01-01_2026-06-30.csv`
- DFF (daily effective Fed Funds) — cached at `.cache/fred/DFF_2018-01-01_2026-06-30.csv`
- UNRATE (monthly unemployment via FRED redistribution route — NOT direct BLS) — cached at `.cache/fred/UNRATE_2018-01-01_2026-06-30.csv`

## Reference method (JUDGE-SIDE ONLY — 4-family opacity per PKW-FAMILIES §3 Framework B)

### FundamentalCompositeScorer (Stage 1)

Combines four fundamental momentum components per filer per quarter:

| Component  | Formula                                                                | Data                        |
|------------|------------------------------------------------------------------------|-----------------------------|
| eps_yoy    | (EPS[q] - EPS[q-4]) / max(\|EPS[q-4]\|, 0.01)                        | EarningsPerShareDiluted     |
| rev_yoy    | (Rev[q] - Rev[q-4]) / max(\|Rev[q-4]\|, 1.0)                         | Revenues (aliased fallback) |
| margin_qoq | (OpInc[q] / Rev[q]) - (OpInc[q-4] / Rev[q-4])                          | OperatingIncomeLoss, Revenues |
| revision   | (EPS[q] - mean(EPS[q-1..q-3])) / max(pstdev(EPS[q-1..q-3]), 0.01)      | EarningsPerShareDiluted     |

Each component is cross-sectionally z-scored per quarter (mean 0, pstdev 1 across
all in-universe filers with that component non-null). Composite = mean of non-null
z-scored components. Requires >= 2 non-null components to emit a score.

### PeerGroupRankRegressor (Stage 2)

Assets deciles substitute for SIC-based peer groups (SIC codes are not present in
EDGAR frames responses). Per quarter, filers are sorted by Assets ascending and
partitioned into 10 equal buckets. `peer_rank_percentile` is the intra-decile
percentile rank of composite_score.

### CrossQuarterSurpriseDetector (Stage 3)

Predicted EPS[q] = linear extrapolation from OLS(x = -offset, y = EPS[q-n]) over
n in 1..4 (requires >= 3 non-null lagged EPS points; otherwise no surprise emitted).
`surprise_relative = (actual - predicted) / max(|predicted|, 0.01)`. Direction:

- `beat` if surprise_relative > +0.05
- `miss` if surprise_relative < -0.05
- `in_line` otherwise

### FactorMomentumPositioner (Stage 4)

Per quarter, positions filer at:
- weight = +1 / n_long if global_rank_percentile >= 0.90 (top decile)
- weight = -1 / n_short if global_rank_percentile <= 0.10 (bottom decile)
- weight = 0 otherwise

Book is dollar-neutral by construction.

### Post-print price-response proxy (grounding.yaml.reference_solver.price_response_proxy)

Per-issuer equity price data is NOT fetched (Stooq/Yahoo/Bloomberg forbidden per
contract MUST-NOT-DO doctrine; FRED does not carry per-CIK equity prices). The
fundamentals-derived proxy is:

    price_response_20d = 0.03 * sign(surprise_rel) * min(|surprise_rel|, 0.5)
                       + hash-seeded uniform(-0.02, +0.02)

where the noise seed is `int.from_bytes(sha256(f'{cik}|{period}')[:8], 'big')`,
ensuring deterministic identical noise across recompute runs while introducing
plausible realized-return dispersion. Anchor `alpha = 0.03` grounded in
Novy-Marx 2013 JFE + Fama-French 2015 quality-factor findings that positive
earnings surprises produce ~1-3% excess return over 20-day post-print window.

## Held-out CY2025Q1-CY2026Q1 test-panel targets

| Metric                                              | Count / Value |
|-----------------------------------------------------|--------------:|
| Test filer-quarter observations                     | 5000 |
| Filer-quarter observations with computed surprise   | 3257 |
|   of which `beat`                                   | 1486 |
|   of which `in_line`                                | 304 |
|   of which `miss`                                   | 1467 |
| Filer-quarters in top decile of composite rank      | 352 |
| Filer-quarters in bottom decile of composite rank   | 352 |

### Per-quarter positioning-book PnL (fundamentals-derived proxy)

| Test quarter | Positioning-book PnL |
|--------------|---------------------:|
| 2025Q1 | +0.010720 |
| 2025Q2 | +0.014505 |
| 2025Q3 | +0.011496 |
| 2025Q4 | +0.010074 |
| 2026Q1 | +0.014693 |

## Sample (first 20 held-out test-panel target rows)

```jsonl
{"assets_decile": 8, "cik": 1800, "composite_score": 0.0065, "eps_actual": 0.76, "eps_predicted_from_prior4": 1.1533, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.546, "period": "2025Q1", "price_response_20d_proxy": -0.029806, "surprise_direction": "miss", "surprise_relative": -0.341}
{"assets_decile": 8, "cik": 2488, "composite_score": 0.3184, "eps_actual": 0.44, "eps_predicted_from_prior4": 0.8333, "in_bottom_decile": false, "in_top_decile": true, "peer_rank_percentile": 0.9483, "period": "2025Q1", "price_response_20d_proxy": -0.032727, "surprise_direction": "miss", "surprise_relative": -0.472}
{"assets_decile": 7, "cik": 2969, "composite_score": -2.391, "eps_actual": -7.77, "eps_predicted_from_prior4": 2.9071, "in_bottom_decile": true, "in_top_decile": false, "peer_rank_percentile": 0.0053, "period": "2025Q1", "price_response_20d_proxy": -0.01817, "surprise_direction": "miss", "surprise_relative": -3.6727}
{"assets_decile": 7, "cik": 3570, "composite_score": -0.955, "eps_actual": 1.57, "eps_predicted_from_prior4": 6.0, "in_bottom_decile": true, "in_top_decile": false, "peer_rank_percentile": 0.0266, "period": "2025Q1", "price_response_20d_proxy": -0.003321, "surprise_direction": "miss", "surprise_relative": -0.7383}
{"assets_decile": 0, "cik": 4127, "composite_score": -0.2092, "eps_actual": 0.43, "eps_predicted_from_prior4": 0.9043, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.1, "period": "2025Q1", "price_response_20d_proxy": -0.02166, "surprise_direction": "miss", "surprise_relative": -0.5245}
{"assets_decile": 2, "cik": 4281, "composite_score": 0.0905, "eps_actual": 0.84, "eps_predicted_from_prior4": 1.0133, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.7722, "period": "2025Q1", "price_response_20d_proxy": -0.014395, "surprise_direction": "miss", "surprise_relative": -0.1711}
{"assets_decile": 6, "cik": 4447, "composite_score": -0.1252, "eps_actual": 1.39, "eps_predicted_from_prior4": 0.1033, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.2865, "period": "2025Q1", "price_response_20d_proxy": 0.00248, "surprise_direction": "beat", "surprise_relative": 12.4516}
{"assets_decile": 8, "cik": 4904, "composite_score": 0.0001, "eps_actual": 1.5, "eps_predicted_from_prior4": 1.2967, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.523, "period": "2025Q1", "price_response_20d_proxy": -0.006293, "surprise_direction": "beat", "surprise_relative": 0.1568}
{"assets_decile": 9, "cik": 4962, "composite_score": -0.046, "eps_actual": 3.64, "eps_predicted_from_prior4": 3.8967, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.2812, "period": "2025Q1", "price_response_20d_proxy": 0.014726, "surprise_direction": "miss", "surprise_relative": -0.0659}
{"assets_decile": 8, "cik": 4977, "composite_score": -0.1832, "eps_actual": 0.05, "eps_predicted_from_prior4": -3.07, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.1322, "period": "2025Q1", "price_response_20d_proxy": 0.010294, "surprise_direction": "beat", "surprise_relative": 1.0163}
{"assets_decile": 9, "cik": 5272, "composite_score": -0.0296, "eps_actual": 1.16, "eps_predicted_from_prior4": -2.715, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.3187, "period": "2025Q1", "price_response_20d_proxy": 0.033809, "surprise_direction": "beat", "surprise_relative": 1.4273}
{"assets_decile": 7, "cik": 5513, "composite_score": -0.1218, "eps_actual": 1.06, "eps_predicted_from_prior4": 4.6467, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.2606, "period": "2025Q1", "price_response_20d_proxy": -0.008674, "surprise_direction": "miss", "surprise_relative": -0.7719}
{"assets_decile": 7, "cik": 6201, "composite_score": -0.0903, "eps_actual": -0.72, "eps_predicted_from_prior4": 0.475, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.2926, "period": "2025Q1", "price_response_20d_proxy": -0.010588, "surprise_direction": "miss", "surprise_relative": -2.5158}
{"assets_decile": 7, "cik": 6281, "composite_score": 0.7307, "eps_actual": 1.14, "eps_predicted_from_prior4": 0.8543, "in_bottom_decile": false, "in_top_decile": true, "peer_rank_percentile": 0.9628, "period": "2025Q1", "price_response_20d_proxy": 0.024332, "surprise_direction": "beat", "surprise_relative": 0.3344}
{"assets_decile": 6, "cik": 6951, "composite_score": 0.0703, "eps_actual": 2.63, "eps_predicted_from_prior4": 1.2743, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.8146, "period": "2025Q1", "price_response_20d_proxy": 0.006138, "surprise_direction": "beat", "surprise_relative": 1.0639}
{"assets_decile": 7, "cik": 7084, "composite_score": -0.0765, "eps_actual": 0.61, "eps_predicted_from_prior4": -1.2567, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.3351, "period": "2025Q1", "price_response_20d_proxy": 0.023832, "surprise_direction": "beat", "surprise_relative": 1.4854}
{"assets_decile": 5, "cik": 7536, "composite_score": -0.1389, "eps_actual": 1.51, "eps_predicted_from_prior4": 2.3317, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.2833, "period": "2025Q1", "price_response_20d_proxy": -0.012592, "surprise_direction": "miss", "surprise_relative": -0.3524}
{"assets_decile": 7, "cik": 7789, "composite_score": -0.0332, "eps_actual": 0.59, "eps_predicted_from_prior4": 0.6667, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.4415, "period": "2025Q1", "price_response_20d_proxy": 0.014269, "surprise_direction": "miss", "surprise_relative": -0.115}
{"assets_decile": 7, "cik": 8670, "composite_score": 1.5608, "eps_actual": 3.06, "eps_predicted_from_prior4": 2.08, "in_bottom_decile": false, "in_top_decile": true, "peer_rank_percentile": 0.9947, "period": "2025Q1", "price_response_20d_proxy": 0.019733, "surprise_direction": "beat", "surprise_relative": 0.4712}
{"assets_decile": 0, "cik": 8818, "composite_score": -0.1245, "eps_actual": 2.09, "eps_predicted_from_prior4": 2.3667, "in_bottom_decile": false, "in_top_decile": false, "peer_rank_percentile": 0.2231, "period": "2025Q1", "price_response_20d_proxy": -0.005015, "surprise_direction": "miss", "surprise_relative": -0.1169}
```

## Reproduction

```
python3 seed/recompute.py                    # regenerate everything from cache
python3 seed/recompute.py --verify           # recompute SHA-256 of every output
```

Expected: idempotent — running twice yields byte-identical outputs (all output
SHA-256 stable across runs). Verified in Phase 1 authoring.

## Grounding snapshot

Full source of truth: `seed/grounding.yaml`. Contract binding: SHA-256
`103f591fb359bcbba17d91ec4c2bf702cd88d83c67dacffc3de99670a9e5ac6f`
(matches `seed/contract.approved`; temper gate OPEN as of 2026-07-31).

Canary tokens (repeated for redundancy - this file has 6 hits total = 3 tokens x 2
references each, satisfying leak-detection assay redundancy convention):

- `MEPHISTO_CANARY_SFM_2026_07_31_KEMUILEJ`
- `MEPHISTO_CANARY_SFM_2026_07_31_6HUOWVQR`
- `MEPHISTO_CANARY_SFM_2026_07_31_JD6DBT7E`
