<p align="center">
  <img src="assets/banner.webp" alt="Mephisto: professional knowledge work RL environments" width="880">
</p>

<p align="center">
  <strong>Professional knowledge work RL environments, built to measure learning rather than endpoint success.</strong>
</p>

<p align="center">
  <a href="#design-goals"><img alt="Built by Ethara.AI" src="https://img.shields.io/badge/built%20by-Ethara.AI-ee00ee.svg"></a>
  <a href="#bundle-structure"><img alt="Tasks: 30" src="https://img.shields.io/badge/tasks-30-35d0ba.svg"></a>
  <a href="#design-goals"><img alt="Horizon: 12h per task" src="https://img.shields.io/badge/horizon-12h_per_task-845EF7.svg"></a>
  <a href="#feedback-loop-and-evaluation-protocol"><img alt="Verifier: offline, separate container" src="https://img.shields.io/badge/verifier-offline_·_separate_container-ff6b6b.svg"></a>
</p>

<p align="center"><sub>
  <a href="#design-goals">Design goals</a> · <a href="#feedback-loop-and-evaluation-protocol">Feedback loop</a> · <a href="#scaling-laws-of-learning-from-real-world-environments">Scaling laws</a> · <a href="#bundle-structure">Bundle</a>
</sub></p>

# Mephisto Samples: Professional Knowledge Work RL Environments

Each task is a self-contained RL environment: a containerized workspace, a 12-hour interaction
window, a continuous reward in `[0, 1]`, and a separate judge container holding evaluation assets
the agent never sees. This repository is a **30-task** sample from the Professional Knowledge Work
family.

## Design goals

The benchmark measures whether an autonomous agent can **learn from experience in an unfamiliar
real world environment**. That requires two properties most evaluations lack.

**Ultra-long-horizon tasks.** Learning behaviours such as exploration, strategy revision and
experience accumulation need time and complexity to emerge. Short tasks are usually solved from
memory rather than learning. Professional Knowledge Work instantiates this as real white-collar
deliverables across domains such as finance, education, healthcare and legal, sized to match work
that would take a human professional with three or more years of experience roughly three full
days. Every task supports a frontier model running for at least 12 hours without saturating.

**Realistic, multi-level feedback.** Human experts learn from rich feedback: test failures,
authoritative judgments, unexpected results. A benchmark that cannot offer that cannot measure
learning, and leaves the agent guessing what the evaluation rewards. In this family the feedback is
carefully designed rubrics and multi-round delivery feedback that approximate real client review
cycles, so an agent can learn from structured critique and revise iteratively.

## Feedback loop and evaluation protocol

Real professional workflows rarely provide a single final answer check. Practitioners iterate
through two complementary loops: a fast local loop for exploration and refinement, and a slower
external loop that provides authoritative calibration through review or delivery. The local loop
enables rapid progress; the external loop guards against overfitting to visible checks and exposes
failures the practitioner's own checks do not capture.

Mephisto adopts this dual-loop structure to measure learning rather than endpoint success:

- **Inner loop.** Local and agent-driven. The agent inspects a writable workspace, runs its own
  validation, observes errors and revises its deliverable, as often as it likes.
- **Outer loop.** Judge-mediated. Submitted deliverables are evaluated against hidden data, expert
  labels and rubric graders, returning calibrated scores, verdicts or diagnostics.

The protocol runs on an isolated work-judge harness. The agent works inside a work container
holding the task materials and local validation tools but **no hidden evaluation assets**, and
submits to a separate judge container that runs the hidden evaluation. A host-side judge server
mediates the outer loop, handling submission queues, cooldowns, authentication and asynchronous
grading, so the agent keeps working while a submission is being judged.

For trajectory measurement the harness also performs host-side auto-evaluation at fixed intervals.
These snapshots are scored through the same hidden judge and recorded for analysis, but are **not
shown to the agent**, preserving the distinction between agent-visible feedback and evaluator-only
measurement.

## Scaling laws of learning from real world environments

Pretraining scaling laws model language-model loss as a power law in training scale. Agents also
continue to learn *after* deployment, by interacting with an environment, and whether that learning
obeys a comparable law is the question these environments are built to answer. The 12-hour window
and the full recorded submission history are what make a learning trajectory measurable in the
first place, rather than a single endpoint score.

## Bundle structure

One self-contained bundle per task, addressed by UUID, at the repository root:

```
<uuid>/
├── task.toml                 # task contract: images, timeouts, submit manifest, metadata
├── task.json                 # the same contract for the sforge runner
├── instruction.md            # the brief presented to the agent
│
├── environment/              # builds the work container
│   ├── Dockerfile
│   └── attachments/          # task materials, up to the information boundary
│
├── tests/                    # builds the judge container (never mounted for the agent)
│   ├── Dockerfile
│   ├── test.sh               # verifier entrypoint; writes /logs/verifier/reward.txt
│   ├── scoring/              # eval_script.py, score.py, scorer_manifest.json
│   └── hidden_test_data/     # held-out data + the answer key
│
├── solution/                 # private oracle tree
│   ├── solve.sh              # the executable oracle
│   ├── TRUTH.md              # the task's ground-truth record
│   └── ...                   # reference implementation and its dependencies
│
└── trajectories/             # recorded runs
    └── <model-id>/
        ├── run_config.json   # model, timeouts, submission cap, cooldown, eval interval
        └── submissions/      # agent-<n> (agent-initiated) and auto-<n> (evaluator-only)
```

`solution/TRUTH.md` is the task's **ground-truth record**: a human-readable statement of the route
through `instruction.md` that satisfies every checker, step by step, naming the state each step
establishes and the checker it satisfies. It never crosses into the agent-visible bundle.


**Licensing.** Released under **CC BY-NC-ND 4.0** (Creative Commons
Attribution-NonCommercial-NoDerivatives 4.0 International, copyright Ethara.AI 2026). Share with
attribution for non-commercial use, no derivatives. Underlying data are public records whose own
terms are recorded per bundle in `task.toml.metadata` and govern that data independently.
