<p align="center"><img alt="Mephisto. Measured by a judge it never sees." src="images/hero.svg" width="880"></p>

<p align="center"><strong>Five professional knowledge work RL environments. Measured by a judge the agent never sees.</strong></p>

<p align="center"><a href="#contact"><img alt="Built by Ethara.AI. Organization badge." src="https://img.shields.io/badge/built%20by-Ethara.AI-8A2BE2"></a> <a href="#dataset-structure"><img alt="Five tasks. Bundle count badge." src="https://img.shields.io/badge/tasks-5-0D9488"></a> <a href="#summary"><img alt="Twelve hour horizon. Episode budget badge." src="https://img.shields.io/badge/horizon-12h%20per%20task-E63946"></a>

<p align="center"><sub><a href="#abstract">Abstract</a> &middot; <a href="#why-this-is-hard">Why this is hard</a> &middot; <a href="#difficulty">Difficulty</a> &middot; <a href="#dataset-structure">Dataset structure</a> &middot; <a href="#reproduction">Reproduction</a></sub></p>

# Mephisto: Professional Knowledge Work RL Environments

## Abstract

Mephisto publishes five reinforcement learning environments from the Professional Knowledge Work family. Each is a containerized workspace with a twelve hour interaction window, a continuous reward in `[0, 1]`, and a separate judge container holding evaluation assets the agent never sees, and each measures whether an agent improves across a long episode under repeated graded feedback instead of whether it produces one correct endpoint answer. This release establishes the structural contract: the two container work and judge split, the multi round delivery feedback protocol, and the full recorded submission history that makes an in-episode learning curve legible.

## Why this is hard

Take `e5d63160-7e3a-5d55-bab1-a887c9e97be3`, the FDIC Bank Capital Projection Book. The input is the full population of US FDIC-insured commercial banks, roughly four thousand active institutions, delivered as a 32.9 MB quarterly financials training file, an institutions reference, macro indicators, and the 12 CFR 6.4 prompt corrective action thresholds. The expected deliverable is a per-institution projection of twelve regulatory scalars, among them `IDT1CER`, `RBCRWAJ`, `NIMYQ` and `NCLNLSR`, plus a predicted PCA zone drawn from five fixed regulatory labels, plus asset and deposit growth rates, plus a `self_reported_metrics` block stating the solver's own error estimates.

The shortcut is to write plausible `self_reported_metrics` rather than recompute them from the fitted model. The judge recomputes every metric independently from the raw projections and the held-out truth. Deviation past `capital_ratio_mae > 0.05 pp`, `earnings_mape > 0.02`, `tail_mae > 0.05 pp`, `asset_growth_mae > 0.010`, `deposit_growth_mae > 0.010`, or `pca_zone_accuracy > 0.10` zeroes the `L7_anti_fabrication` lane and additionally zeroes the capital ratio and earnings lanes for the whole cycle, removing 40 of the 100 base points in one step.

Two further traps sit under the same task. Regulatory PCA thresholds are hard classification boundaries, so a solver that regresses a continuous ratio and thresholds it afterwards blurs the exact surface lane four grades. Institution heterogeneity is deliberate, so a solver that fits large-bank dynamics and carries them onto community banks below one billion dollars in assets loses the cross-size-bucket stability lane. The integrity class under test is reference-fidelity, enforced through the anti-fabrication gate.

## Difficulty

Difficulty is calibrated from measured frontier reward across 12-hour runs on Opus 4.8: higher mean best score maps to easier tasks. The five bundles span five tiers, and mean score decays monotonically across them, with the sharpest drop entering the Expert tier.

<p align="center"><img alt="Reward decay across difficulty tiers. Opus 4.8, 12-hour runs. Mean best score declines monotonically from Trivial (68.3) to Expert (15.3)." src="images/difficulty_reward_decay.png" width="820"></p>

| Tier | Bundle | Mean best score |
| --- | --- | --- |
| Trivial | `5cb28005` sec fundamental momentum calibration | 68.3 |
| Easy | `9c463536` treasury liquidity provisioning | 67.3 |
| Medium | `d3cd6658` sec leverage trajectory projection | 53.9 |
| Hard | `e5d63160` fdic bank capital projection | 39.8 |
| Expert | `60cab9e2` fed funds regime positioning | 15.3 |

## Contributions

- A two-container work and judge split, where the work container holds task materials and local validation tools and no hidden evaluation asset, and a host-side judge server mediates submission queues, cooldowns, authentication and asynchronous grading. To our knowledge no reviewed agent benchmark documents this architecture; [SWE-bench](https://arxiv.org/abs/2310.06770), [SWE-Lancer](https://arxiv.org/abs/2502.12115) and [MLE-bench](https://arxiv.org/abs/2410.07095) hide assets inside the same sandbox, and MLE-bench co-locates a validation server the agent can query.
- Multi-round delivery feedback that approximates a client review cycle. OpenAI's own [GDPval](https://arxiv.org/abs/2510.04374) writeup states that the current version does not go through multiple drafts, and the [Remote Labor Index](https://arxiv.org/abs/2510.26787) excludes work requiring direct client interaction by design.
- A full recorded submission history, agent-initiated and evaluator-only, retained so that an in-episode learning curve is recoverable after the run. Trajectory logging elsewhere targets efficiency analysis rather than learning measurement.
- A primary per-task continuous scalar in `[0, 1]` composed from eight weighted lanes and one bonus lane. Partial credit exists elsewhere, so the narrow claim is that the continuous score is the primary signal, not a secondary one.
- Depth inside named professional verticals rather than first coverage of them. [Agents' Last Exam](https://arxiv.org/abs/2606.05405) already spans law, finance and education across 55 subdomains.

## Summary

| Property | Value |
| --- | --- |
| Task bundles in this release | 5 |
| Capability family | Professional Knowledge Work |
| Agent interaction window | 43200 s per task |
| Verifier timeout | 3600 s |
| Verifier environment mode | `separate` container |
| Network | `no-network` on both work and judge containers |
| Reward | continuous, composed from a 110 point scale |
| Scored components | 8 weighted lanes plus 1 bonus lane |
| Submission cap | 300 per episode, 120 s cooldown |
| Evaluator-only snapshot interval | 1800 s |
| Base image | `python:3.11-slim`, non-root user `agent` |
| Underlying data | US Government work, public domain |
| Release license | CC BY-NC-ND 4.0 |

## Related work

| Benchmark | Publisher and date | Tasks | Agent episode budget | Reward signal | Judge isolation | Multi-round revision |
| --- | --- | --- | --- | --- | --- | --- |
| [GDPval](https://arxiv.org/abs/2510.04374) | OpenAI, 2025-10 | 1320, 220 open | not stated | human pairwise win, tie, loss | gold files open-sourced | no, stated as future work |
| [Agents' Last Exam](https://arxiv.org/abs/2606.05405) | UC Berkeley RDI, 2026-06 | ~1490, ~152 public | hours to weeks | milestone pass or fail scripts | hidden references, container split unconfirmed | no |
| [Remote Labor Index](https://arxiv.org/abs/2510.26787) | Scale AI and CAIS, 2025-10 | 240, 10 public | not stated | 3 point human scale, Elo secondary | manual expert review only | excluded by design |
| [SWE-Lancer](https://arxiv.org/abs/2502.12115) | OpenAI, 2025-02 | 1488, 502 public | 3 h, pass at 1 | binary end to end tests | hidden tests, same sandbox | no |
| [MLE-bench](https://arxiv.org/abs/2410.07095) | OpenAI, 2024-10 | 75 competitions | up to 24 h | medal threshold, percentile underneath | validation server inside agent container | no |
| [TheAgentCompany](https://arxiv.org/abs/2412.14161) | CMU, 2024-12 | 175 | ~27 steps | partial credit checkpoints | not architecturally separated | no |
| [OSWorld 2.0](https://arxiv.org/abs/2606.29537) | multi-institution, 2026-06 | 108 workflows | ~318 tool calls | binary plus continuous partial | environment state check | no |
| [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) | OpenAI, 2024-08 | 500 | single patch | binary hidden unit tests | hidden tests, same sandbox | no |
| [EdgeBench](https://arxiv.org/abs/2607.05155) | Ethara.AI, 2026-08 | 5 in this release | 12 h | continuous, 110 point composition | separate judge container | yes |

The 12 hour window is not the longest agent budget on this table, since MLE-bench grants 24 hours. The differentiating axes are the last two columns.

## Dataset structure

One self-contained bundle per task, addressed by UUID at the repository root. The work container and the judge container are built from disjoint subtrees, and nothing under `tests/` or `solution/` is ever mounted for the agent.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#1A0933","primaryTextColor":"#F5F3FF","primaryBorderColor":"#9B5DE5","lineColor":"#0D9488","textColor":"#9B5DE5","secondaryColor":"#0B0B10","tertiaryColor":"#0B0B10","clusterBkg":"#0B0B10","clusterBorder":"#E63946","fontFamily":"Helvetica Neue, Arial, sans-serif"}} }%%
flowchart TD
    subgraph E["environment, builds the work container"]
        E1["Dockerfile"]
        E2["attachments, task materials up to the information boundary"]
    end
    subgraph T["tests, builds the judge container, never mounted for the agent"]
        T1["test.sh, writes /logs/verifier/reward.txt"]
        T2["scoring: eval_script.py, score.py, scorer_manifest.json"]
        T3["hidden_test_data, held-out data and answer key"]
    end
    subgraph S["solution, private oracle tree"]
        S1["solve.sh, the executable oracle"]
        S2["TRUTH.md, the ground-truth record"]
    end
    subgraph J["trajectories, recorded runs"]
        J1["run_config.json, model and limits"]
        J2["submissions: agent-n and auto-n"]
    end
    U["bundle root, uuid"] --> C["task.toml and task.json, the task contract"]
    U --> I["instruction.md, the brief presented to the agent"]
    U --> E
    U --> T
    U --> S
    U --> J
```

`solution/TRUTH.md` is the ground-truth record: a human-readable statement of the route through `instruction.md` that satisfies every checker, step by step, naming the state each step establishes and the checker it satisfies. It never crosses into the agent-visible bundle.

## Trajectory structure

The protocol runs two loops. The inner loop is local and agent-driven, with a writable workspace, local validation and unlimited revision. The outer loop is judge-mediated, evaluating a submitted deliverable against hidden data, expert labels and rubric graders, and returning a calibrated score, a verdict and diagnostics. A third channel records evaluator-only snapshots on a fixed interval through the same hidden judge; those are retained for analysis and never shown to the agent.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#1A0933","primaryTextColor":"#F5F3FF","primaryBorderColor":"#9B5DE5","lineColor":"#0D9488","textColor":"#9B5DE5","secondaryColor":"#0B0B10","tertiaryColor":"#0B0B10","actorBkg":"#1A0933","actorTextColor":"#F5F3FF","signalColor":"#9B5DE5","signalTextColor":"#9B5DE5","fontFamily":"Helvetica Neue, Arial, sans-serif"}} }%%
sequenceDiagram
    participant A as Agent, work container
    participant H as Judge server, host side
    participant J as Judge container
    A->>A: inner loop, local validation and revision
    A->>H: submit deliverable, cap 300, cooldown 120 s
    H->>J: grade against hidden data and rubric graders
    J-->>H: calibrated score, verdict, diagnostics
    H-->>A: outer loop feedback, agent keeps working
    H->>J: evaluator-only snapshot every 1800 s
    J-->>H: recorded for analysis, withheld from the agent
```

The recorded submission counts below are properties of the published tree rather than statements about capability.

| Bundle | Agent-initiated | Evaluator-only | Total | Recorded resumes |
| --- | --- | --- | --- | --- |
| `9c463536` treasury liquidity provisioning | 282 | 23 | 305 | 0 |
| `5cb28005` sec fundamental momentum calibration | 267 | 23 | 290 | 0 |
| `e5d63160` fdic bank capital projection | 263 | 23 | 286 | 17 |
| `d3cd6658` sec leverage trajectory projection | 243 | 23 | 266 | 0 |
| `60cab9e2` fed funds regime positioning | 172 | 23 | 195 | 1 |

## Scoring methodology

Every bundle composes 100 base points across eight lanes plus a 10 point adaptation bonus, and the verifier writes a single scalar. Each lane is a linear ramp between a zero anchor and a full-marks anchor, so partial competence earns partial credit and the composition stays interpretable. The bank capital bundle allocates its lanes as follows.

| Lane | Points | Full marks anchor | Zero anchor |
| --- | --- | --- | --- |
| `L1_capital_ratio_projection_accuracy` | 25 | MAE 0.4 pp | MAE 3.5 pp |
| `L2_earnings_projection_accuracy` | 15 | MAPE 10% | MAPE 50% |
| `L3_tail_risk_control` | 15 | MAE 0.10 pp | MAE 1.0 pp |
| `L4_pca_zone_classification_accuracy` | 10 | accuracy 80% | accuracy 20% |
| `L5_asset_growth_projection` | 10 | MAE 0.010 | MAE 0.080 |
| `L6_deposit_stability_projection` | 10 | MAE 0.012 | MAE 0.080 |
| `L7_anti_fabrication` | 5 | self-report matches recomputation | any tolerance breached |
| `L8_cross_size_bucket_stability` | 10 | uniform quality across size buckets | one bucket carries the score |
| `pca_zone_transition_bonus` | 10 | 3 detected transitions | none detected |

The reference implementations were tuned at authoring time to land inside a design band on this 110 point scale.

## Threat model

| Threat | Control |
| --- | --- |
| Contamination from public data already in pretraining | Task bytes are frozen and content-addressed, test windows are held out by date, and each bundle carries canary tokens that surface memorized leakage. |
| Reward hacking by fabricating self-reported metrics | The judge recomputes every reported metric from raw outputs, and a breach zeroes the integrity lane plus the primary lanes it guards. |
| Verifier attack surface from a hostile solver | The judge runs in a separate container with no network, built from a subtree never mounted into the work container, and the submit manifest limits what crosses the boundary. |
| Private-boundary leakage from the oracle tree | `solution/` is uploaded only for oracle validation runs, never for evaluation agents, and `TRUTH.md` never enters the agent-visible bundle. |
| Overfitting to visible checks | Local validation and hidden grading are disjoint, and the evaluator-only snapshot channel measures progress the agent cannot optimize against. |

## Reproduction

Every structural figure in this document recomputes from the public tree under a pinned interpreter.

```bash
python3.11 - <<'PY'
import pathlib, re
root = pathlib.Path(".")
bundles = sorted(p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"[0-9a-f-]{36}", p.name))
print("bundles", len(bundles))
for b in bundles:
    subs = sorted((b / "trajectories").glob("*/submissions/*"))
    agent = sum(1 for s in subs if s.name.startswith("agent-"))
    auto = sum(1 for s in subs if s.name.startswith("auto-"))
    toml = (b / "task.toml").read_text()
    timeout = re.search(r"timeout_sec\s*=\s*(\d+)", toml).group(1)
    print(b.name, "agent", agent, "auto", auto, "total", len(subs), "agent_timeout_sec", timeout)
PY
```

## Verification and quality assurance

Four gates hold today. Task bytes are content-addressed, so a bundle identifier changes when its content changes. The judge container builds from a subtree that is never mounted for the agent, so the isolation claim is checkable by reading the image definitions. Every bundle ships an executable oracle and a written ground-truth record, so the task is demonstrably solvable by a stated route. Both containers run with networking disabled, so a solver cannot fetch the answer.

## Who this is for

| Reader | Next action |
| --- | --- |
| Agent researchers measuring long-horizon learning | Read one `instruction.md`, then the matching `scoring/` tree, and compare the two loops against your own harness. |
| Benchmark authors designing verifiers | Read `tests/` and the anti-fabrication lane, then reuse the recompute-and-compare pattern. |
| Practitioners in regulated finance | Read `solution/TRUTH.md` for the route a domain expert would take through the deliverable. |

## Cite

```bibtex
@misc{edgebench_2026,
  title        = {EdgeBench: Professional Knowledge Work RL Environments},
  author       = {{Ethara.AI}},
  year         = {2026},
  howpublished = {Sample release of five task bundles},
  url          = {https://github.com/Ethara-Ai}
}
```

## License

Released under CC BY-NC-ND 4.0, Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International, copyright Ethara.AI 2026. Share with attribution for non-commercial use, no derivatives. The underlying data are public records whose own terms are recorded per bundle in `task.toml` metadata and govern that data independently.

## Contact

Work with us, report a flaw, or send a bundle. The organization page is [Ethara.AI on GitHub](https://github.com/Ethara-Ai). Security disclosures follow the address published in `SECURITY.md` in the parent repository. Contribution routes and review expectations are documented in `CONTRIBUTING.md`.
