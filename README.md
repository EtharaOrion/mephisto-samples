<p align="center">
  <img src="assets/banner.webp" alt="Mephisto: 30 professional knowledge-work tasks graded on realized outcomes" width="880">
</p>

<p align="center">
  <strong>Long-horizon professional knowledge-work environments, graded against what the world actually did next.</strong>
</p>

<p align="center">
  <a href="#summary"><img alt="Built by Ethara.AI" src="https://img.shields.io/badge/built%20by-Ethara.AI-ee00ee.svg"></a>
  <a href="#scoring-methodology"><img alt="Scoring: continuous, lane-weighted" src="https://img.shields.io/badge/scoring-continuous_·_lane--weighted-35d0ba.svg"></a>
  <a href="#the-judge"><img alt="Verifier: offline, separate container" src="https://img.shields.io/badge/verifier-offline_·_separate_container-845EF7.svg"></a>
  <a href="#summary"><img alt="Horizon: 12h per task" src="https://img.shields.io/badge/horizon-12h_per_task-ff6b6b.svg"></a>
</p>

<p align="center"><sub>
  <a href="#summary">Summary</a> · <a href="#repository-layout">Layout</a> · <a href="#bundle-structure">Bundle</a> · <a href="#the-task-contract">Contract</a> · <a href="#the-agent-environment">Environment</a> · <a href="#the-judge">Judge</a> · <a href="#scoring-methodology">Scoring</a> · <a href="#trajectory-structure">Trajectories</a> · <a href="#reproduction">Reproduction</a> · <a href="#verification-and-quality-assurance">Verification</a>
</sub></p>

# Mephisto Samples: 30-Task Professional Knowledge Work Sample

**Mephisto measures whether an agent can produce a professional decision deliverable that survives
contact with the future, not whether it can restate the data it was handed.** Each task drops the
agent into a containerized workspace at a frozen information boundary, hands it an
`instruction.md` and the complete public record up to that boundary, and grades the deliverable it
builds against realized outcomes drawn from data published after that boundary.

Where rubric-graded knowledge-work benchmarks score an opinion about a deliverable, Mephisto
scores the deliverable against a settled result. The answer key is a record of events rather than
a judgment: the graded window is withheld at run time, lives only in the verifier image, and is
recomputed from the agent's raw output rather than accepted on the agent's word.

Every task is a **12-hour** run under a dual-loop protocol. The agent iterates locally against a
train/validation split for free, and submits to a separate judge container for authoritative
grading. Submission budgets are set per invocation rather than baked into the bundle; the
reference runs shipped here allow 300 submissions at a 120 s cooldown, with the host
auto-evaluating the workspace every 30 minutes on top of that.

> **This is a representative, quality-controlled sample of the full Mephisto corpus,** provided for
> evaluation. The task format ([Harbor](https://github.com/harbor-framework/harbor) `task.toml`
> plus the sforge runner form), the trajectory format, and the scoring are identical to the
> production deliveries.

## Summary

| Property             | Value                                                                                  |
| :------------------- | :------------------------------------------------------------------------------------- |
| Tasks                | **30**, one self-contained bundle per UUID                                             |
| Family               | Professional knowledge work: long-horizon decision deliverables                         |
| Agent horizon        | **12 h** per task (`agent.timeout_sec = 43200`)                                        |
| Verifier horizon     | declared per task in `verifier.timeout_sec`                                             |
| Feedback loop        | dual-loop; submission cap, cooldown and auto-eval tick set per invocation               |
| Reward               | continuous, lane-weighted, normalized to `[0, 1]` and written to `reward.txt`            |
| Grading data         | held-out, post-boundary, resident only in the verifier image                             |
| Isolation            | `network_mode = "no-network"` on both containers; `environment_mode = "separate"`        |
| Images               | pinned by content-hash tag **and** `sha256` digest; `python:3.11-slim` base              |
| Format               | Harbor `task.toml` + sforge `task.json`                                                 |

Each bundle is addressed by a deterministic **UUIDv5** over its canonical SHA-256 content hash, so
identical content maps to a stable id and distinct content is collision-resistant.

## Repository layout

Task bundles sit at the repository root. There is no intermediate collection directory, and
trajectories live inside the bundle they belong to rather than in a parallel tree.

```
mephisto-samples/
├── README.md                 # this document
├── LICENSE                   # CC BY-NC-ND 4.0
├── assets/
│   └── banner.webp           # README banner
└── <uuid>/                   # one self-contained task bundle (× 30)
    └── ...
```

## Bundle structure

Every bundle is the same seven-part tree:

```
<uuid>/
├── task.toml                 # Harbor task contract
├── task.json                 # the same contract for the sforge runner
├── instruction.md            # the brief presented to the agent
│
├── environment/              # builds the agent image
│   ├── Dockerfile
│   └── attachments/          # the entire public information boundary
│
├── tests/                    # builds the judge image (never mounted for the agent)
│   ├── Dockerfile
│   ├── test.sh               # verifier entrypoint; writes /logs/verifier/reward.txt
│   ├── scoring/
│   │   ├── eval_script.py    # runs the submission against the held-out data
│   │   ├── score.py          # the scoring lanes and their anchors
│   │   ├── scorer_manifest.json   # entrypoint, required files, score parsing, failure policy
│   │   └── judge_requirements.txt # judge-only deps, when the scorer needs any
│   └── hidden_test_data/     # held-out data + the answer key
│
├── solution/                 # the oracle (never uploaded to an evaluated agent)
│   ├── solve.sh              # places the reference deliverable and invokes it
│   ├── <task>_reference.py   # the reference implementation
│   ├── requirements.txt      # deps the reference needs
│   ├── TRUTH.md              # provenance, contract hash, generation recipe
│   └── ...                   # any state artefact the reference persists
│
└── trajectories/             # recorded reference runs
    └── <model-id>/ ...
```

During a run the agent sees only the built container filesystem and `instruction.md`. `tests/` and
`solution/` are used exclusively by the verifier and are never mounted into the agent's
environment.

**What is fixed across all 30 bundles:** the seven top-level entries above; the `task.toml` /
`task.json` contract pair; `instruction.md` as the sole agent-facing brief; the
`environment/` and `tests/` split into two images; a `score.py` reachable through a
`scorer_manifest.json`; a reference implementation under `solution/`; and a reward normalized to
`[0, 1]` at `/logs/verifier/reward.txt`.

**What varies per bundle:** the domain and the source data; the contents and file names inside
`attachments/` and `hidden_test_data/`; the deliverable filenames and their output schema, which
each `task.toml` declares in `artifacts` and `submit_paths`; the lane composition, weights and
anchors in `score.py`; the held-out unit the scorer iterates over; and the verifier budget. Nothing
outside the bundle needs to change when a task is added, and no bundle needs to know about any
other.

## The task contract

`task.toml` and `task.json` pin the same runtime in the two forms consumers need.

- `[environment]` and `[verifier.environment]` name the prebuilt images by content-hash tag **and**
  `sha256` digest, and both carry `network_mode = "no-network"`.
- `[agent] timeout_sec` sets the run budget and `[verifier] timeout_sec` the grading budget;
  `environment_mode = "separate"` keeps the judge in its own container.
- The top-level `artifacts` list and the `[extensions.sforge]` `submit_paths` / `submit_exclude`
  define exactly which files cross from the agent to the judge. `parser`, `selection` and
  `score_direction` fix the scoring convention.
- `[metadata]` records the upstream `source_host`, `data_license`, `license_class` and
  `license_source` of the underlying public record.

`task.json` additionally inlines two things the runner needs: the full brief as
`work.agent_query`, and the verifier invocation as `judge.eval_cmd`. Both are copies of files that
also ship unpacked (`instruction.md` and `tests/test.sh`), so treat the unpacked files as the
source of truth and regenerate `task.json` rather than editing it by hand.

## The agent environment

`environment/Dockerfile` builds the agent image and symlinks everything in `attachments/` into the
workspace root. `attachments/` holds the entire public information boundary: the raw source data,
any reference tables, an explicit train/validation period split, a deliverables guide, and the
dependency list. Nothing observed after the decision boundary appears here.

Because the container has no network, that dependency list is installed at build time and fixes
what the agent can import. It is not an at-run-time install manifest.

`instruction.md` states the professional role and the decision boundary, the components the
system must contain, the scoring lanes with their point weights and target thresholds, the
benchmark it is scored against, a table of every provided file, the hard constraints (exposure
limits, costs, no future data, no network, per-invocation runtime ceilings), the exact deliverable
filenames and output schema, and an explicit anti-fabrication warning.

## The judge

A separate, network-isolated image built from `tests/`. `hidden_test_data/` carries the held-out
data, the window definitions, and the labelled answer key.

`eval_script.py` re-executes the submitted deliverable once per held-out window against that data,
independently recomputes every self-reported metric from the raw submitted output, scores each
window through `score.py`, and aggregates with a cross-window stability penalty and any detection
bonus. `test.sh` bridges the harness's artifact-delivery convention into that contract and writes
the normalized reward. `scorer_manifest.json` declares the entrypoint, the required submission and
scoring files, the score-extraction pattern and scale, and the failure policy for every degenerate
case (missing submission, parse failure, non-zero exit without a score).

## Scoring methodology

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#2b3352','primaryTextColor':'#ffffff','primaryBorderColor':'#7a99d1','lineColor':'#7a99d1','fontFamily':'DM Sans, Roboto, Segoe UI, sans-serif'}}}%%
flowchart LR
  A["Task<br/>instruction.md + boundary data"] --> B["Agent<br/>builds the deliverable"]
  B --> C["Judge<br/>re-executes per held-out window"]
  C --> D["Recompute<br/>metrics from raw output"]
  D --> E["Reward<br/>lane total / scale, in [0, 1]"]
  classDef sealed fill:#2b3352,stroke:#ee00ee,color:#ffffff;
  classDef node fill:#2b3352,stroke:#ee00ee,color:#ffffff;
  classDef gate fill:#3a4360,stroke:#ee00ee,color:#ffffff;
  class A,B,E node;
  class C,D sealed;
```

Each of the 30 tasks declares its own lane composition in `tests/scoring/score.py`, because a
positioning book and a triage deliverable do not fail in the same ways. The shape is constant:
lanes over the task's held-out unit summing to 100 points, plus aggregate terms, normalized to
`[0, 1]` against the scale declared in `scorer_manifest.json` and written to
`/logs/verifier/reward.txt`.

`treasury_curve_positioning_book` is the worked example below, scored across 20 disjoint held-out
3-week windows. Lane names, weights and anchors differ task to task; read the bundle's own
`score.py` for the authoritative composition.

| Lane                          | Points | Measures                                                      |
| :---------------------------- | -----: | :------------------------------------------------------------ |
| L1 risk-adjusted return       |     25 | Sharpe over realized window returns                            |
| L2 directional accuracy       |     20 | hit rate on curve steepen / flatten calls                      |
| L3 duration precision         |     15 | RMSE of realized versus target portfolio duration              |
| L4 convexity capture          |     15 | butterfly P&L against an equal-DV01 benchmark                  |
| L5 drawdown control           |     10 | maximum within-window drawdown                                 |
| L6 turnover discipline        |      5 | annualized one-way turnover inside the declared band           |
| L7 anti-fabrication           |      5 | judge recompute versus the agent's self-report                 |
| L8 cross-window stability     |      5 | variance of per-window L1 scores (aggregated)                  |
| Regime-shift bonus            |    +10 | data-driven detection of a held-out regime event (aggregated)  |
| **Raw scale**                 | **110** | normalized to `[0, 1]` for the harness reward                 |

Two properties hold across the family. **Anti-fabrication is a lane, not a footnote:** every
metric the agent reports is recomputed from its raw submitted output, and a deviation beyond
tolerance zeroes both the integrity lane and the primary lane for that window. **The floor is
real:** the starter deliverable shipped in the workspace is a deliberately weak baseline that
scores at or near zero, so the reward is bounded and non-trivial at both extremes.

## Trajectory structure

Each recorded run lives under `<uuid>/trajectories/<model-id>/`:

```
<uuid>/trajectories/<model-id>/
├── run_config.json           # model, timeouts, submission cap, cooldown, auto-eval interval
├── agent_prompt.md           # the iterative-evaluation preamble the agent received
├── agent_output.txt          # full agent stdout for the run
├── auto_eval_ticks.log       # one line per host-initiated auto-evaluation
└── submissions/
    └── {agent,auto}-<n>/     # one directory per graded submission
        ├── submission.tar.gz # exactly the declared submit_paths
        ├── report.json       # score, validity, runtime, timestamp
        ├── eval.sh           # the verifier invocation used for this submission
        ├── allowed_files.txt # the submit manifest applied
        ├── test_output.txt   # full verifier stdout, including per-lane breakdown
        └── run_instance.log
```

Submissions are named by origin: `agent-<n>` for agent-initiated calls to `sforge-submit`, and
`auto-<n>` for the host's periodic auto-evaluation. Both are graded identically. The per-lane
breakdown in `test_output.txt` is the authoritative record of how a given score was composed.

## Reproduction

Each bundle ships in two forms simultaneously. Pick whichever fits your environment.

**Prebuilt images (fast path).** `[environment]` and `[verifier.environment]` in `task.toml` name
images hosted in the Mephisto container registry, pinned by both a content-hash tag and a `sha256`
digest. Pull once, run.

**From source (fully offline).** Every bundle also ships the complete build inputs:

```bash
cd <uuid>

# agent image
docker build -t mephisto-work  -f environment/Dockerfile environment/

# judge image
docker build -t mephisto-judge -f tests/Dockerfile       tests/
```

Both Dockerfiles are pinned to `python:3.11-slim` plus a fixed set of system packages, and every
file they `COPY` is committed alongside them, so `docker build` alone reproduces the identical
runtime with no hosted dependency beyond the base image and the pinned Python packages.

To score an existing submission, place the declared `submit_paths` at `/home/workspace/` in the
judge image and run `/tests/test.sh`. The reward lands at `/logs/verifier/reward.txt` and the
per-lane breakdown goes to stdout.

## Verification and quality assurance

- **Structure.** Every bundle carries the full seven-part tree with required files present and
  non-empty; `task.toml` and `task.json` agree on image tags, submit manifest and scoring
  convention; each bundle UUID is the deterministic UUIDv5 of its own canonical content hash.
- **Provenance.** Every task records its upstream source, data licence, licence class and licence
  source in `task.toml.metadata`, and `solution/TRUTH.md` carries the contract hash plus the full
  generation recipe: source endpoints, the boundary split, feature construction, and the reference
  method stage by stage.
- **Discriminative reward.** Every task ships a reference implementation under `solution/` that
  scores the task end to end, so the ceiling is attainable by construction, and a deliberately weak
  starter deliverable that scores at or near zero, so the floor is real.
- **Reward-hacking resistance.** The agent is never shown `tests/` or `solution/`. Both containers
  run `network_mode = "no-network"`, the judge is a separate image under
  `environment_mode = "separate"`, and only the declared `submit_paths` cross between them. Every
  self-reported metric is independently recomputed from the raw submitted output before it can earn
  a point.
- **Determinism.** Images are pinned by `sha256` digest, the reference solver seeds its own RNG,
  and the scorer is a pure function of the submitted output and the frozen held-out data.
- **Limitations.**
  - **Execution locus.** The submitted deliverable is re-executed *inside* the judge image, so the
    held-out data is on disk in the process that runs it. The no-future-data rule is a scoring
    contract, not a sandbox boundary.
  - **Boundary scope.** The information boundary is a property of the task, not of any particular
    model. It fixes what the bundle hands the agent; it cannot guarantee that a given model has not
    seen the underlying public series during pretraining.
  - **Answer key ships in the bundle.** `solution/` and `tests/hidden_test_data/` contain the
    graded truth in plaintext. Treat each task as single-use per model and exclude this repository
    from training corpora.
  - **Model nondeterminism.** Even at a fixed submission budget, temperature and internal reasoning
    traces produce per-run variance not captured by a single trajectory.

**Licensing.** Released under **CC BY-NC-ND 4.0** (Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International, copyright Ethara.AI 2026). The licence
covers the contents of this repository: task specs, scorers, reference solutions and recorded
trajectories. Share with attribution for non-commercial use, no derivatives. Underlying graded data
are public records whose own terms are recorded per bundle in `task.toml.metadata` and govern that
data independently. The runtime containers are *built on* private base images; the CC BY-NC-ND
grant on this repository does not extend to those upstream artefacts.
