# TRUTH — treasury_liquidity_provisioning_book

Judge-side reference ground truth for Phase 1 scaffold (T9/10 of finance-adjacent Framework B slate, 2026-08-01).
NEVER shipped to work image.

## Task identity

- task_id: `treasury_liquidity_provisioning_book`
- bundle_uuid: `9c463536-e514-5a50-9ff6-81ad513bae32`
- contract SHA-256 at Phase 0.5 sign: `d3ba087a3b8089345088586826a8aa68b6b001b7bf331cde5999affc091fc41d`
- hardness_catalog_digest: `543b83fb4ca8759cf6d8620f2914467b7e918bee74edab08a7dd3ac5d0096866`
- authored: 2026-08-01

=========================================================================
GOLDEN TRAJECTORY (ordered, executable, judge-side-only)
=========================================================================

STEP 1: Data fetch (judge-side inputs and endpoints)
- NY Fed Markets API: `https://markets.newyorkfed.org/api/rates/secured/sofr/last/{N}.json`
  (SOFR daily), `https://markets.newyorkfed.org/api/rp/reverserepo/all/results/last/{N}.json`
  (RRP operations). PD /get/ endpoint is gated (returns empty) — L5 defaults to 50% per grounding.
- fiscaldata.treasury.gov: DTS operating_cash_balance (TGA) + Debt-to-Penny v2.
- FRED series: SOFR, RRPONTSYD, DFF, IORB, DGS2, DGS10, DGS1MO, DGS3MO, DGS6MO, DGS1.
- TreasuryDirect: `/search` endpoint for bill terms 4W/8W/13W/26W/52W issuance calendar.
- home.treasury.gov daily curve for short-end yields (1M/3M/6M/1Y bill segments).
- Local cache dirs: `.cache/{ny_fed,fiscaldata,fred,treasurydirect,home_treasury}/`.
- Boundary split: TRAIN 2018-04-03..2024-12-31, TEST 2025-01-01..2026-07-31.
- State established: raw daily rate/repo/curve panels + weekly issuance calendar.

STEP 2: Feature construction (judge-side)
- Supply signals: `projected_weekly_issuance_b_next4w` (OLS trend slope over trailing 52w of
  weekly bill issuance) and `supply_direction_score` (signed z of next-4w vs trailing baseline),
  overlaid with TGA drawdown from fiscaldata DTS operating cash balance.
- Regime signals: SOFR-IORB spread, RRP acceptance amount, SOFR percentile dispersion
  computed against the 2018-04-03..2024-12-31 fit window.
- Demand signals: RRP counterparty count, RRP acceptance amount, IORB-RRP rate spread.
- State established: derived feature matrix aligned to daily observations.

STEP 3: Reference method (JUDGE-SIDE ONLY — 4-family opacity per PKW-FAMILIES §3 Framework B)
Stage A. TreasuryBillSupplyProjector (compute_bill_supply_projection). Fits baseline weekly
   bill issuance from TreasuryDirect auction calendar + OLS trend slope over trailing 52 weeks.
   Overlays TGA drawdown signal from fiscaldata DTS operating cash balance. Emits
   `projected_weekly_issuance_b_next4w` + directional `supply_direction_score`.
Stage B. RepoRegimeDetector (compute_repo_regime). Classifies each daily observation into
   4 states {deep_qt, normal, elevated_stress, extreme_stress} using SOFR-IORB spread +
   RRP acceptance amount + SOFR percentile dispersion. K=4 rule-based classifier with regime
   overrides on extreme thresholds; history statistics fit on 2018-04-03..2024-12-31.
Stage C. MoneyMarketDemandModel (compute_money_market_demand). Combines RRP counterparty
   count + RRP acceptance amount + IORB-RRP rate spread into a signed demand signal
   (positive = strong short-end liquidity demand). Fit on train baseline.
Stage D. RegimeConditionalLadderPositioner (compute_ladder_allocation). Allocates cash across
   6 bins {4W bill, 8W bill, 13W bill, 26W bill, O/N RRP, IORB proxy} per regime with
   rate-cycle overlay on supply direction + demand signal. Applies 2% turnover-discipline
   smoothing against prior allocation. Duration cap 0.35 years.
Realized return proxy (per-CUSIP prices FORBIDDEN by contract): return per bill bin computed
as convexity-adjusted duration × yield-change from home.treasury.gov short-end curve
(1M/3M/6M/1Y), plus coupon accrual per rebalance interval:

    return_bin(t) = -duration_bin × (yield_bin(t+1) - yield_bin(t))/100 + yield_bin(t)/100 × Δt/365

RRP and IORB legs use short-rate accrual with RRP rate from NY Fed Ops (fallback: FRED IORB/DFF).
Anchor: Fama 1984 (JFE) rate-carry proxy.

STEP 4: Backtest definition (deterministic)
- Test window: 2025-01-01..2026-07-31 sampled at 395 rebalance dates (daily coverage for
  reposition cadence) with 82 weekly rebalance anchors for lane L8 stability aggregation.
- Boundary split fixed at 2024-12-31 (all fit statistics derived from prior data only).
- No lookahead: each rebalance date uses only data available strictly before that date.

STEP 5: Per-lane score composition
| Lane | Points | Anchor / Metric |
|---|---:|---|
| L1 ladder_return | 20 | Sharpe of realized ladder return, cap 1.5 |
| L2 repo_regime_classification | 15 | 4-class accuracy on {deep_qt, normal, elevated_stress, extreme_stress} |
| L3 extreme_stress_detection | 15 | F1 on `extreme_stress` label vs judge-side truth |
| L4 bill_supply_direction_ranking | 10 | 3-class accuracy on {up, flat, down} of `supply_direction_score` |
| L5 ny_fed_pd_position | 10 | Default 50% (PD /get/ endpoint gated per grounding) |
| L6 money_market_pnl_proxy | 10 | Sharpe of demand-signal-driven PnL proxy |
| L7 anti_fabrication | 5 | Six field-level tolerances (±0.20) vs judge reference values |
| L8 cross_week_stability | 10 | 1 - min(1, var(weekly)/var_baseline), var_baseline=0.08 |
| liquidity_cycle_bonus | 10 | QT + extreme_stress precision ≥ 0.75 on judge-side conjunction |
Grader perturbation (opaque to solvers): `GRADER_SALT=TLP_2026_08_01_GRADER_CALIBRATION_SALT`,
`p_flip_regime=0.22`, `p_flip_stress=0.06`, `jitter_supply_dir=0.18`, `sigma_returns=0.00055`.
Measured reference score: **74.03/110** IN-BAND [65,78].

STEP 6: Reproduction protocol
```
python3 seed/build/treasury_liquidity_provisioning_book/recompute.py --regenerate-truth
python3 seed/build/treasury_liquidity_provisioning_book/recompute.py --self-score
python3 seed/build/treasury_liquidity_provisioning_book/recompute.py --control-ladder
```

=========================================================================
NEAR-MISS ROUTES the checkers reject (recorded alongside the intended route)
=========================================================================

Each route below is plausible from an agent's vantage but is rejected by a specific
checker or scoring lane. Why the rejection is correct is recorded so the intended
trajectory and its documented near misses live together in one artifact.

Route A. Substituting per-CUSIP bill prices (explicitly forbidden by contract) for the
  yield-curve-derived return proxy from home.treasury.gov short-end curve (1M/3M/6M/1Y)
  that grounding.yaml pins.
    Rejected by: L1 ladder_return (20pts, Sharpe cap 1.5) + L7 anti_fabrication (±0.20).
    Why the rejection is correct: contract explicitly forbids per-CUSIP prices; realized
      return per bill bin is computed as convexity-adjusted duration × yield-change from
      the short-end curve plus coupon accrual (return_bin(t) = -duration_bin ×
      (yield_bin(t+1) - yield_bin(t))/100 + yield_bin(t)/100 × Δt/365). Per-CUSIP
      substitution produces returns divergent from the reference's yield-curve derivation
      beyond L7 tolerance and collapses L1 Sharpe below the cap.

Route B. Naming any of the four reference method families (TreasuryBillSupplyProjector,
  RepoRegimeDetector, MoneyMarketDemandModel, RegimeConditionalLadderPositioner) or the
  four regime states {deep_qt, normal, elevated_stress, extreme_stress} in agent-visible
  solve.sh, imports, or comments.
    Rejected by: leak-detection assay (canary_bindings.opacity_boundary_family_names).
    Why the rejection is correct: PKW-FAMILIES section 3 Framework B places reference
      method-family selection judge-side. Naming the families or the regime cardinality
      leaks the architecture that makes per-regime ladder selection the intended hardness
      lever, collapsing the task from 'pick the right regime + ladder' to 'run the named
      stack' and voiding the four-family opacity boundary.

Route C. Fitting the repo regime detector with K=3 (tightening / neutral / easing) or
  K>=5 states instead of the K=4 rule-based classifier {deep_qt, normal, elevated_stress,
  extreme_stress} the reference uses on (SOFR-IORB spread, RRP acceptance amount, SOFR
  percentile dispersion).
    Rejected by: L2 repo_regime_classification (4-class acc, 15pts) + L3 extreme_stress_detection
      (F1, 15pts) + liquidity_cycle_bonus (QT + extreme_stress precision 0.75, 10pts).
    Why the rejection is correct: K=3 collapses elevated_stress and extreme_stress into a
      single tail state, missing the F1 differentiation L3 requires and pulling the bonus
      precision below 0.75; K>=5 fragments normal into low-confidence sub-states that
      degrade the 4-class accuracy anchor on L2. Only K=4 matches the SOFR-IORB signal
      cardinality that generated the extreme-stress event set.

Route D. Fabricating NY Fed Primary Dealer position data instead of defaulting to the 50%%
  neutral position that grounding.yaml pins per gap_ny_fed_pd_endpoint_gate (the PD /get/
  endpoint returned HTTP 400 during Phase 1 authoring and remains gated).
    Rejected by: L5 ny_fed_pd_position (10pts) + L7 anti_fabrication (±0.20, 6 fields).
    Why the rejection is correct: PD /get/ endpoint was gated during Phase 1 authoring;
      grounding pins 50%% neutral default and the judge-side recompute uses the same
      default. Fabricated PD position values diverge from the 50%%-default recompute
      beyond L7 tolerance on the ny_fed_pd_position field and collapse L5 to zero once
      the anti-fabrication reconciliation lands outside ±0.20.

Route E. Over-allocating to 26W bills (or 52W where allowed) and ignoring the ladder
  duration cap of 0.35 years across the six bins {b4w, b8w, b13w, b26w, rrp, iorb}.
    Rejected by: L1 ladder_return (Sharpe cap 1.5) + L6 money_market_pnl_proxy (10pts).
    Why the rejection is correct: 26W bills carry approximately 0.5-year duration and
      52W bills approach 1 year; unconstrained allocation into the long end blows the
      0.35-year ladder-average cap that turnover_penalty=0.02 is calibrated against.
      Duration-uncapped allocation drives L1 Sharpe below the cap once the yield-curve
      shock terms dominate and pulls L6 realized-return proxy below anchor.

Route F. Ignoring the grader perturbation model (GRADER_SALT=TLP_2026_08_01_GRADER_CALIBRATION_SALT,
  p_flip_regime=0.22, p_flip_stress=0.06, jitter_supply_dir=0.18, sigma_returns=0.00055)
  and self-reporting exact truth-value regime labels and supply-direction signals.
    Rejected by: L7 anti_fabrication (5pts, ±0.20 across 6 fields).
    Why the rejection is correct: L7 recomputes each lane metric on the judge side with
      GRADER_SALT applied to perturb regime labels, stress flags, and supply direction.
      Agents that self-report pre-perturbation exact truths land outside the ±0.20
      tolerance on all 6 anti-fab fields; the perturbation is a deliberate seam that
      distinguishes real regime-conditional ladder allocation from truth-echoing.

=========================================================================

## Held-out 2025-01-01..2026-07-31 test-panel summary

| Metric | Count |
|---|---:|
| Rebalance dates | 395 |
| Extreme-stress days flagged | 5 |
| Regime `deep_qt` days | 266 |
| Regime `elevated_stress` days | 1 |
| Regime `extreme_stress` days | 5 |
| Regime `normal` days | 123 |

## Sample (first 20 rebalance-date entries)

```jsonl
{"allocation": {"b13w": 0.25, "b26w": 0.17, "b4w": 0.18, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-02", "demand_signal": 0.02867, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.192663, "regime_label": "normal", "self_reported_certainty": 0.600779, "supply_direction": "up", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.17, "b4w": 0.18, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-03", "demand_signal": 0.033546, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.192663, "regime_label": "normal", "self_reported_certainty": 0.585036, "supply_direction": "up", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.17, "b4w": 0.18, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-06", "demand_signal": 0.044257, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.192663, "regime_label": "normal", "self_reported_certainty": 0.566527, "supply_direction": "up", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.17, "b4w": 0.18, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-07", "demand_signal": 0.090691, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.192663, "regime_label": "normal", "self_reported_certainty": 0.644199, "supply_direction": "up", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.219, "b4w": 0.131, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-08", "demand_signal": 0.136185, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.213394, "regime_label": "normal", "self_reported_certainty": 0.829151, "supply_direction": "down", "supply_projection_b": 332.0021, "weekly_rank_key": "2025-01-08", "weekly_supply_direction_ranking": "down"}
{"allocation": {"b13w": 0.25, "b26w": 0.17098, "b4w": 0.17902, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-09", "demand_signal": 0.169432, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.193078, "regime_label": "normal", "self_reported_certainty": 0.661001, "supply_direction": "up", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.17002, "b4w": 0.17998, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-10", "demand_signal": 0.148651, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.192672, "regime_label": "normal", "self_reported_certainty": 0.608356, "supply_direction": "up", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.17, "b4w": 0.18, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-13", "demand_signal": 0.139084, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.192663, "regime_label": "normal", "self_reported_certainty": 0.590637, "supply_direction": "up", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.17, "b4w": 0.18, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-14", "demand_signal": 0.185164, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.192663, "regime_label": "normal", "self_reported_certainty": 0.696607, "supply_direction": "up", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.219, "b4w": 0.131, "b8w": 0.2, "iorb": 0.07, "rrp": 0.13}, "date": "2025-01-15", "demand_signal": 0.264241, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.213394, "regime_label": "normal", "self_reported_certainty": 0.749564, "supply_direction": "down", "supply_projection_b": 332.0021, "weekly_rank_key": "2025-01-15", "weekly_supply_direction_ranking": "down"}
{"allocation": {"b13w": 0.201, "b26w": 0.31798, "b4w": 0.08102, "b8w": 0.151, "iorb": 0.168, "rrp": 0.081}, "date": "2025-01-16", "demand_signal": 0.314326, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.239385, "regime_label": "deep_qt", "self_reported_certainty": 0.721968, "supply_direction": "down", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.24902, "b26w": 0.22196, "b4w": 0.12902, "b8w": 0.19902, "iorb": 0.07196, "rrp": 0.12902}, "date": "2025-01-17", "demand_signal": 0.267483, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.214329, "regime_label": "normal", "self_reported_certainty": 0.673777, "supply_direction": "down", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.20098, "b26w": 0.318039, "b4w": 0.08098, "b8w": 0.15098, "iorb": 0.168039, "rrp": 0.08098}, "date": "2025-01-21", "demand_signal": 0.311327, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.239404, "regime_label": "deep_qt", "self_reported_certainty": 0.581125, "supply_direction": "down", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.24902, "b26w": 0.221961, "b4w": 0.12902, "b8w": 0.19902, "iorb": 0.071961, "rrp": 0.12902}, "date": "2025-01-22", "demand_signal": 0.256373, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.214329, "regime_label": "normal", "self_reported_certainty": 0.620268, "supply_direction": "down", "supply_projection_b": 332.0021, "weekly_rank_key": "2025-01-22", "weekly_supply_direction_ranking": "down"}
{"allocation": {"b13w": 0.24998, "b26w": 0.220039, "b4w": 0.12998, "b8w": 0.19998, "iorb": 0.070039, "rrp": 0.12998}, "date": "2025-01-23", "demand_signal": 0.240554, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.213827, "regime_label": "normal", "self_reported_certainty": 0.459231, "supply_direction": "down", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.25, "b26w": 0.220001, "b4w": 0.13, "b8w": 0.2, "iorb": 0.070001, "rrp": 0.13}, "date": "2025-01-24", "demand_signal": 0.293726, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.213817, "regime_label": "normal", "self_reported_certainty": 0.4469, "supply_direction": "down", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.201, "b26w": 0.318, "b4w": 0.081, "b8w": 0.151, "iorb": 0.168, "rrp": 0.081}, "date": "2025-01-27", "demand_signal": 0.317521, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.239394, "regime_label": "deep_qt", "self_reported_certainty": 0.426941, "supply_direction": "down", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.24902, "b26w": 0.22196, "b4w": 0.12902, "b8w": 0.19902, "iorb": 0.07196, "rrp": 0.12902}, "date": "2025-01-28", "demand_signal": 0.278422, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.214329, "regime_label": "normal", "self_reported_certainty": 0.444267, "supply_direction": "down", "supply_projection_b": 332.0021}
{"allocation": {"b13w": 0.24998, "b26w": 0.220039, "b4w": 0.12998, "b8w": 0.19998, "iorb": 0.070039, "rrp": 0.12998}, "date": "2025-01-29", "demand_signal": 0.260576, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.213827, "regime_label": "normal", "self_reported_certainty": 0.425432, "supply_direction": "down", "supply_projection_b": 332.0021, "weekly_rank_key": "2025-01-29", "weekly_supply_direction_ranking": "down"}
{"allocation": {"b13w": 0.25, "b26w": 0.220001, "b4w": 0.13, "b8w": 0.2, "iorb": 0.070001, "rrp": 0.13}, "date": "2025-01-30", "demand_signal": 0.252474, "extreme_stress_flag": false, "extreme_stress_probability": 0.5, "ladder_duration_years": 0.213817, "regime_label": "normal", "self_reported_certainty": 0.440787, "supply_direction": "down", "supply_projection_b": 332.0021}
```
