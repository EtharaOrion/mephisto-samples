# TRUTH.md - p6zeta_zero_one_ip_solver_from_scratch_v2

<!-- GENERATED SECTION. DO NOT HAND-EDIT. Re-run solution/recompute.py <bundle_dir> to regenerate this file from grounding.yaml. -->

**task_id**: `p6zeta_zero_one_ip_solver_from_scratch_v2`
**family**: Framework A: from-scratch combinatorial-optimization solver

## Canary tokens

- `MEPHISTO_CANARY_P6Z2_20260905_7C1E9A40`
- `MEPHISTO_CANARY_P6Z2_20260905_D3B872F1`
- `MEPHISTO_CANARY_P6Z2_20260905_5E0F4C9B`

## Golden trajectory

**reference_method_name**: v2 of p6zeta. Same from-scratch primal-simplex LP relaxation with Big-M artificials plus best-first branch-and-bound reference solver as v1 (calibration artifact only). The judge loads N=90 hidden instances from hidden_benchmarks/*.ip.json plus hidden_optima.json (author-computed via scipy.optimize.milp HiGHS backend with mip_rel_gap=0 and a 300 s cap; only instances HiGHS PROVED optimal were admitted, chosen hardest-first by HiGHS wall time within each family), invokes the agent's ./solve per instance under a 60-second timeout with 16 parallel workers each pinned to one cpu, reads the agent-written l3_ranking.json for L3 top-K=8 precision against the HiGHS wall-time ranking of the 30-instance multi-dimensional-knapsack cohort, re-runs ./solve on a fixed 21-instance subset (first 3 of each family) under seven deterministic perturbations for L5, un-perturbs the outputs, and grades through the 5-lane rubric (L1 10, L2 30, L3 25, L4 20, L5 15) with the KILL band. v2 exists because the v1 hidden set was solved to gap 0 on all 90 instances by the first frontier run within 40 minutes and v1's judge never executed the L5 sweep.

### Step 1

**action**: Judge loads /home/workspace/scoring/data/hidden_benchmarks/*.ip.json and confirms 90 files present (60 primary plus the 30-instance multi-dimensional-knapsack L3 cohort), then loads hidden_optima.json keyed by instance_id with status=optimal, objective_value, variables and solver_wall_seconds (HiGHS wall time) for every instance.

**state**: universe pinned

**drift_survived**: instance-order drift, generator-seed drift

**checker**: score.py N_UNIVERSE-check plus lib.validate_instance_json

### Step 2

**action**: Judge runs ./build.sh once, then invokes ./solve <instance> per hidden instance under `timeout 60s taskset -c <cpu>` from 16 parallel lanes (lane w takes every 16th instance and is pinned to cpu w), capturing stdout to scoring/outputs/<instance_id>.out.json and stderr (BEST ts= obj= tokens) to scoring/traces/<instance_id>.log.

**state**: submissions collected

**drift_survived**: solve-wall-time jitter, output field-order drift, lane-to-cpu mapping

**checker**: lib.validate_output_json plus lib.feasibility_violations

### Step 3

**action**: If the submission wrote /home/workspace/submission/l3_ranking.json (a JSON list of instance ids, hardest first, written by the solver at evaluation time since submit_paths cannot ship it), score.py takes its first K=8 ids from the multi-dimensional-knapsack cohort and computes precision against the oracle top-8 by hidden_optima.json solver_wall_seconds descending. Absent file => L3 = 0.

**state**: L3 ranking read

**drift_survived**: ranking-file absence, ids outside the cohort

**checker**: lib.top_k_precision over hidden_optima.json solver_wall_seconds

### Step 4

**action**: Judge runs perturb_v2.py make to build seven perturbed variants of a fixed subset: the first lib.L5_SUBSET_PER_FAMILY=3 instances of each family in sorted id order (21 instances). Perturbations: variable_order_within_constraint (one column permutation applied to objective and all rows), constraint_reorder, coefficient_common_scale (each row and rhs times an integer in 2..9), instance_id_salt_rewrite (HMAC suffix), json_whitespace_reformat (indent=4), output_json_field_order (keys reordered in the instance and in each constraint object), output_json_trailing_whitespace (trailing blank lines). Each variant cohort is solved with the same 16-lane pinned runner; perturb_v2.py restore maps outputs back (instance_id restored, variables un-permuted) into scoring/perturb/<perturbation>/<instance_id>.out.json.

**state**: perturbation sweep complete on the 21-instance subset

**drift_survived**: perturbation-order drift, whitespace/field-order drift, salted ids, permuted variables

**checker**: tests/perturb_v2.py restore + lib.perturbation_robustness_score (credit-retained form)

### Step 5

**action**: Judge runs score.py --instances hidden_benchmarks --optima hidden_optima.json --outputs scoring/outputs --traces scoring/traces --perturbations-root scoring/perturb [--l3-ranking submission/l3_ranking.json] --reward-out /logs/verifier/reward.json. L5 per perturbation = retained L2 credit / base L2 credit over the 21 subset instances (min(base, perturbed) summed, divided by summed base; 0 if base is 0); lane = mean over 7 perturbations x 15. KILL band clips to 0 on forbidden_library, network_egress, private_artifact_read or shortcut_mine_and_return. test.sh writes reward.txt = score/100.

**state**: reward emitted

**drift_survived**: lane-order drift, missing L3 file, missing perturbation dirs

**checker**: score.py --perturbation-subset; test.sh writes reward.txt = score/100

## Near-miss routes

- **route**: reference_naive_bnb_primal_simplex
  **rejection_reason**: Reference solver is CALIBRATION ARTIFACT only per MEPHISTO 1.2; agent submission is graded against author-computed optima directly, never against reference output. Reference measured lands at 37.74/100 IN BAND [20, 40], confirming task is not too-easy (ref << ceiling 100) and not too-hard (ref >> floor 0). Reference hits LP-iteration-limit on 27 of 90 hardest instances (mostly capacitated-facility-location at 252-464 vars, plus graph-coloring LP-heavy cases, plus some multi-dim-knapsack), returning status unknown, which is honest degradation for a stdlib-only naive baseline. [Numbers quoted here were measured on v1 (2026-08-10); v2 route re-measurement pending.]

- **route**: lp_round
  **rejection_reason**: Solve LP relaxation via _solve_lp_relaxation, round x_i to nearest integer, feasibility-check via lib.feasibility_violations, set status feasible if no violations else infeasible. LP-round measured total 15.91 SAFELY BELOW reference 37.74 (margin 21.83). Fractional LP solutions rarely round to integer-feasible points on tight constraint families (CFL, GC, MDK), so L1 fails on most hard instances. Reference's B&B search dominates this shortcut. [Numbers quoted here were measured on v1 (2026-08-10); v2 route re-measurement pending.]

- **route**: all_zero
  **rejection_reason**: Submit variables=[0]*n_vars for every instance, status=feasible if feasible else infeasible. v2 MEASURED 2026-09-05 on the v2 judge: 4.44/100 (L1 4.44 from status agreement on the 40 instances where the zero vector is feasible/infeasible as the oracle says; L2 0, L3 0, L4 0, L5 0 under the credit-retained formula). Reference 24.23, margin 19.79.

- **route**: greedy_set_cover
  **rejection_reason**: Family-gated greedy (largest uncovered-element gain per subset cost) applied to set-cover family only; other 80 of 90 instances return status=unknown. Greedy-set-cover measured total 2.79 SAFELY BELOW reference 37.74 (margin 34.95). Even on the 10 set-cover instances, greedy achieves feasibility but leaves 5-15% optimality gap versus B&B optimum, yielding partial L2 credit only within that family. [Numbers quoted here were measured on v1 (2026-08-10); v2 route re-measurement pending.]

- **route**: greedy_knapsack
  **rejection_reason**: Family-gated value-per-max-weight-across-constraints density greedy applied to zero-one-knapsack plus multi-dimensional- knapsack (40 of 90 instances); other 50 return status=unknown. Greedy-knapsack measured total 14.49 SAFELY BELOW reference 37.74 (margin 23.25). Density-greedy achieves feasibility on the 40 instances but leaves 3-10% optimality gap where B&B closes to optimum on knapsack cohort. [Numbers quoted here were measured on v1 (2026-08-10); v2 route re-measurement pending.]

- **route**: hard_coded_lookup
  **rejection_reason**: Read hidden_optima.json entry per instance_id and return oracle answers verbatim as agent output. Hard-coded-lookup RAW score 40.00 would trip KILL band clipping to 0.00 via lib.KILL_REASON_SHORTCUT_MINE_AND_RETURN. hidden_optima.json is judge-side artefact under private_boundary; agent-visible closure cannot read it. Any attempt would be detected via canary tripwire scan on hidden_optima.json filename or objective_value literal byte-match. [Numbers quoted here were measured on v1 (2026-08-10); v2 route re-measurement pending.]

- **route**: shell_out_to_cbc_mock
  **rejection_reason**: Import subprocess plus string-literal-mention cbc, gurobi, or_tools, pulp, glpk, scip, highs, mosek, xpress, cvxpy, python_mip, pyscipopt, z3, cvc5, minisat, kissat, cadical (any of lib.FORBIDDEN_LIBRARY_STEMS 33-tuple), or reference scipy. optimize.milp / scipy.optimize.linprog (lib.FORBIDDEN_SCIPY_ATTRS). Shell-out-to-cbc-mock RAW score 0.00 with immediate KILL band clip via lib.KILL_REASON_FORBIDDEN_LIBRARY. Detected via lib.scan_forbidden_imports source-scan over agent-shipped src/ tree at grading time. [Numbers quoted here were measured on v1 (2026-08-10); v2 route re-measurement pending.]

- **route**: network_egress_mock
  **rejection_reason**: Attempt outbound HTTP or DNS resolution during solve execution. Network-egress-mock RAW score 0.00 with immediate KILL band clip via lib.KILL_REASON_NETWORK_EGRESS. Docker network_mode=no-network binds work and judge containers per Harbor 1.4 environment_mode= separate contract; any egress attempt at build time or solve time fails at the network boundary and is logged for KILL attribution. [Numbers quoted here were measured on v1 (2026-08-10); v2 route re-measurement pending.]

## Lane reconciliation

### L1_structural

- satisfied_by_steps: [1, 2]
- detail: Universe cardinality N=90 pinned from hidden_benchmarks/*.ip.json file count; per-instance output validated via lib.validate_output_json for schema plus status agreement plus variables-in-{0,1} plus objective_value numeric; feasibility re-checked via lib.feasibility_violations when reported status is optimal or feasible. Reference measured: 1.11.

### L2_optimality_gap

- satisfied_by_steps: [2, 5]
- detail: Optimality gap computed per instance as lib.optimality_gap( reported_obj, oracle_obj, sense), credit awarded via lib.l2_credit_for_gap(gap) piecewise curve (v2 curve gap<=0.00 -> 30, <=0.005 -> 27, <=0.01 -> 24, <=0.02 -> 18, <=0.05 -> 10, <=0.10 -> 4, else 0). Awarded only when oracle status is optimal AND reported status matches AND variables pass feasibility check. Reference measured: 3.33.

### L3_topk_precision

- satisfied_by_steps: [3, 5]
- detail: K=lib.L3_TOPK_K=8 top-K precision on the lib.L3_TOPK_COHORT_FAMILY='multi-dimensional-knapsack' cohort of 30 instances. Submitted ranking = the agent's own l3_ranking.json written at evaluation time (hardest first); only ids in the cohort count. Oracle ranking = cohort ordered by hidden_optima.json.solver_wall_seconds (HiGHS wall time) descending. Precision = |submitted[:8] intersect oracle[:8]| / 8, scaled by 25 points. Reference measured: 0.00.

### L4_anytime_progression

- satisfied_by_steps: [2, 5]
- detail: For each instance, parse stderr for BEST ts=<t> obj=<f> tokens via lib.L4_BEST_TOKEN_REGEX, require at least lib.L4_MIN_PROGRESSION_TOKENS=2 tokens to award any credit, compute area under best-so-far normalized-credit curve from t=0 to lib.PER_INSTANCE_TIMEOUT_SEC=60 using trapezoidal step-hold of credit=max(0, 1 - optimality_gap(best_so_far, oracle, sense)) at each timestamp. Score = mean across 90 instances scaled by 20 points. Reference measured: 5.50.

### L5_perturbation_robustness

- satisfied_by_steps: [4, 5]
- detail: Seven perturbations of a fixed 21-instance subset (first 3 per family, sorted ids), built by tests/perturb_v2.py, solved by the same pinned 16-lane runner, outputs un-perturbed, then lib.perturbation_robustness_score = sum(min(base, perturbed)) / sum(base) per perturbation (0 when base is 0); lane = mean over the seven x 15. The v1 stability form (1 - mean|base - perturbed|) paid 15/15 to the all-zero control on v2 (measured 2026-09-05) and was replaced. v1 declared this lane but its test.sh never ran the sweep, so every v1 submission scored 0 here. Reference measured: 14.29.

### anti_gaming_kill_band

- satisfied_by_steps: [5]
- detail: KILL band per lib.apply_kill_band clips total score to 0.0 if any reason in lib.KILL_REASONS = (forbidden_library, network_egress, private_artifact_read, shortcut_mine_and_return) fires during grading. Detected via lib.scan_forbidden_imports source-scan plus canary tripwire on private-artifact filename or byte-content match plus Docker network_mode=no-network at container boundary plus explicit --extra-kill-reason judge invocation for detected shortcuts.

## Oracle reconciliation

- invoked_at: 2026-09-05
- method: solve.sh invokes reference_solver.py against each hidden instance under 60-second per-instance timeout, produces per-instance stdout JSON output plus stderr progression trace, judge runs score.py to grade assembled submission. Reference IS the honest oracle for Framework A from-scratch-solver task-shape; there is no hindsight oracle CSV because grading requires solving from inputs.
- work_image_ref: `426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.work.p6zeta_zero_one_ip_solver_from_scratch:v2-41d69325de35@sha256:41d69325de35d03f622a5e8060db07e48234fd020338b8413edbd9ce8841658c`
- judge_image_ref: `426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.judge.p6zeta_zero_one_ip_solver_from_scratch:v2-968885e234f0@sha256:968885e234f05fc1faef321baeccc07b9faef4fa71c77014c4756fbdedc42881`
- total_score_raw: 24.23
- total_score_normalized: 0.2423
- full_reward_threshold: 0.95
- full_reward_reached: False

### per_lane_measured

- L1_structural: {'score': 1.11, 'max': 10, 'satisfied_by': [1, 2]}
- L2_optimality_gap: {'score': 3.33, 'max': 30, 'satisfied_by': [2, 5]}
- L3_topk_precision: {'score': 0.0, 'max': 25, 'satisfied_by': [3, 5]}
- L4_anytime_progression: {'score': 5.5, 'max': 20, 'satisfied_by': [2, 5]}
- L5_perturbation_robustness: {'score': 14.29, 'max': 15, 'satisfied_by': [4, 5]}

**score_gap_analysis**: v2 reference (the v1 from-scratch primal-simplex + best-first B&B calibration artifact) lands 24.23/100 on the v2 hidden set with the full lane-5 sweep executed. Frontier calibration on the same judge (2026-09-05): today's v1 OpenHands+Opus5 artifact (agent-27, 75.62 on v1) scores 79.67 (L1 9.78 L2 23.69 L3 12.50 L4 19.29 L5 14.42); yesterday's artifact (agent-11, 81.87 on v1) scores 72.07 (L1 10 L2 24.39 L3 3.12 L4 19.69 L5 14.88); all-zero control 4.44 (L1 only). Reference band [20, 40] retained: 24.23 is IN BAND. Full-reward threshold remains 0.95.

