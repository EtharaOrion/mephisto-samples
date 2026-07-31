---
license: cc-by-nc-nd-4.0
tags:
  - professional-knowledge-work
  - long-horizon
pretty_name: "Mephisto: Professional Knowledge Work Tasks"
size_categories:
  - n<1K
---

<div align="center">

# Mephisto: Professional Knowledge Work Tasks

<img src="assets/banner.webp" alt="Mephisto" width="100%" />

**A study of how autonomous agents learn from real-world environments.**

<p>
  <img src="https://img.shields.io/badge/Family-Professional%20Knowledge%20Work-16a34a?style=flat-square" alt="Professional Knowledge Work">
  <img src="https://img.shields.io/badge/Tasks-30-1f6feb?style=flat-square" alt="30 Tasks">
  <img src="https://img.shields.io/badge/Horizon-≥12h%20per%20task-f59e0b?style=flat-square" alt="≥12h per task">
  <img src="https://img.shields.io/badge/Grading-Deterministic%20·%20Post--cutoff-8957e5?style=flat-square" alt="Deterministic post-cutoff grading">
  <img src="https://img.shields.io/badge/License-CC%20BY--NC--ND%204.0-black?style=flat-square" alt="CC BY-NC-ND 4.0 License">
</p>

</div>

---

## Overview

Pretraining scaling laws revealed that model capability improves predictably with data and compute. But once agents are deployed, they must learn from *interaction* with real-world environments, and whether that learning obeys any clean scaling law was, until recently, unknown.

**Mephisto** distills the empirical and theoretical findings behind a large-scale study of agent and environment interaction across many real-world tasks. This dataset is the **Professional Knowledge Work** slice: white-collar decision deliverables graded not by a rubric of opinion but by **real, external, post-cutoff outcomes**: what actually happened after the agent's information boundary.

Every task hands the agent a decision a professional actually makes, at a frozen information boundary, then grades the deliverable against what the world actually did next. **The answer key is a record of events, not a rubric.** The graded outcome is drawn from public data published after the boundary the agent is given, and it is withheld at run time: the agent container has no network, and the held-out data exists only inside the judge image. Because the graded truth is a realized future outcome rather than a restatement of the boundary data, the deliverable cannot be gamed by echoing the past; it has to project what actually changes.

## Realistic, multi-level feedback

Real workflows are driven by rich feedback. Tasks are built for a **dual-loop protocol**:

- **Inner loop (local, agent-driven).** A writable workspace holding the public boundary data and a train/validation split the agent may iterate against freely. Unlimited fast iteration, no network.
- **Outer loop (judge-mediated).** Each submitted deliverable is graded by a hidden judge container against the private, post-cutoff outcome. The agent submits repeatedly over the run and the judge grades every submission; submissions are rate-limited by a cooldown and capped at a maximum (in the reference invocation, a 120 s cooldown and a 300-submission cap over the 12-hour budget), and the host additionally auto-evaluates the workspace on a fixed interval. Slower, authoritative, submission-gated.

The judge is deterministic: it re-executes the submitted deliverable against its own frozen post-cutoff data and scores only what that execution produces. Anti-fabrication is structural: every self-reported metric is independently recomputed from the raw submitted output, and a deviation beyond tolerance zeroes both the integrity lane and the primary lane for that window.

## What's in this dataset

30 task bundles. Each is one self-contained `<uuid>/` directory sitting at the repository root, with no intermediate collection directory:

```
mephisto/
├── <uuid>/                          # one self-contained task bundle (× 30)
├── assets/banner.webp
├── LICENSE
└── README.md
```

Every task has the same shape. Only the domain, the data, the decision boundary and the held-out grading window change.

## Bundle schema

Every bundle is the same seven-part tree:

```
<uuid>/
├── task.toml                        # Harbor task contract
├── task.json                        # the same contract for the sforge/EdgeBench runner
├── instruction.md                   # the full task brief handed to the agent
│
├── environment/                     # → the agent image
│   ├── Dockerfile
│   └── attachments/                 # everything public: data, specs, dependency list
│
├── tests/                           # → the judge image (agent never sees it)
│   ├── Dockerfile
│   ├── test.sh                      # harness adapter → /logs/verifier/reward.txt
│   ├── scoring/
│   │   ├── eval_script.py           # per-window runner; emits TOTAL_SCORE <N>
│   │   ├── score.py                 # the scoring lanes
│   │   ├── scorer_manifest.json     # entrypoint, required files, score parsing, failure policy
│   │   └── judge_requirements.txt
│   └── hidden_test_data/            # held-out data + the answer key
│
├── solution/                        # → the oracle (never uploaded to real agents)
│   ├── solve.sh
│   ├── <task>_reference.py
│   ├── reference_state.json
│   ├── requirements.txt
│   └── TRUTH.md                     # provenance + golden trajectory, judge-side only
│
└── trajectories/                    # → recorded reference runs
    └── <model-id>/
        ├── run_config.json          # model, timeouts, submission cap, cooldown, eval interval
        ├── agent_prompt.md          # the iterative-evaluation preamble the agent received
        ├── agent_output.txt
        ├── auto_eval_ticks.log
        └── submissions/
            └── {agent,auto}-<n>/    # one directory per graded submission
                ├── submission.tar.gz
                ├── report.json      # score, validity, runtime, timestamp
                ├── eval.sh
                ├── allowed_files.txt
                ├── test_output.txt
                └── run_instance.log
```

`<uuid>` is a deterministic UUIDv5 (fixed FORGE namespace) over the bundle's canonical SHA-256 content hash, so identical content maps to a stable id and distinct content is collision-resistant.

### `task.toml` / `task.json`: the contract

Both files pin the same runtime, in the two forms consumers need. `[environment]` and `[verifier.environment]` name the prebuilt images by tag **and** `sha256` digest; both carry `network_mode = "no-network"`. `[agent] timeout_sec` sets the run budget (12 h in the reference invocation) and `[verifier] timeout_sec` the grading budget, with `environment_mode = "separate"` keeping the judge in its own container. The top-level `artifacts` list and the `[extensions.sforge]` `submit_paths` / `submit_exclude` define exactly which files travel to the judge; `parser`, `selection` and `score_direction` fix the scoring convention. `[metadata]` records the upstream source and the licence class of the underlying public record.

`task.json` additionally embeds two things the runner needs inline: the full brief as `work.agent_query`, and the judge invocation as `judge.eval_cmd`. Both are copies of files that also ship unpacked in the bundle (`instruction.md` and `tests/test.sh`), so treat the unpacked files as the source of truth and regenerate `task.json` rather than editing it by hand.

### `instruction.md`: the brief

Delivered verbatim to the agent. It states the professional role and the decision boundary, the components the system must contain, the scoring lanes with their point weights and target/full-marks thresholds, the benchmark it is scored against, a table of every provided file, the hard constraints (exposure limits, costs, no future data, no network, per-invocation runtime ceilings), the exact deliverable filenames and output schema, and an explicit anti-fabrication warning.

### `environment/`: what the agent gets

`Dockerfile` builds the agent image and symlinks everything in `attachments/` into the workspace root. `attachments/` holds the entire public information boundary: the raw source data, any reference tables, an explicit train/validation period split, a deliverables guide, and the dependency list. Nothing observed after the decision boundary appears here. Because the container has no network, that dependency list is installed at build time and fixes what the agent can import; it is not an at-run-time install manifest.

### `tests/`: the judge

A separate, network-isolated image. `hidden_test_data/` carries the held-out data, the window definitions, and the labelled answer key. `eval_script.py` re-executes the submitted deliverable once per held-out window against that data, independently recomputes every self-reported metric from the raw submitted output (anti-fabrication), scores each window through `score.py`, and aggregates with the cross-window stability penalty and detection bonus. `test.sh` bridges the harness's artifact-delivery convention into that contract and writes a normalized reward. `scorer_manifest.json` declares the entrypoint, required submission and scoring files, the score-extraction regex and scale, and the failure policy for every degenerate case (missing submission, parse failure, non-zero exit).

### `solution/`: the oracle

A reference implementation that scores the task end to end, plus `TRUTH.md`: canary tokens, the contract hash, and the full generation recipe: source endpoints, the boundary split, feature construction, and the reference method stage by stage. Real evaluation agents never receive this directory; only the harness's oracle agent mounts it.

### `trajectories/`: recorded runs

One directory per evaluated model, holding the exact run configuration and every graded submission from that run, both agent-initiated (`agent-<n>`) and the harness's periodic auto-evaluations (`auto-<n>`), with the submitted archive and its scored report preserved for each.

## Reproducibility & image distribution

Each bundle ships in two forms simultaneously. Pick whichever fits your environment:

- **Prebuilt images (fast path).** `[environment]` and `[verifier.environment]` in `task.toml` name images hosted in the Mephisto container registry, pinned by both a 12-character content-hash tag and a `sha256` digest. Pull once, run.
- **From source (fully offline).** Every bundle also ships the complete build inputs: `environment/Dockerfile` + `environment/attachments/` for the agent image, and `tests/Dockerfile` + `tests/scoring/` + `tests/hidden_test_data/` for the judge. Both are pinned to `python:3.11-slim` plus a fixed set of system packages, and every file they `COPY` is committed alongside them, so `docker build` alone reproduces the identical runtime, with no hosted dependency beyond the base image and the pinned Python packages.

Grading integrity does not depend on hiding the outcome from bundle bytes. The graded truth is baked into the judge image at build time and is unreachable from the **agent** container while the agent works: both containers run with `network_mode = "no-network"`, the judge is a separate image under `environment_mode = "separate"`, and only the declared `submit_paths` cross from one to the other. `solution/` is likewise build-time material; the harness mounts it only for oracle runs, never for an evaluated agent. On top of that, every self-reported metric is independently recomputed from the raw submitted output before it can earn a point.

Two limits are worth stating plainly. The submitted deliverable is re-executed **inside** the judge image, so the held-out data is on disk in the process that runs it; the no-future-data rule is a scoring contract, not a sandbox boundary. And the "boundary" is a property of the task, not of any particular model: it fixes what the bundle hands the agent, and it cannot guarantee that a given model has not seen the underlying public series during pretraining.

Because each bundle ships its own answer key, treat these tasks as single-use per model, and exclude this repository from training corpora.

## License

Released under [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)](https://creativecommons.org/licenses/by-nc-nd/4.0/). Underlying graded data are public records; each bundle records its own `source_host`, `data_license`, `license_class` and `license_source` in the `[metadata]` block of its `task.toml`. © 2026 Ethara.AI.
