# TRUTH.md - p3gamma_sec_opmargin_expansion_book

<!-- GENERATED SECTION. DO NOT HAND-EDIT. Re-run seed/build/p3gamma_sec_opmargin_expansion_book/recompute.py <bundle_dir> to regenerate this file from grounding.yaml. -->

**task_id**: `p3gamma_sec_opmargin_expansion_book`
**family**: Framework A: outcome-anchored book

## Canary tokens

- `MEPHISTO_CANARY_P3GAMMASOM_20260808_A7B4C9D1`
- `MEPHISTO_CANARY_P3GAMMASOM_20260808_E2F8B5A3`
- `MEPHISTO_CANARY_P3GAMMASOM_20260808_6D1E4C87`

## Golden trajectory

**reference_method_name**: hindsight-perfect realized_opmargin_change_rank derived from post-outcome SEC EDGAR XBRL us-gaap:OperatingIncomeLoss / us-gaap:Revenues (ASC 606 tag union) at CY2026Q1 vs CY2025Q1 on a no-dimension consolidated basis, sector-residualized at SIC-2 (submissions API SIC first-2 digits), snapshot 2026-08-08 covering measure window CY2025Q1-CY2026Q1, rank-transformed by descending sector-relative Delta_pp with ties broken by cik ascending, joined to the 2799-cik inner-intersection universe (CY2026Q1 & CY2025Q1 OpIncomeLoss + Revenues both quarters, Revenues>0 both quarters, SIC known)

### Step 1

**action**: Read the 2799-cik graded universe from universe_p3gamma_2026.csv and the judge-private realized_opmargin_change_rank for every one of them from the hidden panel.

**state**: Graded universe enumerated with realized sector-relative Delta OpMargin fully known on the judge side.

**drift_survived**: Agent-visible copy of sec_xbrl_panel_stripped.csv carries op_income_loss_ cy2025q1 + revenues_cy2025q1 + revenues_cy2026q1 + opmargin_cy2025q1_level + prior_year_opmargin_level_rank + 8 raw sibling columns (gross_profit, ocf, assets 4-quarter I). Judge-side hidden_opmargin_change_realized.csv carries (cik, sector_relative_delta_opmargin_pp, realized_opmargin_change_rank) but score.py never emits realized magnitudes in production emission (VERIFIER OPACITY block; P3GAMMASOM_JUDGE_AUDIT env gate off in Harbor).

**checker**: L1 structural gate: every submitted cik must lie in universe; every universe member appears exactly once with a rank in [1, 2799].

### Step 2

**action**: For every graded cik, emit realized_opmargin_change_rank as prediction, honoring convention (1 = MOST margin EXPANSION = largest positive sector- relative Delta_pp; 2799 = MOST margin COMPRESSION = largest negative) and permutation constraint.

**state**: Prediction vector = realized reality identically; spearman = 1.0, top-K precision = 1.0, decile calibration MAE = 0.

**drift_survived**: Any prediction different from realized reality reduces spearman (L2 above threshold curve slope = LANE_L2/(1-L2_RHO_THRESHOLD) = 60), disturbs top-K precision (L3), disturbs bin-mean tightness (L4). Missing/extra cik, duplicate rank, out-of-range rank fails L1 structural gate and cascades total to 0.

**checker**: L2 reaches 30/30 (rho = 1.0 well above threshold 0.5); L3 reaches 25/25 (top-K identical); L4 reaches 20/20 (bin means track expected centers exactly); L5 reaches at most ~3/15 by empirical cross-sibling partial correlation bounds in Nissim 2023 + Amir/Kama/Livnat 2011 literature.

### Step 3

**action**: Write submission/opmargin_change_ranks.csv (2799 data rows + 1 header, bijective, rank permutation of {1..2799}) to /home/workspace/submission/ opmargin_change_ranks.csv.

**state**: Single graded artifact on the path the verifier reads.

**drift_survived**: Missing/wrong header, row-count off from 2799, duplicate cik, missing/ extra cik, rank outside [1,2799], duplicate rank each zeroes total via L1 cascade. No separate policy re-run.

**checker**: L1 structural gate.

## Near-miss routes

- **route**: The 4-sibling DuPont ensemble reference solver preserved at solution/ reference_solver.py (weighted composite W_GM=0.45 * gm_rank + W_ATO=0.10 * ato_rank + W_OCFM=0.25 * ocfm_rank + W_REV=0.20 * revgrowth_rank; each sibling raw value sector-residualized at SIC-2 then ranked descending; neutral midpoint (N+1)/2 fallback for CIKs where a sibling raw signal is missing from the visible panel).
  **rejection_reason**: Legitimate decision-time method reflecting analyst-realistic effort building on the agent-visible sec_xbrl_panel_stripped.csv (GP+OCF+Assets+ Revenues+SIC-2); lands in [24, 44] band (measured 27.942 on 2026-08-08). Cannot reach hindsight-perfect because (a) L5 partial correlations cap by Nissim 2023 + Amir-Kama-Livnat 2011 literature bounds and (b) L2 threshold curve at rho=0.5 gates raw Spearman signal below 0.5.

- **route**: Predict prior_year_opmargin_level_rank persistence.
  **rejection_reason**: Persist-of-boundary MUST land below 24 (Stage-2b HARD KILL GATE). Screen measured spearman(prior_year_opmargin_level_rank, realized_opmargin_change_ rank) = +0.248 (requirements/PKW-FAMILIES.md §3 wave 2026-07-18). Under rubric (L2_RHO_THRESHOLD=0.5, L5 partial correlation controlling for prior_year_opmargin_level_rank), persist earns 0 on L2 (rho below threshold), essentially 0 on L5 (partial(agent, sibling_i | boundary) = 0 by construction when agent = boundary). Measured persist total on 2026-08-08: 14.012, 9.988 pts below KILL bar (10-pt headroom).

- **route**: Predict single constant rank (e.g. midpoint 1400) for every cik.
  **rejection_reason**: Fails L1: not permutation, 2799 duplicate ranks. Total = 0 via cascade.

- **route**: Predict uniformly-random permutation of {1..2799}.
  **rejection_reason**: Passes L1. L2 rho ~ 0 below threshold -> 0 pts. L3 top-K precision ~ K/N = 0.036. L4 tightness ~ 0. L5 partial correlations ~ 0. Total ~ 10.25 (measured 2026-08-08 seed=20260808).

- **route**: Use single sibling measure alone (e.g. rank by Delta GM only).
  **rejection_reason**: Bounded by single-sibling correlation to realized (~0.30-0.45 range). Under threshold curve L2 grants 0-8 pts at most. Expected total 15-22, above persist but below reference band, illustrates value of ensemble.

- **route**: Hand-tune CSV after inspecting verifier feedback without coherent method.
  **rejection_reason**: Judge emits ONLY 5 lane scalars + structural feedback + submitted distributional shape (min, max, mean, stddev of submitted ranks). No per-cik hit list, no ground-truth cik, no realized value, no rho scalar, no per-sibling partial. L4 is real-valued MAE-normalized (metric-continuous), L3 is precision-at-K aggregate over K-item set, L5 is mean of partial correlations. Best-of-N gain bounded by calibration-search on N continuous weights against 5 aggregate scalars; no per-item bits leak. See §15 declaration in mephisto_extensions.

## Lane reconciliation

### L1 structural (10 pts)

- satisfied_by_steps: [1, 3]
- detail: Step 1 fixes universe, step 3 places CSV. Structural pass grants 10; any structural failure cascades total to 0. Formula binding: p3gamma_lib.structural_check() reasons list must be empty.

### L2 spearman_rank_threshold (30 pts)

- satisfied_by_steps: [2]
- detail: Perfect rank agreement -> rho = 1.0, lane clamps at 30 via threshold curve. Formula binding: p3gamma_lib.score_l2_rank_correlation = LANE_L2_POINTS * max(0, (rho - L2_RHO_THRESHOLD) / (1 - L2_RHO_THRESHOLD)) with L2_RHO_THRESHOLD=0.5. Persist-of-boundary shortcuts (rho ~ +0.248) earn 0.

### L3 top_k_worst (25 pts)

- satisfied_by_steps: [2]
- detail: Top-K by prediction (largest ranks = most-compression cohort) and by realized are identical when prediction = realized; precision-at-K = 1.0, lane clamps at 25. Formula binding: p3gamma_lib.score_l3_topk_worst = LANE_L3 * precision_at_k(top_k_ids(agent, K), top_k_ids(realized, K)). Aggregate over K-item set (K=100), does not invert to per-item ground-truth membership.

### L4 decile_calibration_tightness (20 pts)

- satisfied_by_steps: [2]
- detail: 10 equal-count bins ordered by agent rank; mean(realized) per bin tracks expected_center exactly when agent=realized. Formula binding: p3gamma_lib.score_l4_decile_calibration = LANE_L4 * max(0, 1 - sum|bin_mean_realized - bin_expected_center| / MAE_naive). Only saturates for tight bin-level calibration, not for weak monotonic signal.

### L5 cross_sibling_consistency (15 pts, bonus)

- satisfied_by_steps: [2]
- detail: Partial rank correlation of agent vs each of 4 siblings (delta_gross_margin_ rank, delta_asset_turnover_rank, delta_ocf_margin_rank, revenue_growth_rank) after controlling for prior_year_opmargin_level_rank. Formula binding: p3gamma_lib.score_l5_cross_condition_consistency = LANE_L5 * mean(max(0, partial_spearman(agent, sibling_i | L5_CONTROL_COLUMN))). Persist-of-boundary shortcuts collapse to 0 by construction (partial when agent=boundary is 0). Empirical L5 ceiling at hindsight is ~3/15 per Nissim 2023 + Amir/Kama/Livnat 2011 cross-sibling correlation literature bounds; measured 2.610/15 on 2026-08-08 for oracle route.

### anti-fabrication (veto, no points)

- satisfied_by_steps: [3]
- detail: Deliverable is a permutation with exact universe bijection; L1 structural gate fully captures anti-fabrication surface. A permutation cannot lie about its own distribution.

## Oracle reconciliation

- invoked_at: 2026-08-08T18:00:00Z
- method: Score numbers below measured by running emitted solution/ artifacts through in-process p3gamma_lib.score_all against seed/build/p3gamma_sec_opmargin_ expansion_book/hidden_opmargin_change_realized.csv + hidden_sibling_ranks.csv, with /home/workspace/submission/opmargin_change_ranks.csv path pointed at pre-computed dataset/<uuid>/solution/oracle_opmargin_change_ranks.csv (byte-copied by solve.sh under Harbor -a oracle), P3GAMMASOM_JUDGE_AUDIT unset (redacted emission).
- work_image_ref: `426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.work.p3gamma_sec_opmargin_expansion_book:phase1-222826dbd90d@sha256:4b3b13a4f5d85723322dbb94d811ed4964c228c8ff5af1b511e303d6e4bb4db2`
- judge_image_ref: `426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.judge.p3gamma_sec_opmargin_expansion_book:phase1-222826dbd90d@sha256:8e2d0a671fa5e1a391d31dbaf3dfe0207c4224ef2845bed13f2b4bee702a5640`
- total_score_raw: 87.61
- total_score_normalized: 0.8761
- full_reward_threshold: 0.95
- full_reward_reached: False

### per_lane_measured

- L1_structural: {'score': 10.0, 'max': 10, 'satisfied_by': ['step_1', 'step_3']}
- L2_spearman_rank_threshold: {'score': 30.0, 'max': 30, 'satisfied_by': ['step_2']}
- L3_top_k_worst: {'score': 25.0, 'max': 25, 'satisfied_by': ['step_2']}
- L4_decile_calibration_tightness: {'score': 20.0, 'max': 20, 'satisfied_by': ['step_2']}
- L5_cross_sibling_consistency: {'score': 2.61, 'max': 15, 'satisfied_by': ['step_2']}

**score_gap_analysis**: Oracle reaches 87.610 not 100.000: the 12.390-pt gap sits entirely in L5. L5 measures partial rank correlation of agent-rank vs each of 4 siblings (delta_gross_margin_rank, delta_asset_turnover_rank, delta_ocf_margin_rank, revenue_growth_rank) after controlling for prior_year_opmargin_level_rank. Even at hindsight-perfect, cross-sibling partial correlations after removing prior-level component sit around 0.15-0.25 per Amir-Kama-Livnat 2011 + Nissim 2023 (OPM less persistent than ATO; OPM/ATO conditionally negatively correlated). L5 bonus lane bounded by empirical cross-sibling correlation ceilings, not defect.

