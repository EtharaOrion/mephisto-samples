# Pilot Runbook - cftc_futures_positioning_book

## What you are doing

You are executing a single 12-hour rollout of Claude Opus 4.8 against the
frozen CFTC futures positioning book task, then capturing the score for
signed proof.

## Prerequisites

1. Docker daemon running, linux/amd64 platform support (rosetta on M1/M2 Macs)
2. `aws` CLI configured with credentials that can pull from ECR account 426628337772
3. Local disk: at least 2 GB free
4. Approximately 12 hours of Opus-4.8 API budget
5. Task bundle UUID: `33d28748-b172-584d-b378-f46d85de56fe`
6. `ANTHROPIC_API_KEY` exported in the shell running `sforge run`

## Model cohort

The bound pilot cohort in `seed/pilot.yaml` is **`claude-opus-4-8`**. This
matches the shipped-sample convention, and the current `seed/contract.approved`
digest (`b169a971cf9ed768c80e0f1e1de4a034871ea6b754d34580fd0bc85d6e70b790`)
covers a contract that pins this cohort. Run the pilot with:

```bash
export ANTHROPIC_API_KEY=<your key>
SFORGE_TASKS_DIR=$(git rev-parse --show-toplevel)/dataset \
SFORGE_BENCHMARK_PATH=$(git rev-parse --show-toplevel)/touchstones \
  uv run --project harness/sforge sforge run \
    --task cftc_futures_positioning_book \
    --model claude-opus-4-8 \
    --timeout 43200 \
    --disable-internet
```

### If you must swap the cohort

Changing the pilot cohort re-triggers Phase 0.5 sign-off per FORGE.md rule 9:

1. Edit `seed/pilot.yaml` `cohort.models_predeclared` to the new model id
2. Recompute the SHA-256 of `seed/contract.yaml`:
   `sha256sum seed/contract.yaml | awk '{print $1}' > seed/contract.approved`
3. Human approver signs by keeping that digest in `contract.approved`
4. Re-run the pilot with the new `--model` flag

A pilot proof whose executed model does not match the bound cohort is invalid
and will not raise disposition — the operator must not swap silently.

## Step-by-step

### 1. Pull the two Docker images

```bash
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin 426628337772.dkr.ecr.ap-south-1.amazonaws.com

docker pull 426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.work.cftc_futures_positioning_book:v3@sha256:b50d13058361b328482348dc6d6c8776bbcf0a85a970102aba64153427ae30f6

docker pull 426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.judge.cftc_futures_positioning_book:v3@sha256:34109d4e16f1c38c4501a73c167bb2486d139d48f387aee026cd41b12d28258d
```

### 2. Run the agent (12 hours max)

Point your Opus 4.8 agent harness at the work container. The agent reads
`/home/workspace/attachments/` for data and writes to `/home/workspace/`.
Agent must submit exactly three files:
- `/home/workspace/cftc_positioning.py`
- `/home/workspace/requirements.txt`
- `/home/workspace/positioning_results.json`

Container is `network_mode = no-network`.

### 3. Score with the judge

```bash
docker run --rm --platform linux/amd64 \
  -v $(pwd)/agent_submission:/home/workspace \
  -v $(pwd)/logs:/logs \
  --network none \
  426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.judge.cftc_futures_positioning_book:v3
```

Result appears at `logs/verifier/reward.json` and `logs/verifier/reward.txt`.

### 4. Fill in the proof template

Copy `memory/proofs/33d28748-b172-584d-b378-f46d85de56fe.yaml.template`
to `memory/proofs/33d28748-b172-584d-b378-f46d85de56fe.yaml` and fill in every
`<FILL>` slot with the actual measurements. Sign the file per your local
signing convention.

### 5. Trajectory files

Save the following into `dataset/33d28748-b172-584d-b378-f46d85de56fe/trajectories/opus-4-8/`:
- `positioning_results.json` (the agent's submission)
- `reward.json` (the judge's output)
- `reward.txt` (the normalized reward)
- `agent.log` (full transcript, if available)
- `run_config.json` (model version, temperature, budget, wall clock)

## How to read the score

**Do not trust the sforge stdout `pass_rate` display.** This task returns a
continuous 0-110 reward via `reward.json`, not pytest pass/fail counts, so
sforge always prints `0/0 passed (pass_rate=0.00%)` regardless of outcome.
The actual score lives in two places:

- `logs/runs/<run-id>/cftc_futures_positioning_book/submissions/<sub>/report.json`
  - Field `score` is the normalized reward in [0, 1]
- Inside the judge container at `/logs/verifier/reward.json`
  - Field `score` is the raw 0-110 value, with per-lane breakdown

The `report.json:score` and `reward.json:score / 110` must agree, and both
must appear before the run is considered valid.

## Verification (baselines already measured on this frozen bundle)

Reference solver: **27.60 / 110 = 0.25091**
Copy-last-week baseline: **13.37 / 110 = 0.122**
Uniform-up baseline: **9.43 / 110 = 0.086**
Empty submission: **0.00**

Frontier defeat floor is **0.34** (per `memory/scope.yaml`).

If Opus 4.8 scores below 0.34, the task successfully defeats the frontier and
is a candidate for SHIP disposition. If Opus 4.8 scores at or above 0.34, the
task does not sufficiently challenge the frontier and returns to Phase 1 for
harder design.

## Per-lane budget reference (from reference-solver run)

| Lane | Metric      | Value  | Points |
|------|-------------|--------|--------|
| L1   | direction acc | 0.5154 | 6.54  |
| L2   | magnitude acc | 0.2841 | 0.23  |
| L3   | crowding acc  | 0.4162 | 2.84  |
| L4   | extreme F1    | 0.4397 | 4.79  |
| L5   | rank rho      | 0.0228 | 0.57  |
| L6   | rate-adaptive | 0.5261 | 3.80  |
| L7   | anti-fabricate | small deltas | 5.00 (max) |
| L8   | quarter var   | 0.0079 | 3.83  |
| B1   | commodity bonus | n/a  | 0.00 (EIA unavailable by design) |
| **Total** |         |        | **27.60 / 110** |
