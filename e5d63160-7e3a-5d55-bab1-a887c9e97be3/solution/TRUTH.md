
============================================================================
GOLDEN TRAJECTORY (ordered, executable, judge-side-only)
========================================================

STEP 1: Data fetch (executable via seed/build/fdic_bank_capital_projection_book/_fetch_data.py or recompute.py --regenerate-fixtures).

FDIC BankFind Financials quarterly panel:
  Endpoint template (paginated limit=1000):
    https://banks.data.fdic.gov/api/financials?filters=REPDTE:YYYYMMDD&limit=1000&offset={n}&fields=<field-list></field>
  Boundary split at REPDTE=20250101:
    - REPDTE < 20250101 → environment/attachments/financials_train.csv (agent-visible)
    - REPDTE in [20250101, 20260101) → tests/hidden_test_data/financials_test.csv (HIDDEN)
  Train quarters: 24 (2019Q1..2024Q4).  Test quarters: 4 (2025Q1..Q4).

FDIC BankFind Institutions:
  Endpoint template: https://banks.data.fdic.gov/api/institutions?filters=ACTIVE:1&limit=1000&offset={n}
  Full active-insured universe as of fetch date; snapshot stable across the 2025 test window.

FRED clean series (US Government works, no license):
  Endpoint template: https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES}
  Series: DGS10, DFF, T10Y2Y, UNRATE, GDPC1 (NEVER SP500 or VIXCLS — licensed).
  Merge on date; forward-fill weekends/holidays.

STEP 2: Feature construction (judge-side).
  Per-institution size bucket:
    community (<$1B), mid ($1B-$10B), regional ($10B-$100B), large (>$100B).
  Per-observation capital ratios:
    IDT1CER (CET1 %), IDT1RWAJR (Tier-1 risk-based %),
    RBC1AAJ (Tier-1 leverage %), RBCRWAJ (Total risk-based %).
  Earnings: NIMYQ, ROAQ, ROEQ.
  Tail: NPERFV (nonperforming assets/assets %), NCLNLSR (net charge-offs/loans %),
        LNATRESR (loan-loss reserve %).
  Macro feature vector (quarter-end lookback):
    [DFF, DGS10, T10Y2Y, UNRATE, DFF_change_4q, T10Y2Y_slope_1q].
  PCA zone (12 CFR § 6.4):
    well_capitalized: total ≥10% AND tier1_rwa ≥6% AND tier1_leverage ≥5%
    adequately_capitalized: ≥8/4.5/4
    undercapitalized: ≥6/4/3
    significantly_under: total ≥2%
    critically_under: total <2%

STEP 3: Reference method (JUDGE-SIDE ONLY — method names never appear
        in agent-visible surfaces per PKW-FAMILIES section 3 Framework B).

  Stage A. PeerGroupPercentileRegression: per-size-bucket per-metric AR(1)
    projector anchored on empirical bucket-median. AR(1) phi fit as median
    of per-institution phis over pre-2025 quarterly panel.
  Stage B. MacroConditionalCapitalTrajectory: 3-regime scipy-only Gaussian
    mixture on macro feature vector (k-means-init, forced distinct labels
    via cluster-center sort on DFF_change_4q). Regime-conditional metric-drift
    table (per-bucket per-metric median delta) applied additively.
  Stage C. ConcentrationRiskFactorLoadings: per-bucket 2-factor eigen-decomposition
    of standardized [NPERFV, NCLNLSR, LNATRESR] correlation matrix. Per-CERT
    factor scores decayed 0.85 per quarter and back-projected via loadings.
  Stage D. CapitalBufferRegimeDetector: per-bucket 3-cluster K-means on
    [IDT1CER, IDT1RWAJR, RBC1AAJ, RBCRWAJ, EQV] normalized within bucket;
    cluster centers sorted on IDT1RWAJR and mapped canonically to
    [buffer_critical, buffer_eroding, buffer_comfortable]. Regime label
    conditions a small capital-buffer tilt on the four projection ratios.

STEP 4: 2025 per-institution per-quarter backtest definition (deterministic).
  N = 4539 unique test institutions (community: 3483, large: 32, mid: 893, regional: 131) x 4 quarters
  Aggregation: per-observation score across 6 magnitude lanes + L7 anti-fab
  gate + L8 cross-size-bucket stability + PCA-zone-transition bonus.

STEP 5: Per-lane score composition (deterministic Python subprocess).
  L1 capital_ratio_projection    25 pts  MAE across 4 capital ratios in pp (0.4pp full / 3.5pp zero)
  L2 earnings_projection         15 pts  MAPE across NIM + ROA + ROE (0.10 full / 0.50 zero)
  L3 tail_risk_control           15 pts  MAE across NPERFV + NCLNLSR in pp (0.10pp full / 1.0pp zero)
  L4 pca_zone_classification     10 pts  categorical accuracy (0.80 full / 0.20 zero)
  L5 asset_growth_projection     10 pts  MAE on ASSET growth (0.010 full / 0.080 zero)
  L6 deposit_stability           10 pts  MAE on DEPDOM growth (0.012 full / 0.080 zero)
  L7 anti_fabrication             5 pts  self-report vs judge-recompute; HARD VETO zeros L1+L2 on violation
  L8 cross_size_bucket_stability 10 pts  cross-bucket variance-and-mean of L1 scores
  PCA-zone-transition bonus  +10 pts  detected quarter-over-quarter zone shifts
                                       vs true_pca_zone_events.json within 1-quarter tolerance.

STEP 6: Reproduction protocol.
  From this file, an authorized reviewer can rebuild the bundle whose
  reference-through-grader self-score lands in the contract target band
  [65, 78] by executing (in a Python venv with numpy/pandas/scipy):

    python3 seed/build/fdic_bank_capital_projection_book/recompute.py 
        --regenerate-fixtures    # optional; re-fetches FDIC+FRED if data drifted
    python3 dataset/e5d63160-7e3a-5d55-bab1-a887c9e97be3/solution/bank_capital_projection_reference.py 
        --train 
        --data dataset/e5d63160-7e3a-5d55-bab1-a887c9e97be3/environment/attachments/financials_train.csv 
        --macro dataset/e5d63160-7e3a-5d55-bab1-a887c9e97be3/environment/attachments/macro_indicators_train.csv 
        --state dataset/e5d63160-7e3a-5d55-bab1-a887c9e97be3/solution/reference_state.json
    python3 seed/build/fdic_bank_capital_projection_book/recompute.py --self-score
