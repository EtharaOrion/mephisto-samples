## Iterative Evaluation Mode

You are working with iterative test feedback. After implementing code, you can submit your work for evaluation at any time to see which tests pass and which fail, then iterate based on the results.

### How to Test Your Code

- Run `sforge-submit` to submit your current code for evaluation. It will package the files, send them to the judge server, and return results showing score, pass rate, and a summary of findings.
- Run `sforge-submit --details` to submit and see detailed per-test results.
- Run `sforge-submit --list` to view all previous submissions and their scores for this run.

You should use these regularly to check your progress and identify issues.

### Submitted Files

Only the following paths are submitted for evaluation: `build.sh`, `solve`, `src/`

**Keep these files in a compilable/runnable state at all times.** A background process periodically auto-evaluates your code — if the submitted files are broken, incomplete, or contain syntax errors at that moment, the auto-evaluation will fail. Write changes to disk promptly and ensure the submitted files always represent your current best solution.

### Submission Limits

- You have a **limited number of submissions (300 total)**. Plan carefully and validate locally before submitting.
- There is a **minimum interval of 120s** between submissions.

### Network Environment

**This environment has NO internet access.** Only the judge server and the AI API are reachable. Do not attempt to download packages, fetch remote resources, or access external URLs — all dependencies are pre-installed in the workspace.

### Strategy

- **Implement incrementally**: Complete one module/project at a time
- **Read test feedback carefully**: Failed test names often hint at what's broken
- **Iterate**: Fix failing tests based on the feedback, then submit again

### Scoring

- Your **best score** across all submissions is your final score
- You don't lose points for failed attempts — experimentation is encouraged

---

Read the complete task instructions in `/home/workspace/task_instruction.md` before beginning any work. That file is the authoritative agent-facing specification for this task; the summary below exists only to point you at it.

# Zero-One Integer Programming Solver from Scratch

## Role

You are implementing a from-scratch 0-1 integer programming (0-1 IP) solver. The evaluator will invoke your `./solve` binary once per instance across a private set of 90 held-out instances drawn from seven NP-hard families. Your job is to maximize your 5-lane score under the constraints below.

## Deliverable

Provide three submission paths at your working directory root:

- `build.sh` - shell script the judge runs once before evaluation to compile or install any local artifacts your solver needs. May be empty.
- `solve` - executable entrypoint. The judge invokes `./solve <path/to/input.ip.json>` per instance and expects a JSON solution on stdout. Structured progression tokens `BEST ts=<seconds> obj=<value>` on stderr contribute to the anytime-progression lane.
- `src/` - directory containing your solver source. All source under `src/` ships with the submission; nothing outside these three paths is considered.

## Input format

Each instance is a JSON file with the following schema:

```json
{"instance_id": "p6zeta__hidden__<family>__NNN",
 "family": "<one of seven families>",
 "n_vars": <positive int>,
 "objective_sense": "max" | "min",
 "objective_coefficients": [<n_vars floats>],
 "constraints": [
   {"coefficients": [<n_vars floats>],
    "rhs": <float>,
    "sense": "<=" | ">=" | "=="}
 ]
}
```

All decision variables are binary (values 0 or 1). Feasibility is defined row-by-row against the sense.

## Output format

Print a single JSON document to stdout:

```json
{"instance_id": "<echoed input id>",
 "status": "optimal" | "feasible" | "infeasible" | "unknown",
 "variables": [<n_vars 0/1 ints>] | null,
 "objective_value": <float> | null
}
```

`variables` and `objective_value` may be `null` only when `status` is `infeasible` or `unknown`.

## Progression tokens (optional but graded)

Emit lines to stderr of the exact form `BEST ts=<seconds_since_start> obj=<current_incumbent>` each time you find an improved incumbent. At least two such tokens are required to earn any anytime-progression credit for an instance.

## Provided inputs

Your working environment contains:

- `data/develop/*.ip.json` - 6 example instances (one per primary family) with matching structure to the hidden set. Use for local development.
- `data/ip_format_spec.md` - byte-level format specification.
- `p6zeta_lib.py` - shared reference library (validators, feasibility check, objective computation, canonical JSON helpers). You may import or copy from it as you see fit.

## Scoring (0 to 100)

Five lanes summed then clipped:

- L1 structural (10 pts): fraction of instances passing schema check and status agreement with oracle.
- L2 optimality gap (30 pts): threshold curve on the relative gap to the author-computed optimum. Gap <= 0.00 earns 30; <= 0.02 earns 27; <= 0.05 earns 24; <= 0.10 earns 18; <= 0.20 earns 10; <= 0.35 earns 4; otherwise 0.
- L3 top-K precision (25 pts): submit a JSON list of your K=8 hardest multi-dimensional-knapsack instance ids (sorted hardest-first) to file `l3_ranking.json` alongside your outputs. Scored against oracle hardness ranking by wall-time.
- L4 anytime progression (20 pts): mean progression-curve credit across instances, requires >= 2 BEST tokens per instance.
- L5 perturbation robustness (15 pts): mean stability across seven deterministic perturbations (variable order, constraint reorder, coefficient scaling, id salt, whitespace, field order, trailing whitespace). The judge runs your solver against each perturbed cohort.

## KILL band (score to 0)

Any of the following collapses your total to 0:

- Importing or shelling out to a forbidden solver library (cplex, gurobi, ortools, pulp, cbc, glpk, scip, highs, mosek, xpress, cvxpy, python-mip, scipy.optimize.milp, scipy.optimize.linprog, z3-solver, cvc5, minisat, kissat, cadical, and 15 others).
- Any outbound network egress attempt.
- Reading a private artifact outside your submission surface.
- Emitting the ShortcutScore mine-and-return signature (verbatim oracle answer for hidden instances that were not provided to you).

## Runtime constraints

- 60 second per-instance wall-clock timeout (judge kills your process).
- 16 parallel judge workers.
- 7200 second whole-run wall-clock budget across the 90-instance sweep.
- 43200 second total agent budget.
- No network access at agent time or judge time.

## Submission

Single-shot: one submission of build.sh + solve + src/ tree. There is no interactive feedback loop; you cannot see hidden scores before final grading. Use the develop set and the public grader library to tune locally.
