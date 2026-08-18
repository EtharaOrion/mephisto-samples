# TRUTH - sec_leverage_trajectory_projection_book

Judge-side reference
ground truth for Phase 1 scaffold (T7/10 of the finance-adjacent Framework B
slate, 2026-07-31). NEVER shipped to work image.

## Task identity

- task_id: `sec_leverage_trajectory_projection_book`
- bundle_uuid: `d3cd6658-d997-5f26-89e3-97e5443046b4`
- contract SHA-256 at Phase 0.5 sign: `cb68e81c405253bb6aa8642eb0aad9d3b7e063f049bc5f9c45876b131793e3e5`
- hardness_catalog_digest: `543b83fb4ca8759cf6d8620f2914467b7e918bee74edab08a7dd3ac5d0096866`
- authored: 2026-07-31

=========================================================================
GOLDEN TRAJECTORY (ordered, executable, judge-side-only)
=========================================================================

STEP 1: Data fetch (judge-side inputs and endpoints)
- SEC EDGAR XBRL frames (5 req/s cap).
  9 concepts fetched: Assets (universe anchor), Liabilities (primary numerator),
  StockholdersEquity, LongTermDebt (+ fallback aliases LongTermDebtNoncurrent,
  LongTermDebtAndCapitalLeaseObligations), ShortTermBorrowings (sparse),
  CashAndCashEquivalentsAtCarryingValue, InterestExpense (subset — feeds L5
  coverage_direction only when present), OperatingIncomeLoss, NetIncomeLoss.
- Universe: top-1000 filers by Assets per quarter (T6 precedent; cross-quarter
  entry/exit flagged for survivorship-bias mitigation).
- FRED rate anchors (T7 shift from T6's UNRATE-only): DGS10 (daily 10Y
  Treasury), DGS2 (daily 2Y), DFF (daily effective Fed Funds), T10Y2Y (daily
  curve slope 10Y - 2Y). Cache dir `.cache/fred/`.
- Boundary split: TRAIN CY2018Q1..CY2024Q4 (28 quarters × 1000 = 28000
  filer-quarter observations); TEST CY2025Q1..CY2026Q1 (5 quarters × 1000 =
  5000 filer-quarter observations). Pre-2018 excluded per ASC 842 lease-standard
  shift (2019) + ASC 606 revenue-recognition regime shift (2018).
- Per-issuer equity price data FORBIDDEN by contract (Stooq/Yahoo/Bloomberg
  banned per MUST-NOT-DO doctrine; FRED has no per-CIK equity series).
- State established: raw XBRL balance-sheet + income-statement panel + FRED
  rate anchors + top-1000 universe roster per quarter.

STEP 2: Feature construction (judge-side)
- Per-filer per-quarter trajectory slopes over trailing 5-quarter window:
  - deleverage_slope     = -slope(Liabilities/Assets vs quarter-index)
  - net_debt_shrink      = -slope((LongTermDebt+ShortTermBorrowings-Cash)/Assets)
  - coverage_improvement = +slope(OperatingIncomeLoss/InterestExpense) [SUBSET]
- Each slope cross-sectionally z-scored per quarter. Composite = mean non-null
  z-scored slopes; requires ≥ 2 non-null components. Higher composite = stronger
  deleveraging + coverage-improving trajectory = higher predicted price response.
- Peer-group substitute: Assets deciles (SIC codes absent from EDGAR frames
  responses; T6 precedent). Per quarter, filers sorted by Assets ascending,
  partitioned into 10 buckets.
- State established: per-filer per-quarter feature matrix with 3 z-slopes +
  composite + peer/global rank percentiles + `delta_liab_over_assets_yoy`.

STEP 3: Reference method (JUDGE-SIDE ONLY — 4-family opacity per PKW-FAMILIES §3 Framework B)
Stage A. CapitalStructureTrajectoryProjector. Emits the 3 z-scored slopes above
   + composite score per filer per quarter.
Stage B. PeerLeverageDeltaRankRegressor. Emits `peer_rank_percentile` within
   Assets decile, `global_rank_percentile` across universe, and
   `delta_liab_over_assets_yoy` (realized YoY change in Liabilities/Assets)
   for L4 scoring.
Stage C. RefinancingRiskSurpriseDetector. Overlays FRED DGS10 trailing-4Q
   change onto per-filer LTD/Assets percentile within Assets-decile peer group:
   - `risk_up`   if Δ-4Q DGS10 > +25 bps AND filer LTD/Assets percentile within decile ≥ 0.6
   - `risk_down` if Δ-4Q DGS10 < -25 bps AND filer LTD/Assets percentile ≤ 0.4
   - `neutral`   otherwise
Stage D. NetDebtRegimePositioner. Position weight per filer per quarter:
   `+1/n_long` if global_rank_percentile ≥ 0.90 (top decile of deleveragers);
   `-1/n_short` if ≤ 0.10 (bottom decile / worst leveragers); `0` otherwise.
   Rate-cycle overlay: `risk_down` boosts long side +10%; `risk_up` boosts
   short side +10%. Book dollar-neutral by base construction.
Realized return proxy (per-issuer equity prices FORBIDDEN by contract):
capital-structure-derived formula

    price_response_20d = 0.03 × sign(composite) × min(|composite|, 2.0) / 2.0
                       + hash-seeded uniform(-0.02, +0.02)

where noise seed is `int.from_bytes(sha256(f'{cik}|{period}').digest()[:8], 'big')`.
Anchor α = 0.03 grounded in Baker-Wurgler 2002 JF ("Market Timing and Capital
Structure", ~1-3% excess return per positive deleveraging trajectory) and
Frank-Goyal 2009 JFE capital-structure survey (cross-sectional IC 0.30-0.50
range for balance-sheet Δ-metrics).

STEP 4: Per-lane score composition
| Lane | Points | Anchor / Metric |
|---|---:|---|
| L1 composite_trajectory_rank_correlation | 20 | Spearman IC of composite vs realized price_response_20d_proxy, anchor_full 0.50 |
| L2 refinancing_risk_direction | 15 | 3-class accuracy on {risk_up, neutral, risk_down} |
| L3 extreme_mover_detection | 15 | F1 on top-decile ∪ bottom-decile flag vs judge-side truth |
| L4 delta_liabilities_growth_ranking | 10 | Spearman of `delta_liab_over_assets_yoy` rank, anchor_full 0.70 |
| L5 interest_coverage_direction | 10 | 3-class accuracy on {up, flat, down} of coverage_improvement (subset filers with InterestExpense present) |
| L6 composite_position_pnl | 10 | Sharpe of dollar-neutral top/bottom decile PnL, cap 5.0 |
| L7 anti_fabrication | 5 | Five field-level tolerances (±0.15) vs judge reference values |
| L8 cross_quarter_stability | 10 | 1 - min(1, var(per-quarter)/var_baseline), var_baseline=0.10 |
| leverage_cycle_bonus | 10 | CY2025 top-decile deleveragers precision ≥ 0.85 on judge-side conjunction |

Grader perturbation (opaque to solvers; T7 first-adoption of this pattern):
`GRADER_SALT=SLT_2026_07_31_GRADER_CALIBRATION_SALT`, `p_flip_refi=0.28`,
`jitter_scale_extremes=0.045`, `sigma_price_shock_pnl=0.11`,
`sigma_price_shock_l1=0.05`.
Measured reference score: **70.49/110**.

STEP 5: Reproduction protocol
```
python3 seed/build/sec_leverage_trajectory_projection_book/recompute.py --regenerate-truth
python3 seed/build/sec_leverage_trajectory_projection_book/recompute.py --verify
```
Expected: idempotent — running twice yields byte-identical outputs.
Phase 2 `--regenerate-truth` CLI added 2026-08-02 to replace the stale
`seed/recompute.py` reference from the pre-layout-migration era.

=========================================================================
NEAR-MISS ROUTES the checkers reject (recorded alongside the intended route)
=========================================================================

Each route below is plausible from an agent's vantage but is rejected by a specific
checker or scoring lane. Why the rejection is correct is recorded so the intended
trajectory and its documented near misses live together in one artifact.

Route A. Substituting equity-price panels, credit-spread feeds, or any commercial
  fundamentals vendor (yfinance, quandl, Bloomberg) for the SEC EDGAR XBRL frames
  that grounding.yaml pins across nine concepts (Assets, Liabilities,
  StockholdersEquity, LongTermDebt + aliases, ShortTermBorrowings, CashAndCash-
  EquivalentsAtCarryingValue, InterestExpense, OperatingIncomeLoss, NetIncomeLoss).
    Rejected by: L1 composite_trajectory_rank_correlation (20pts, anchor_full=0.50)
      + L4 delta_liabilities_growth_ranking (10pts Spearman, anchor_full=0.70) +
      L7 anti_fabrication (5pts, ±0.15 across 5 fields).
    Why the rejection is correct: contract binds capital-structure fundamentals to
      SEC EDGAR XBRL as the single source of truth; vendors report distinct filer
      universes, different LTD alias resolution, and different InterestExpense
      subsetting. Their Liabilities/Assets ratios diverge from XBRL-derived
      trajectories, driving L1 Spearman below the 0.50 anchor, degrading L4 rank
      correlation on the delta-liabilities slope, and pushing L7 self-reported
      metrics outside the ±0.15 tolerance versus judge-side XBRL recompute.

Route B. Naming any of the four reference method families (CapitalStructure-
  TrajectoryProjector, PeerLeverageDeltaRankRegressor, RefinancingRiskSurprise-
  Detector, NetDebtRegimePositioner) in agent-visible solve.sh, imports, comments,
  or docstrings.
    Rejected by: leak-detection assay (canary_bindings.opacity_boundary_family_names).
    Why the rejection is correct: PKW-FAMILIES section 3 Framework B places the
      four family names judge-side. Naming them leaks the trajectory-slopes +
      refinancing-surprise + regime-conditional-position architecture that makes
      reconciling per-filer capital-structure slope with the rate-cycle-conditioned
      book the intended hardness lever, collapsing the task from 'project the
      trajectory + score the surprise + position by regime' to 'run the named
      stack' and voiding the four-family opacity boundary.

Route C. Fitting the capital-structure composite over a 3-quarter or 7-quarter
  trailing window instead of the 5-quarter window that grounding.yaml pins for
  the three trajectory slopes (deleverage_slope = -slope(Liabilities/Assets),
  net_debt_shrink = -slope((LTD+ST-Cash)/Assets), coverage_improvement =
  +slope(OpInc/InterestExpense) [SUBSET]).
    Rejected by: L1 composite_trajectory_rank_correlation + L3 extreme_mover_
      detection (15pts F1) + leverage_cycle_bonus (10pts, CY2025 top-decile
      deleveragers precision ≥ 0.85).
    Why the rejection is correct: 5 quarters spans one refi-cycle wavelength for
      the typical large filer and dampens single-quarter accrual noise; 3-quarter
      windows over-index on the most recent print and mislabel transient
      restatements as trajectory shifts, while 7-quarter windows dilute the
      current-year deleveraging signal that CY2025 top-decile precision requires.
      Only the 5-quarter cadence produces the ≥ 0.85 precision on top-decile
      deleveragers that the leverage_cycle_bonus grades.

Route D. Computing L5 interest_coverage_direction across the full 5000 test-panel
  filer-quarters instead of respecting the SUBSET requirement that grounding.yaml
  pins for filers with InterestExpense ≠ null (approximately 508 observations of
  the 5000 test panel).
    Rejected by: L5 interest_coverage_direction (10pts SUBSET grading) + L7
      anti_fabrication (5pts).
    Why the rejection is correct: InterestExpense is a sparse XBRL concept
      (n≈1050 across the full universe; the SUBSET restriction on L5 excludes
      filers that never report the concept). Grading directional labels for
      filers without an interest-expense series against imputed zeros injects
      thousands of spurious up/flat/down classifications that don't reconcile
      with the judge-side SUBSET recompute, driving L5 to zero and pulling
      self-reported metrics outside the L7 ±0.15 tolerance on the interest-
      coverage field.

Route E. Positioning long/short from the top and bottom composite deciles without
  applying the rate-cycle overlay (+10%% long weight when refi_direction=risk_down,
  +10%% short weight when refi_direction=risk_up) that grounding.yaml pins over
  the base +1/n_long (composite ≥ 0.90) and -1/n_short (composite ≤ 0.10) book.
    Rejected by: L6 composite_position_pnl (10pts Sharpe cap 5.0) + leverage_cycle_
      bonus.
    Why the rejection is correct: the rate-cycle overlay is the seam that converts
      static composite-decile positioning into refinancing-risk-conditional
      exposure — long deleveragers get amplified when Δ4Q DGS10 < -25bps (risk_down)
      and short leveragers get amplified when Δ4Q DGS10 > +25bps (risk_up). Static
      positioning underweights the CY2025 rate cycle where DGS10 dispersion drove
      the top-decile deleveraging outperformance, driving L6 Sharpe below the 5.0
      cap and missing the top-decile-deleveragers precision that leverage_cycle_
      bonus requires.

Route F. Ignoring the grader perturbation model (GRADER_SALT=SLT_2026_07_31_
  GRADER_CALIBRATION_SALT, p_flip_refi=0.28, jitter_scale_extremes=0.045,
  sigma_price_shock_pnl=0.11, sigma_price_shock_l1=0.05) and self-reporting exact
  truth-value refi labels or exact PnL series.
    Rejected by: L7 anti_fabrication (5pts, ±0.15 across 5 fields).
    Why the rejection is correct: L7 recomputes each lane metric on the judge side
      with GRADER_SALT applied to flip 28%% of refi labels, jitter the top-decile
      extreme classifications by 4.5%%, and shock the L1 rank correlation and L6
      PnL with sigma_price_shock_l1=0.05 and sigma_price_shock_pnl=0.11. Self-
      reporting pre-perturbation exact truths lands outside the ±0.15 tolerance
      on all 5 anti-fab fields; the perturbation is a deliberate seam that
      distinguishes real trajectory-based composite construction from truth-echoing.

=========================================================================

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
