---
license: cc-by-nc-nd-4.0
tags: - professional-knowledge-work
  - long-horizon
pretty_name: "Mephisto — Professional Knowledge Work Tasks"
size_categories:
  - n<1K
---
<div align="center">

---

## Overview

Pretraining scaling laws revealed that model capability improves predictably with data and compute. But once agents are deployed, they must learn from *interaction* with real-world environments, and whether that learning obeys any clean scaling law was, until recently, unknown.

**Mephisto** distills the empirical and theoretical findings behind a large-scale study of agent and environment interaction across many real-world tasks. This dataset is the **Professional Knowledge Work** slice: white-collar decision deliverables graded not by a rubric of opinion but by **real, external, post-cutoff outcomes** — what actually happened after the agent's information boundary.

Every task hands the agent a decision a professional actually makes (allocate a supervisory budget, target inspections, flag which entities will cross into distress) at a frozen information boundary, then grades the deliverable against the settled real-world result. **Nobody authored the answer key.** The graded truth is a public record filed by thousands of independent parties after the agent's cutoff, so it cannot have been memorized before the cutoff, and it is withheld from the agent by network isolation at run time. Because the graded truth is a future outcome rather than a restatement of the boundary data, the deliverable cannot be gamed by echoing the past — it has to predict what actually changes.

## Realistic, multi-level feedback

Real workflows are driven by rich feedback. Tasks are built for a **dual-loop protocol**:

- **Inner loop (local, agent-driven).** A writable workspace with the public boundary data, the exact (public) scorer, and a starter deliverable. Unlimited fast iteration.
- **Outer loop (judge-mediated).** Each submitted deliverable is graded by a hidden judge container against the private, post-cutoff outcome. The agent submits repeatedly over the run and the judge grades every submission; submissions are rate-limited by a cooldown and capped at a maximum (in the reference invocation, a 120 s cooldown and a 400-submission cap over the 12-hour budget), and the host additionally auto-evaluates the workspace on a fixed interval. Slower, authoritative, submission-gated.

The judge is deterministic and pure: it reads only the weights the submitted policy returns and its own frozen outcome. A static allowlist gate blocks any attempt to exfiltrate the hidden answer; anti-fabrication blocks any self-reported score.

## What's in this dataset

30 task bundles, one per `<uuid>/task.json`, where `<uuid>` is a deterministic UUIDv5 (fixed FORGE namespace) over the bundle's canonical SHA-256 content hash, so identical content maps to a stable id and distinct content is collision-resistant.

The tasks come in two archetypes:

**Allocation books (17)** — distribute a finite attention/exposure budget across a universe, graded on the realized outcome the book covered.

| Task                                     | Domain                      |
| ---------------------------------------- | --------------------------- |
| `fdic_bank_credit_surveillance`        | finance / banking           |
| `nport_liquidity_provisioning`         | finance / funds             |
| `cms_ma_retention_provisioning`        | healthcare / plans          |
| `cfpb_complaint_surge_surveillance`    | finance / consumer          |
| `sec_opmargin_expansion_book`          | finance / corporate         |
| `sec_leverage_expansion_book`          | finance / corporate         |
| `pell_grant_disbursement_growth`       | education / access          |
| `dl_disbursement_growth`               | education / access          |
| `fafsa_completion_provisioning`        | education / access          |
| `txmeal_participation_outreach`        | education / access          |
| `nyc_restaurant_inspection_targeting`  | enforcement / municipal     |
| `chicago_food_inspection_targeting`    | enforcement / municipal     |
| `chicago_building_code_book`           | enforcement / municipal     |
| `montgomery_food_safety_book`          | enforcement / public-health |
| `bts_station_reliability_provisioning` | transport                   |
| `tx_mixedbev_tax_book`                 | public finance              |
| `chicago_taxi_revenue_book`            | public finance / municipal  |

**Breach-triage watchlists (13)** — flag the entities that will cross into a worst-case band next period, graded by precision-recall over the realized crossing.

| Task                                         | Domain                                  |
| -------------------------------------------- | --------------------------------------- |
| `bank_supervisory_watchlist`               | finance / banking                       |
| `nport_liquidity_watchlist`                | finance / funds                         |
| `cms_ma_retention_watchlist`               | healthcare / plans                      |
| `cfpb_surge_watchlist`                     | finance / consumer                      |
| `sec_margin_collapse_watchlist`            | finance / corporate                     |
| `sec_leverage_distress_watchlist`          | finance / corporate                     |
| `pell_disbursement_shortfall_watchlist`    | education / access                      |
| `dl_disbursement_collapse_watchlist`       | education / access                      |
| `txmeal_participation_shortfall_watchlist` | education / access                      |
| `nyc_restaurant_closure_risk_watchlist`    | enforcement / municipal                 |
| `tx_mixedbev_collapse_watchlist`           | public finance                          |
| `chicago_taxi_collapse_watchlist`          | public finance / municipal              |
| `oss_dependency_abandonment_watchlist`     | open-source software / package registry |

## Bundle schema

```
ethara/mephisto/
├── <uuid>/
│   ├── task.json                 # self-contained bundle spec
│   ├── base/
│   │   └── Dockerfile            # base image: python:3.11 + system deps + agent user
│   ├── work/
│   │   ├── Dockerfile            # agent workspace image, atop base
│   │   └── setup_workspace.sh    # provisions boundary data, scorer, allowlist gate, starter deliverable
│   └── judge/
│       ├── Dockerfile            # grader image, atop base
│       └── setup_judge.sh        # provisions hidden outcome, allowlist gate, runner, score.py
├── assets/banner.webp
└── README.md
```

Each `task.json` carries `task_id`, `category`, `base_image`, `cwd`, `internet: false`, the submit manifest, and `work.image_tag` / `judge.image_tag` — 12-character content hashes pointing at prebuilt, hosted images. Grading is deterministic against a real, post-cutoff outcome.

## Reproducibility & image distribution

Each bundle ships in two forms simultaneously — pick whichever fits your environment:

- **Prebuilt images (fast path).** `work.image_tag` and `judge.image_tag` in `task.json` are 12-character content hashes for images hosted in the Mephisto container registry. Pull once, run.
- **From source (fully offline).** Every bundle also ships the complete build inputs: `base/Dockerfile` (pinned to `python:3.11` plus a fixed set of system packages and an `agent` user), `work/Dockerfile` + `setup_workspace.sh`, `judge/Dockerfile` + `setup_judge.sh`. The setup scripts are self-contained shell — they base64/gunzip inline payloads into place and fetch nothing over the network — so `docker build` alone reproduces the identical runtime with no hosted dependencies beyond `python:3.11`.

The `work/` and `judge/` Dockerfiles currently `FROM` the hosted base image tag for convenience; consumers building fully from source can retag their locally-built `base/` image to match (or edit the `FROM` line) — the sibling `base/Dockerfile` is the authoritative recipe.

Grading integrity does not depend on hiding the outcome from bundle bytes. The graded truth is provisioned into the judge image at build time and is unreachable from the agent's workspace at run time: the agent container runs with `internet: false`, the judge lives in a separate container, a static allowlist gate blocks any import outside a fixed set of pure-stdlib maths modules, and an anti-fabrication check rejects any self-reported score. The earlier `setup_cmds` form (which inlined the build recipe into `task.json`) has been fully retired in favor of the standard Dockerfile layout above.

## License

Released under [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)](https://creativecommons.org/licenses/by-nc-nd/4.0/). Underlying graded data are public records from their respective sources — government open-data portals (federal and municipal) and, for the software task, public package-registry release metadata. © 2026 Ethara.AI.
