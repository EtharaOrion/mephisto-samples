# TRUTH.md - p6zeta_zero_one_ip_solver_from_scratch

<!-- GENERATED SECTION. DO NOT HAND-EDIT. Re-run seed/build/p6zeta_zero_one_ip_solver_from_scratch/recompute.py <bundle_dir> to regenerate this file from grounding.yaml. -->

**task_id**: `p6zeta_zero_one_ip_solver_from_scratch`
**family**: Framework A: from-scratch combinatorial-optimization solver

## Canary tokens

- `MEPHISTO_CANARY_P6Z_20260810_C4B18F2A`
- `MEPHISTO_CANARY_P6Z_20260810_9E735D61`
- `MEPHISTO_CANARY_P6Z_20260810_2A48C7E9`

## Golden trajectory

**reference_method_name**: From-scratch primal-simplex LP relaxation with Big-M artificials plus best-first branch-and-bound over binary variables. The judge loads N=90 hidden instances from hidden_benchmarks/*.ip.json plus hidden_optima.json (author-computed via scipy.optimize.milp HiGHS backend, cross-verified via pure-Python B&B on seven spot instances), invokes the agent's shipped ./solve entry-point per instance with 60-second per-instance timeout under 16-worker parallelism inside a 7200-second whole-run wall-clock budget, captures per-instance stdout JSON plus stderr BEST-token trace, ranks the multi-dimensional- knapsack stress cohort (30 instances) by wall-time desc for L3 top-K=8 precision, replays each instance under seven perturbations for L5 robustness, and grades the assembled submission through the 5-lane rubric (L1 structural 10, L2 optimality-gap threshold curve 30, L3 top-K precision 25, L4 anytime progression 20, L5 perturbation robustness 15) with KILL-band clip on forbidden_library, network_ egress, private_artifact_read, or shortcut_mine_and_return. Reference self-score measured 37.74/100 lands IN BAND [20, 40].

### Step 1

**action**: Judge loads /home/workspace/scoring/data/hidden_benchmarks/*.ip.json and confirms 90 files present (canonical N_UNIVERSE for this task matching lib.HIDDEN_INSTANCE_TOTAL = 60 primary plus 30 L3 stress cohort), then loads hidden_optima.json keyed by instance_id with author-computed optima plus cross_verified flag per instance.

**state**: universe pinned

**drift_survived**: instance-order drift, generator-seed drift

**checker**: score.py N_UNIVERSE-check plus lib.validate_instance_json

### Step 2

**action**: Judge invokes ./solve <path/to/input.ip.json> per hidden instance under 60-second timeout (lib.PER_INSTANCE_TIMEOUT_SEC), captures per-instance stdout JSON output at _judge_outputs/<instance_id>.out.json plus stderr trace at _judge_traces/<instance_id>.log, validates output schema via lib.validate_output_json (status in {optimal, feasible, infeasible, unknown} plus variables plus objective_value plus instance_id), parses stderr for BEST-token progression via lib.L4_BEST_TOKEN_REGEX.

**state**: submissions collected

**drift_survived**: solve-wall-time jitter, output field-order drift

**checker**: lib.validate_output_json plus lib.feasibility_violations

### Step 3

**action**: Judge builds L3 top-K=8 ranking by ordering the multi-dimensional- knapsack cohort (30 instances, lib.L3_TOPK_COHORT_FAMILY) by agent-reported solver wall-time descending, computes precision against oracle wall-time-desc ranking sourced from hidden_optima.json.solver_wall_seconds field.

**state**: L3 ranking computed

**drift_survived**: wall-time measurement noise below 1 second bin

**checker**: lib.top_k_precision with k=lib.L3_TOPK_K=8

### Step 4

**action**: Judge invokes ./solve on each of seven perturbation variants per hidden instance (variable_order_within_constraint, constraint_reorder, coefficient_common_scale, instance_id_salt_rewrite via HMAC, json_whitespace_reformat, output_json_field_order, output_json_trailing_whitespace), captures perturbed outputs at _judge_perturbations/<perturbation_name>/<instance_id>.out.json, computes per-perturbation L2 credit vector.

**state**: perturbation sweep complete

**drift_survived**: perturbation-order drift, whitespace-normalization drift

**checker**: lib.perturbation_robustness_score across 7 perturbations

### Step 5

**action**: Judge runs score.py --instances hidden_benchmarks --optima hidden_optima.json --outputs _judge_outputs --traces _judge_traces --perturbations-root _judge_perturbations --l3-ranking _judge_l3.json --reward-out /tmp/reward.json, aggregates 5 lanes (L1=10, L2=30, L3=25, L4=20, L5=15, sum=100), applies KILL-band clip to 0 if any reason in lib.KILL_REASONS fires, emits reward document to /tmp/reward.json per lib.REWARD_CONTRACT_PATH, test.sh normalizes to [0, 1] reward at /logs/verifier/reward.txt.

**state**: submission graded

**drift_survived**: score-JSON field-order drift, reward-normalizer drift

**checker**: score.py grade_submission plus emit_reward_document plus test.sh normalizer

## Near-miss routes

- **route**: reference_naive_bnb_primal_simplex
  **rejection_reason**: Reference solver is CALIBRATION ARTIFACT only per MEPHISTO 1.2; agent submission is graded against author-computed optima directly, never against reference output. Reference measured lands at 37.74/100 IN BAND [20, 40], confirming task is not too-easy (ref << ceiling 100) and not too-hard (ref >> floor 0). Reference hits LP-iteration-limit on 27 of 90 hardest instances (mostly capacitated-facility-location at 252-464 vars, plus graph-coloring LP-heavy cases, plus some multi-dim-knapsack), returning status unknown, which is honest degradation for a stdlib-only naive baseline.

- **route**: lp_round
  **rejection_reason**: Solve LP relaxation via _solve_lp_relaxation, round x_i to nearest integer, feasibility-check via lib.feasibility_violations, set status feasible if no violations else infeasible. LP-round measured total 15.91 SAFELY BELOW reference 37.74 (margin 21.83). Fractional LP solutions rarely round to integer-feasible points on tight constraint families (CFL, GC, MDK), so L1 fails on most hard instances. Reference's B&B search dominates this shortcut.

- **route**: all_zero
  **rejection_reason**: Submit variables=[0]*n_vars for every instance, status=feasible if feasible else infeasible. All-zero measured total 5.56 SAFELY BELOW reference 37.74 (margin 32.18). Trivial zero vector is infeasible on covering families (set-cover, GC) and yields objective 0 on packing families (K01, MDK), losing L2 credit on every instance where oracle objective is strictly positive.

- **route**: greedy_set_cover
  **rejection_reason**: Family-gated greedy (largest uncovered-element gain per subset cost) applied to set-cover family only; other 80 of 90 instances return status=unknown. Greedy-set-cover measured total 2.79 SAFELY BELOW reference 37.74 (margin 34.95). Even on the 10 set-cover instances, greedy achieves feasibility but leaves 5-15% optimality gap versus B&B optimum, yielding partial L2 credit only within that family.

- **route**: greedy_knapsack
  **rejection_reason**: Family-gated value-per-max-weight-across-constraints density greedy applied to zero-one-knapsack plus multi-dimensional- knapsack (40 of 90 instances); other 50 return status=unknown. Greedy-knapsack measured total 14.49 SAFELY BELOW reference 37.74 (margin 23.25). Density-greedy achieves feasibility on the 40 instances but leaves 3-10% optimality gap where B&B closes to optimum on knapsack cohort.

- **route**: hard_coded_lookup
  **rejection_reason**: Read hidden_optima.json entry per instance_id and return oracle answers verbatim as agent output. Hard-coded-lookup RAW score 40.00 would trip KILL band clipping to 0.00 via lib.KILL_REASON_SHORTCUT_MINE_AND_RETURN. hidden_optima.json is judge-side artefact under private_boundary; agent-visible closure cannot read it. Any attempt would be detected via canary tripwire scan on hidden_optima.json filename or objective_value literal byte-match.

- **route**: shell_out_to_cbc_mock
  **rejection_reason**: Import subprocess plus string-literal-mention cbc, gurobi, or_tools, pulp, glpk, scip, highs, mosek, xpress, cvxpy, python_mip, pyscipopt, z3, cvc5, minisat, kissat, cadical (any of lib.FORBIDDEN_LIBRARY_STEMS 33-tuple), or reference scipy. optimize.milp / scipy.optimize.linprog (lib.FORBIDDEN_SCIPY_ATTRS). Shell-out-to-cbc-mock RAW score 0.00 with immediate KILL band clip via lib.KILL_REASON_FORBIDDEN_LIBRARY. Detected via lib.scan_forbidden_imports source-scan over agent-shipped src/ tree at grading time.

- **route**: network_egress_mock
  **rejection_reason**: Attempt outbound HTTP or DNS resolution during solve execution. Network-egress-mock RAW score 0.00 with immediate KILL band clip via lib.KILL_REASON_NETWORK_EGRESS. Docker network_mode=no-network binds work and judge containers per Harbor 1.4 environment_mode= separate contract; any egress attempt at build time or solve time fails at the network boundary and is logged for KILL attribution.

## Lane reconciliation

### L1_structural

- satisfied_by_steps: [1, 2]
- detail: Universe cardinality N=90 pinned from hidden_benchmarks/*.ip.json file count; per-instance output validated via lib.validate_output_json for schema plus status agreement plus variables-in-{0,1} plus objective_value numeric; feasibility re-checked via lib.feasibility_violations when reported status is optimal or feasible. Reference measured L1=7.00/10, meaning 63 of 90 instances pass full structural check; 27 fail on status_mismatch (reference reported unknown when oracle proved optimal).

### L2_optimality_gap

- satisfied_by_steps: [2, 5]
- detail: Optimality gap computed per instance as lib.optimality_gap( reported_obj, oracle_obj, sense), credit awarded via lib.l2_credit_for_gap(gap) piecewise curve (gap<=0.00 -> 30, <=0.02 -> 27, <=0.05 -> 24, <=0.10 -> 18, <=0.20 -> 10, <=0.35 -> 4, else 0). Awarded only when oracle status is optimal AND reported status matches AND variables pass feasibility check. Reference measured L2=19.63/30 across 90 instances, meaning honest reference solves easy families (GA, K01, TSP) to optimum but times out on hard families (CFL, GC, MDK stress) with partial credit through partial-gap tail.

### L3_topk_precision

- satisfied_by_steps: [3, 5]
- detail: K=lib.L3_TOPK_K=8 top-K precision on lib.L3_TOPK_COHORT_FAMILY='multi-dimensional-knapsack' cohort of 30 instances. Submitted ranking = 30 MDK instances ordered by agent-reported solver wall-time descending (proxy for hardness). Oracle ranking = 30 MDK instances ordered by hidden_optima.json.solver_wall_seconds descending. Precision = |submitted[:8] intersection oracle[:8]| / 8, scaled by 25 points. Reference measured L3=3.12/25, meaning naive B&B's wall-time ranking imperfectly tracks scipy HiGHS wall-time ranking (they share hardness structure but differ on algorithm-specific pruning).

### L4_anytime_progression

- satisfied_by_steps: [2, 5]
- detail: For each instance, parse stderr for BEST ts=<t> obj=<f> tokens via lib.L4_BEST_TOKEN_REGEX, require at least lib.L4_MIN_PROGRESSION_TOKENS=2 tokens to award any credit, compute area under best-so-far normalized-credit curve from t=0 to lib.PER_INSTANCE_TIMEOUT_SEC=60 using trapezoidal step-hold of credit=max(0, 1 - optimality_gap(best_so_far, oracle, sense)) at each timestamp. Score = mean across 90 instances scaled by 20 points. Reference measured L4=7.98/20; most instances that solve to optimum at root LP emit only 1 BEST token (below threshold, credit=0), so L4 rewards instances that legitimately enter B&B with multiple incumbent updates.

### L5_perturbation_robustness

- satisfied_by_steps: [4, 5]
- detail: For each of 7 perturbations in lib.PERTURBATIONS tuple, judge re-invokes ./solve on perturbed variant per instance, computes per-instance L2 credit vector under perturbation, then computes per-perturbation robustness score = lib.perturbation_robustness_score(base_credits, perturbed_credits) = max(0, 1 - mean(|base - perturbed|)). Total L5 = mean across 7 perturbation scores scaled by 15 points. Reference measured L5=0.00/15 during Phase 1 calibration because perturbation sweep was not run during P1.4; reference is deterministic so measured L5 will land in 14-15/15 range when Phase 2 sweep completes.

### anti_gaming_kill_band

- satisfied_by_steps: [5]
- detail: KILL band per lib.apply_kill_band clips total score to 0.0 if any reason in lib.KILL_REASONS = (forbidden_library, network_egress, private_artifact_read, shortcut_mine_and_return) fires during grading. Detected via lib.scan_forbidden_imports source-scan plus canary tripwire on private-artifact filename or byte-content match plus Docker network_mode=no-network at container boundary plus explicit --extra-kill-reason judge invocation for detected shortcuts.

## Oracle reconciliation

- invoked_at: 2026-08-10
- method: solve.sh invokes reference_solver.py against each hidden instance under 60-second per-instance timeout, produces per-instance stdout JSON output plus stderr progression trace, judge runs score.py to grade assembled submission. Reference IS the honest oracle for Framework A from-scratch-solver task-shape; there is no hindsight oracle CSV because grading requires solving from inputs.
- work_image_ref: `<PENDING_ECR_WORK_URI>`
- judge_image_ref: `<PENDING_ECR_JUDGE_URI>`
- total_score_raw: 37.74
- total_score_normalized: 0.377
- full_reward_threshold: 0.95
- full_reward_reached: False

### per_lane_measured

- L1_structural: {'score': 7.0, 'max': 10, 'satisfied_by': [1, 2]}
- L2_optimality_gap: {'score': 19.63, 'max': 30, 'satisfied_by': [2, 5]}
- L3_topk_precision: {'score': 3.12, 'max': 25, 'satisfied_by': [3, 5]}
- L4_anytime_progression: {'score': 7.98, 'max': 20, 'satisfied_by': [2, 5]}
- L5_perturbation_robustness: {'score': 0.0, 'max': 15, 'satisfied_by': [4, 5]}

**score_gap_analysis**: Reference lands 37.74 / 100 = 37.7% far below full-reward threshold 95%. L5 = 0.00 during Phase 1 because perturbation sweep deferred to Phase 2; deterministic solver will contribute 14-15 pts under full sweep, projecting Phase 2 total to 52-53. Even with full L5, reference remains well below 95 threshold, confirming task-shape correctly requires either (a) a fundamentally better solver design than naive stdlib B&B (branch-and-cut, cuts learned per-family, presolve reductions, warm-start heuristics) or (b) exhausting the 12-hour agent horizon with careful implementation. Frontier LLMs on EdgeBench Optimize @12h scored 36.5 (Opus 4.8), 33.6 (GPT-5.5), 27.9 (GPT-5.4), 26.4 (GLM-5.1), 21.5 (DS-V4-Pro), placing reference 37.74 slightly above Opus 4.8, consistent with a naive-competent- stdlib-baseline calibration.

