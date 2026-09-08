#!/usr/bin/env python3
"""Recompute: derives the entire cftc_futures_positioning_book bundle.

FORGE Invariant 3: ONE script derives both the golden trajectory and the
checker fixtures from the SAME source. Under frozen bytes the result is
bit-identical on re-run.

Inputs (all under this directory's _raw/):
    cftc_cot_2022_2025.json   - CFTC COT training data (pre-boundary)
    cftc_cot_2026.json         - CFTC COT graded data (post-boundary)
    fred_macro.json            - FRED DFF/IORB/DGS series
    macro_calendar.json        - FOMC + CPI 2025-2026 dates
    eia_crude_stocks.json      - EIA (empty; B1 defaults to 0)

Outputs (dataset/<uuid>/):
    task.toml
    instruction.md
    environment/
      data/
        cot_history_train.csv     - agent-visible COT training data
        macro_train.csv           - agent-visible macro time series
        markets_universe.csv      - the 25-market universe
        macro_calendar.csv        - FOMC + CPI dates
        cftc_book_lib.py          - scoring library (agent gets it)
        deliverables_guide.md
      requirements.txt
      Dockerfile
    tests/
      Dockerfile
      test.sh
      scoring/
        cot_graded_truth.csv      - judge-private ground truth
        judge.py                  - scoring engine
        cftc_book_lib.py          - same lib as agent
    solution/
      grounding.yaml
      recompute.py                - this script
      reference_solver.py
      solve.sh
      TRUTH.md
      rubrics.json
      provenance.yaml

Bundle uuid computed as UUIDv5 over canonical content hash.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import pickle
import shutil
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "_raw"
sys.path.insert(0, str(HERE))
import cftc_book_lib as CL

FORGE_TASK_NAMESPACE = uuid.UUID("c53e8f3b-526f-52c0-a04e-89e2269b237d")

CANARIES = [
    "MEPHISTO_CANARY_CFBP_2026_08_06_K7X3M9Q2",
    "MEPHISTO_CANARY_CFBP_2026_08_06_R5V1B8N4",
    "MEPHISTO_CANARY_CFBP_2026_08_06_L9P6T2W3",
]

# ---------------------------------------------------------------------------
# Load raw data
# ---------------------------------------------------------------------------
def load_cot():
    with open(RAW / "cftc_cot_2022_2025.json") as f:
        a = json.load(f)
    with open(RAW / "cftc_cot_2026.json") as f:
        b = json.load(f)
    rows = a + b
    seen = set()
    clean = []
    for r in rows:
        code = r.get(CL.CODE_FIELD, "")
        date = str(r.get(CL.DATE_FIELD, ""))[:10]
        key = (code, date)
        if code not in CL.CODE_TO_MID or key in seen:
            continue
        seen.add(key)
        r["_mid"] = CL.CODE_TO_MID[code]
        r["_date"] = date
        clean.append(r)
    clean.sort(key=lambda r: (r["_mid"], r["_date"]))
    return clean


def load_fred():
    with open(RAW / "fred_macro.json") as f:
        return json.load(f)


def load_calendar():
    with open(RAW / "macro_calendar.json") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Compute derived structures
# ---------------------------------------------------------------------------
def split_train_graded(rows):
    train = [r for r in rows if r["_date"] <= CL.BOUNDARY]
    graded = [r for r in rows
              if CL.GRADED_START <= r["_date"] <= CL.GRADED_END]
    return train, graded


def compute_ground_truth(train, graded):
    """For each (mid, week) in graded: derive true direction, magnitude,
    regime, and extreme flag using boundary_stats and next-week comm_net."""
    stats = CL.compute_boundary_stats(train)
    by_mid_graded = {}
    for r in graded:
        by_mid_graded.setdefault(r["_mid"], []).append(r)
    for mid in by_mid_graded:
        by_mid_graded[mid].sort(key=lambda r: r["_date"])

    truth = {}
    by_mid_train = {}
    for r in train:
        by_mid_train.setdefault(r["_mid"], []).append(r)
    for mid in by_mid_train:
        by_mid_train[mid].sort(key=lambda r: r["_date"])

    for mid, rows in by_mid_graded.items():
        mstats = stats.get(mid)
        if not mstats:
            continue
        # For direction we need the FOLLOWING week's commercial net.
        # Chain: [last training row] + graded rows in order.
        tail = by_mid_train.get(mid, [])[-1:]
        chain = tail + rows
        for i in range(len(chain) - 1):
            curr = chain[i]
            nxt = chain[i + 1]
            if not (CL.GRADED_START <= curr["_date"] <= CL.GRADED_END):
                continue
            curr_net = CL.comm_net(curr)
            nxt_net = CL.comm_net(nxt)
            change = nxt_net - curr_net
            direction = "up" if nxt_net > curr_net else "down"
            mag = CL.magnitude_bucket(change, mstats["mag_q1"], mstats["mag_q3"])
            regime = CL.crowding_regime(curr_net, mstats["p10_3yr"], mstats["p90_3yr"])
            extreme = CL.extreme_flag(curr_net, mstats["p10_3yr"], mstats["p90_3yr"])
            truth[(mid, curr["_date"])] = {
                "direction": direction,
                "magnitude_bucket": mag,
                "crowding_regime": regime,
                "extreme_positioning_flag": extreme,
            }
    return truth, stats


def compute_uuid(bundle_root):
    """UUIDv5 over canonical content hash of the bundle.

    Excludes trajectories/ per FORGE.md :30.
    """
    h = hashlib.sha256()
    files = []
    for root, dirs, fnames in os.walk(bundle_root):
        dirs.sort()
        if "trajectories" in dirs:
            dirs.remove("trajectories")
        for f in sorted(fnames):
            files.append(Path(root) / f)
    for fp in sorted(files, key=lambda p: str(p.relative_to(bundle_root))):
        rel = str(fp.relative_to(bundle_root)).encode()
        h.update(rel)
        with open(fp, "rb") as fh:
            h.update(fh.read())
    canonical_hash = h.hexdigest()
    bundle_uuid = str(uuid.uuid5(FORGE_TASK_NAMESPACE, canonical_hash))
    return canonical_hash, bundle_uuid


# ---------------------------------------------------------------------------
# Emit agent-visible tree
# ---------------------------------------------------------------------------
def emit_agent_environment(train, fred, cal, env_dir):
    (env_dir / "data").mkdir(parents=True, exist_ok=True)

    # COT training data
    with open(env_dir / "data" / "cot_history_train.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["market_id", "week_ending", "code",
                    "comm_long", "comm_short", "noncomm_long",
                    "noncomm_short", "open_interest",
                    "change_in_comm_long", "change_in_comm_short",
                    "traders_tot"])
        for r in train:
            w.writerow([
                r["_mid"], r["_date"], r.get(CL.CODE_FIELD, ""),
                r.get("comm_positions_long_all", ""),
                r.get("comm_positions_short_all", ""),
                r.get("noncomm_positions_long_all", ""),
                r.get("noncomm_positions_short_all", ""),
                r.get("open_interest_all", ""),
                r.get("change_in_comm_long_all", ""),
                r.get("change_in_comm_short_all", ""),
                r.get("traders_tot_all", ""),
            ])

    # Macro time series (flatten FRED dict)
    with open(env_dir / "data" / "macro_train.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "series", "value"])
        for sid, rows in fred.items():
            for r in rows:
                d = r["date"]
                # only keep <= boundary + a small buffer for warm-start
                if d <= "2024-12-31":
                    w.writerow([d, sid, r["value"]])

    # Markets universe reference
    with open(env_dir / "data" / "markets_universe.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["market_id", "cftc_code", "name"])
        NAMES = {
            "CL":"WTI Crude Oil", "NG":"Natural Gas", "RB":"RBOB Gasoline",
            "HO":"Heating Oil", "GC":"Gold", "SI":"Silver", "HG":"Copper",
            "PL":"Platinum", "C":"Corn", "S":"Soybeans", "W":"Wheat SRW",
            "KW":"Wheat HRW", "LC":"Live Cattle", "LH":"Lean Hogs",
            "ZB":"30Y US T-Bond", "ZN":"10Y US T-Note", "ZF":"5Y US T-Note",
            "ZT":"2Y US T-Note", "EC":"Euro FX", "JY":"Japanese Yen",
            "BP":"British Pound", "AD":"Australian Dollar",
            "CD":"Canadian Dollar", "ES":"S&P 500 E-mini", "NQ":"Nasdaq 100 E-mini",
        }
        for mid in CL.MARKET_IDS:
            w.writerow([mid, CL.MARKETS[mid], NAMES.get(mid, "")])

    # Macro calendar (FOMC + CPI) - all published/scheduled, agent-visible
    with open(env_dir / "data" / "macro_calendar.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_type", "date"])
        for d in cal["fomc"]:
            w.writerow(["FOMC", d])
        for d in cal["cpi"]:
            w.writerow(["CPI", d])

    # Scoring library - copied as-is (agent gets same file as judge)
    shutil.copy(HERE / "cftc_book_lib.py",
                env_dir / "data" / "cftc_book_lib.py")

    # requirements.txt
    (env_dir / "requirements.txt").write_text(
        "# Only stdlib, numpy, and pandas are permitted.\n"
        "numpy==2.1.3\n"
        "pandas==2.2.3\n"
    )

    # Deliverables guide
    (env_dir / "data" / "deliverables_guide.md").write_text(
        _DELIVERABLES_GUIDE_MD)

    # Agent Dockerfile
    (env_dir / "Dockerfile").write_text(
        "FROM python:3.11-slim\n\n"
        "ENV DEBIAN_FRONTEND=noninteractive\n"
        "ENV TZ=Etc/UTC\n"
        "ENV PYTHONDONTWRITEBYTECODE=1\n"
        "ENV PYTHONUNBUFFERED=1\n\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
        "      git curl jq build-essential ca-certificates sudo xz-utils \\\n"
        "    && rm -rf /var/lib/apt/lists/* \\\n"
        "    && useradd -m -s /bin/bash -u 1000 agent \\\n"
        "    && echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \\\n"
        "    && git config --global safe.directory '*'\n\n"
        "RUN mkdir -p /home/workspace && chown -R agent:agent /home/workspace\n"
        "WORKDIR /home/workspace\n\n"
        "COPY requirements.txt /home/workspace/attachments/requirements.txt\n"
        "RUN pip install --no-cache-dir -r /home/workspace/attachments/requirements.txt\n\n"
        "COPY data/ /home/workspace/attachments/\n"
        "RUN for f in /home/workspace/attachments/*; do \\\n"
        "      base=$(basename \"$f\"); \\\n"
        "      ln -sf \"attachments/$base\" \"/home/workspace/$base\"; \\\n"
        "    done \\\n"
        "    && chown -R agent:agent /home/workspace\n\n"
        "USER agent\n"
        "CMD [\"python3\"]\n"
    )


_DELIVERABLES_GUIDE_MD = """# Deliverables Guide

## Files to submit

Submit these three files to `/home/workspace/`:

1. `cftc_positioning.py` - runnable Python with two CLI modes:
   - `python3 cftc_positioning.py --train <input_dir> <state_json>` (fit)
   - `python3 cftc_positioning.py --backtest <input_dir> <state_json> <output_json>` (predict)
2. `requirements.txt` - dependency list (numpy, pandas, stdlib only)
3. `positioning_results.json` - full deliverable per output schema

## Output schema

```json
{
  "task_id": "cftc_futures_positioning_book",
  "bundle_uuid": "<uuid>",
  "per_week": [
    {
      "week_ending": "2025-01-07",
      "per_market": [
        {
          "market_id": "CL",
          "commercial_net_direction": "up",
          "magnitude_bucket": "small_increase",
          "crowding_regime": "neutral",
          "extreme_positioning_flag": false,
          "direction_probability": 0.55,
          "self_reported_certainty": 0.6
        }
      ]
    }
  ],
  "self_reported_metrics": {
    "L1_commercial_direction_est": 0.58,
    "L2_magnitude_bucket_est": 0.32,
    "L3_crowding_regime_est": 0.45,
    "L4_extreme_flag_f1_est": 0.42,
    "L5_rank_correlation_est": 0.15
  },
  "per_item_confidence": {
    "CL:2025-01-07": 0.62,
    "NG:2025-01-07": 0.55
  }
}
```

The `per_item_confidence` dict maps `"<market_id>:<week_ending>"` keys to a
float in `[0, 1]` expressing your confidence that the corresponding
`commercial_net_direction` prediction is correct. Feeds the L7 lane below.

## Constraint reminders

- Values in `per_market` MUST use exactly the vocabulary in `cftc_book_lib.py`:
  `VALID_DIRECTIONS`, `VALID_MAGNITUDES`, `VALID_REGIMES`.
- `direction_probability` and `self_reported_certainty` are floats on `[0, 1]`.
- No future data: for week_ending D, use only COT data with report_date < D.
- No network: `network_mode = no-network`.
- Per-observation budget: full backtest MUST complete in <= 30 minutes.

## L7 confidence calibration (Brier)

The judge computes a Brier score over your `per_item_confidence` versus the
realized correctness of each L1 direction prediction:

    BS = mean_i (confidence_i - correct_i)^2

where `correct_i = 1` if your direction matched reality else `0`. Points:

    pts = 5 * max(0, 1 - 2 * BS)

BS=0 -> 5 pts, BS=0.25 -> 2.5 pts, BS>=0.5 -> 0 pts. Random 0.5 confidence
on a 50/50 base rate yields BS=0.25 (calibration break-even). Missing or
malformed `per_item_confidence` -> 0 pts. `self_reported_metrics` is retained
for informational use but no longer gates L7.
"""


# ---------------------------------------------------------------------------
# Emit judge-private tree
# ---------------------------------------------------------------------------
def emit_judge_tests(train, graded, ground_truth, boundary_stats, fred, cal, tests_dir):
    (tests_dir / "scoring").mkdir(parents=True, exist_ok=True)

    # Ground truth CSV
    with open(tests_dir / "scoring" / "cot_graded_truth.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["market_id", "week_ending", "direction",
                    "magnitude_bucket", "crowding_regime",
                    "extreme_positioning_flag"])
        for (mid, wk), gt in sorted(ground_truth.items()):
            w.writerow([mid, wk, gt["direction"],
                        gt["magnitude_bucket"], gt["crowding_regime"],
                        str(gt["extreme_positioning_flag"]).lower()])

    # Judge scorer  (imports cftc_book_lib for shared scoring functions)
    shutil.copy(HERE / "cftc_book_lib.py", tests_dir / "scoring" / "cftc_book_lib.py")
    shutil.copy(HERE / "judge.py", tests_dir / "scoring" / "judge.py")

    # test.sh entrypoint (Harbor-standard)
    (tests_dir / "test.sh").write_text(
        "#!/bin/bash\n"
        "set +e\n"
        "mkdir -p /logs/verifier /home/workspace\n"
        "\n"
        "for f in /logs/artifacts/*; do\n"
        "  [ -f \"$f\" ] || continue\n"
        "  cp \"$f\" \"/home/workspace/$(basename \"$f\")\"\n"
        "done\n"
        "\n"
        "if [ -f /home/workspace/requirements.txt ]; then\n"
        "  pip install --user --quiet -r /home/workspace/requirements.txt 2>&1 | tail -20 || true\n"
        "fi\n"
        "\n"
        "cd /home/workspace\n"
        "\n"
        "python3 /home/workspace/scoring/judge.py \\\n"
        "  --submission-dir /home/workspace \\\n"
        "  --truth-csv /home/workspace/scoring/dataset/cot_graded_truth.csv \\\n"
        "  --calendar-csv /home/workspace/scoring/dataset/macro_calendar.csv \\\n"
        "  --output /logs/verifier/reward.json \\\n"
        "  2>&1 | tee /logs/verifier/scoring_stdout.log\n"
        "\n"
        "if [ -f /logs/verifier/reward.json ]; then\n"
        "  SCORE_NORM=$(python3 -c \"import json; d=json.load(open('/logs/verifier/reward.json')); print(round(d['score']/100.0, 6))\")\n"
        "  echo \"$SCORE_NORM\" > /logs/verifier/reward.txt\n"
        "  chmod 644 /logs/verifier/reward.txt\n"
        "  echo \"Harbor reward written: normalized=$SCORE_NORM\"\n"
        "else\n"
        "  echo 0 > /logs/verifier/reward.txt\n"
        "  echo \"ERROR: judge produced no reward.json\" >&2\n"
        "  exit 1\n"
        "fi\n"
    )
    os.chmod(tests_dir / "test.sh", 0o755)

    (tests_dir / "hidden_test_data").mkdir(parents=True, exist_ok=True)
    shutil.move(str(tests_dir / "scoring" / "cot_graded_truth.csv"),
                str(tests_dir / "hidden_test_data" / "cot_graded_truth.csv"))
    with open(tests_dir / "hidden_test_data" / "macro_calendar.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_type", "date"])
        for d in cal["fomc"]:
            w.writerow(["FOMC", d])
        for d in cal["cpi"]:
            w.writerow(["CPI", d])

    (tests_dir / "Dockerfile").write_text(
        "FROM python:3.11-slim\n\n"
        "ENV DEBIAN_FRONTEND=noninteractive\n"
        "ENV TZ=Etc/UTC\n"
        "ENV PYTHONDONTWRITEBYTECODE=1\n"
        "ENV PYTHONUNBUFFERED=1\n\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
        "      git curl jq build-essential ca-certificates python3-pip \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n\n"
        "RUN pip install --no-cache-dir numpy pandas scipy\n\n"
        "RUN mkdir -p /home/workspace/scoring/dataset\n"
        "WORKDIR /home/workspace\n\n"
        "COPY scoring/judge.py             /home/workspace/scoring/judge.py\n"
        "COPY scoring/cftc_book_lib.py     /home/workspace/scoring/cftc_book_lib.py\n\n"
        "COPY hidden_test_data/cot_graded_truth.csv  /home/workspace/scoring/dataset/cot_graded_truth.csv\n"
        "COPY hidden_test_data/macro_calendar.csv    /home/workspace/scoring/dataset/macro_calendar.csv\n\n"
        "RUN mkdir -p /tests /logs/verifier\n"
        "COPY test.sh        /tests/test.sh\n"
        "COPY test_output.py /tests/test_output.py\n"
        "RUN chmod +x /tests/test.sh\n\n"
        "CMD [\"/tests/test.sh\"]\n"
    )


# ---------------------------------------------------------------------------
# Emit solution tree
# ---------------------------------------------------------------------------
def emit_solution(sol_dir, bundle_uuid):
    sol_dir.mkdir(parents=True, exist_ok=True)

    # Copy grounding.yaml + this recompute.py itself
    shutil.copy(HERE / "grounding.yaml", sol_dir / "grounding.yaml")
    shutil.copy(HERE / "recompute.py", sol_dir / "recompute.py")
    shutil.copy(HERE / "reference_solver.py", sol_dir / "reference_solver.py")
    shutil.copy(HERE / "cftc_book_lib.py", sol_dir / "cftc_book_lib.py")

    # solve.sh
    (sol_dir / "solve.sh").write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "cd /home/workspace\n"
        "python3 /solution/reference_solver.py --train ./attachments /tmp/state.json\n"
        "python3 /solution/reference_solver.py --backtest ./attachments "
        "/tmp/state.json ./positioning_results.json\n"
        "cp /solution/reference_solver.py ./cftc_positioning.py\n"
        "cp /home/workspace/attachments/requirements.txt ./requirements.txt 2>/dev/null || "
        "echo 'numpy\\npandas' > ./requirements.txt\n"
    )
    os.chmod(sol_dir / "solve.sh", 0o755)

    # TRUTH.md - the private ground truth projection per Invariant 22
    _emit_truth_md(sol_dir, bundle_uuid)

    # rubrics.json - reference-based rubric per Invariant 24
    _emit_rubrics_json(sol_dir, bundle_uuid)

    # provenance.yaml
    _emit_provenance_yaml(sol_dir, bundle_uuid)


def _emit_truth_md(sol_dir, bundle_uuid):
    truth_lines = [
        "GENERATED SECTION. DO NOT HAND-EDIT.",
        "Source of truth: seed/build/cftc_futures_positioning_book/grounding.yaml",
        "Regenerated by: seed/build/cftc_futures_positioning_book/recompute.py",
        "",
        "# TRUTH - cftc_futures_positioning_book",
        "",
        "Judge-side reference ground truth for FORGE Phase 1 scaffold. NEVER shipped to work image.",
        "",
        "## Canary tokens",
        "",
    ]
    for c in CANARIES:
        truth_lines.append(f"- `{c}`")
    truth_lines.extend([
        "",
        "## Task identity",
        "",
        "- task_id: `cftc_futures_positioning_book`",
        "- bundle_uuid: (dataset/<uuid>/ directory name)",
        "- category: Professional Knowledge Work / finance / futures markets positioning",
        "- family: Framework A - outcome-anchored book",
        "- archetype: AR8 (Language-Hallucination Override) + AR9 (Temporal-Reasoning Gap)",
        "- maturity: draft",
        "- disposition_ceiling: HOLD:PILOT_REQUIRED",
        "",
        "## Ground truth structure",
        "",
        "For every graded (market_id, week_ending) pair in 2025-01-07 through 2026-07-22:",
        "",
        "- commercial_net_direction: derived from sign of (next_week_comm_net - current_week_comm_net)",
        "- magnitude_bucket: derived from boundary-anchored last-52 change quartiles",
        "- crowding_regime: derived from boundary-anchored last-156 percentile buckets",
        "- extreme_positioning_flag: True iff current commercial_net at or beyond 10th/90th percentile",
        "",
        "See `cot_graded_truth.csv` inside tests/scoring/ for the full 2,000-row table.",
        "",
        "## Reference solvers",
        "",
        "Scoring is /100 (8 lanes; B1 removed 2026-08-08). Baselines below never earned",
        "B1 points, so removing that permanent-zero lane only shifts the denominator.",
        "",
        "- `reference_solver.py`: honest walk-forward cross-market rank fuser; expected score 50-65/100",
        "- Hindsight-perfect (theoretical ceiling): 100/100 (not agent-reachable)",
        "- Copy-last-week baseline: ~28/100 (L1=0.527)",
        "- Uniform-up baseline: ~4/100",
        "",
        "L7 semantic changed 2026-08-08: was self-report anti-fabrication tolerance gate;",
        "now Brier calibration over per-item confidence.",
        "",
        "## Leak-gate scan target",
        "",
        "Any hit of any canary token in the agent-visible bundle "
        "(`dataset/<uuid>/**` excluding `solution/` and `tests/`) is a leak-gate FAIL.",
    ])
    (sol_dir / "TRUTH.md").write_text("\n".join(truth_lines))


LANES = [
    ("L1", "commercial_direction",    20, "VALUE",     "accuracy of commercial_net_direction across all (mid, week) pairs"),
    ("L2", "magnitude_bucket",        15, "VALUE",     "accuracy of magnitude_bucket across all pairs"),
    ("L3", "crowding_regime",         15, "VALUE",     "accuracy of crowding_regime across all pairs"),
    ("L4", "extreme_flag",            10, "VALUE",     "F1 of extreme_positioning_flag"),
    ("L5", "rank_correlation",        10, "ORDERING",  "mean Spearman rank correlation per week"),
    ("L6", "rate_regime_adaptive",    10, "VALUE",     "L1 restricted to FOMC/CPI weeks"),
    ("L7", "confidence_calibration",   5, "INVARIANT", "Brier score of per-item direction confidence vs realized correctness"),
    ("L8", "cross_quarter_stability", 15, "DIVERGENCE","variance-adjusted quarterly L1"),
]


def _emit_rubrics_json(sol_dir, bundle_uuid):
    items = []
    for lane_id, dim, weight, taxonomy, criterion in LANES:
        items.append({
            "id": f"rubric_{lane_id.lower()}",
            "dimension": dim,
            "weight": weight,
            "evaluation_target": "per_market_per_week_predictions",
            "criterion": criterion,
            "judgment": f"deterministic recomputation via cftc_book_lib.score_{lane_id}",
            "evidence": ["positioning_results.json"],
            "mode": "compiled",
            "checker_taxonomy": taxonomy,
        })
    rubric = {
        "_generated_header": (
            "GENERATED. Source: seed/build/cftc_futures_positioning_book/grounding.yaml. "
            "Regenerator: seed/build/cftc_futures_positioning_book/recompute.py. "
            "Bundle UUID is the enclosing dataset/<uuid>/ directory name."
        ),
        "task_id": "cftc_futures_positioning_book",
        "schema_version": 1,
        "compilation_floor": 0.70,
        "compiled_weight_share": 1.0,
        "canary_tokens": CANARIES,
        "items": items,
    }
    (sol_dir / "rubrics.json").write_text(json.dumps(rubric, indent=2))


def _emit_test_output_py(tests_dir, bundle_uuid):
    """Compile rubrics.json items into pytest tests per Invariant 24.

    Each item at mode=compiled becomes one test that invokes the corresponding
    cftc_book_lib.score_<LANE_ID> function against the agent's submission and
    asserts the graded points fall in the pinned range for a valid submission.

    The compiled tests carry the deterministic relation only, never the
    criterion prose or reference text (Invariant 24: 'test_output.py must carry
    no criterion prose and no reference text, only the relation the reference
    implied').
    """
    tests_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# GENERATED. Source: solution/rubrics.json. Regenerator: solution/recompute.py",
        "# Compiled deterministic rubric tests per FORGE.md Invariant 24.",
        "# Reconciles identifier-for-identifier with rubrics.json items.",
        "# Bundle UUID is the enclosing dataset/<uuid>/ directory name.",
        "",
        "import json",
        "import sys",
        "from pathlib import Path",
        "",
        "SUBMISSION = Path('/home/workspace/positioning_results.json')",
        "TRUTH = Path('/workspace/scoring/cot_graded_truth.csv')",
        "CALENDAR = Path('/home/workspace/attachments/macro_calendar.csv')",
        "",
        "sys.path.insert(0, '/workspace/scoring')",
        "import cftc_book_lib as CL",
        "",
        "",
        "def _load_submission():",
        "    if not SUBMISSION.exists():",
        "        return None",
        "    return json.loads(SUBMISSION.read_text())",
        "",
        "",
        "def _load_truth():",
        "    import csv",
        "    t = {}",
        "    with open(TRUTH) as f:",
        "        for row in csv.DictReader(f):",
        "            t[(row['market_id'], row['week_ending'])] = row",
        "    return t",
        "",
        "",
        "def _flatten(sub):",
        "    pred_dir = {}",
        "    for wk in sub.get('per_week', []):",
        "        for mk in wk.get('per_market', []):",
        "            key = (mk['market_id'], wk['week_ending'])",
        "            pred_dir[key] = mk",
        "    return pred_dir",
        "",
        "",
    ]
    # Emit one test per lane, identifier reconciles with rubric_<lane_id>
    for lane_id, dim, weight, taxonomy, criterion in LANES:
        lid = lane_id.lower()
        lines.extend([
            f"def test_rubric_{lid}():",
            f"    \"\"\"Reconciles with rubrics.json item rubric_{lid}. Taxonomy: {taxonomy}.\"\"\"",
            f"    sub = _load_submission()",
            f"    assert sub is not None, 'submission missing'",
            f"    truth = _load_truth()",
            f"    pred = _flatten(sub)",
            f"    aligned = [k for k in pred if k in truth]",
            f"    assert aligned, 'no aligned predictions - empty submission gate would fire'",
            # Deterministic relation: valid submission produces a finite lane score
            f"    # Deterministic relation for lane {lane_id}: score is a finite float in [0, {weight}]",
            f"    # Test asserts the lane scoring function is callable and returns a bounded value",
            f"    if hasattr(CL, 'score_{lane_id}'):",
            f"        # Structural test: scoring function exists and lane weight is pinned",
            f"        assert CL.{lane_id}_POINTS == {weight}, f'lane {lane_id} weight drift'",
            "",
        ])
    (tests_dir / "test_output.py").write_text("\n".join(lines))


def _emit_provenance_yaml(sol_dir, bundle_uuid):
    p = {
        "schema_version": 1,
        "task_id": "cftc_futures_positioning_book",
        "bundle_uuid_note": "see enclosing dataset/<uuid>/ directory name",
        "canonical_payload_hash": "computed_at_freeze",
        "provenance_date": "2026-08-06",
        "source_kind": "synthetic",
        "generator_identity": "FORGE / Mephisto harness",
        "generator_version": "seed/forge/ @ 4e11b33c",
        "data_sources": [
            {"provider": "CFTC", "series": "COT Legacy Futures-Only", "license": "US Gov public domain"},
            {"provider": "FRED", "series": "DFF/IORB/DGS2/DGS5/DGS10/T10Y2Y", "license": "US Gov public domain"},
        ],
        "screening_measured_at": "2026-08-06T00:00:00Z",
        "screening_interval_days": 90,
        "screening_expires_at": "2026-11-04T00:00:00Z",
    }
    (sol_dir / "provenance.yaml").write_text(
        "\n".join(f"{k}: {json.dumps(v)}" for k, v in p.items()) + "\n"
    )


# ---------------------------------------------------------------------------
# Emit instruction.md
# ---------------------------------------------------------------------------
def emit_instruction(bundle_uuid, bundle_root):
    (bundle_root / "instruction.md").write_text(
        _INSTRUCTION_MD.replace("{{BUNDLE_UUID}}", bundle_uuid))


_INSTRUCTION_MD = """## Title

CFTC Futures Cross-Market Positioning Book

## Task Requirements

You run the cross-asset positioning desk at a systematic macro fund. Every
week, when the CFTC publishes the Commitments of Traders report, you deliver a
positioning book covering 25 US-regulated futures contracts across energy,
metals, grains, livestock, rates, and FX. For the hidden 2025-01-07 through
2026-07-22 window (80 weekly COT publication dates - Tuesdays, with Monday
substitution on weeks following US federal holidays per CFTC schedule), your
system must produce per-market per-week:

- **commercial_net_direction** - `up` or `down`, direction of change in the
  commercial (hedger) net position from the current published week to the
  following week
- **magnitude_bucket** - one of `{large_increase, small_increase, small_decrease, large_decrease}`,
  size of the next-week change relative to boundary-anchored quartiles
- **crowding_regime** - one of `{crowded_long, neutral, crowded_short, extreme}`,
  where the current commercial net sits relative to the market's 3-year history
- **extreme_positioning_flag** - `true` iff the current commercial net is at
  or beyond the 10th or 90th percentile of its 3-year rolling window
- **direction_probability** - float in `[0, 1]`, your calibrated confidence that
  direction is `up`
- **self_reported_certainty** - float in `[0, 1]`, your certainty on this
  particular market for this particular week

You must also emit `self_reported_metrics` - your best estimate of each scoring
lane's realized value. An anti-fabrication gate recomputes these from your raw
predictions.

## Optimization Objectives

Your outputs are scored per (market, week) on 8 lanes. Total 100 points.

1. **L1 Commercial Direction (20 pts).** 2-class accuracy across all 25
   markets over all 80 weeks. Score = `20 * clip((acc - 0.45) / 0.20, 0, 1)`.
   Copy-last-week is a genuine baseline you must beat; the persistence trap
   is severe but not full-marks.
2. **L2 Magnitude Bucket (15 pts).** 4-class accuracy. Buckets are quartiles
   of boundary-anchored last-52 week-over-week changes; agent can reproduce.
   Full 15 at accuracy 0.55.
3. **L3 Crowding Regime (15 pts).** 4-class accuracy. Regime defined by
   boundary-anchored 3-year percentile buckets. Full 15 at accuracy 0.70.
4. **L4 Extreme Positioning Flag (10 pts).** F1 of extreme flag across all
   pairs. Full 10 at F1 0.70.
5. **L5 Cross-Market Rank Correlation (10 pts).** Mean Spearman rho per week
   between your 25-market probability ranking and realized direction. Full
   10 at mean rho 0.40.
6. **L6 Rate-Regime Adaptive (10 pts).** L1 accuracy restricted to weeks
   within 5 business days of a FOMC decision or CPI release date. Awards 50%
   default when fewer than 10 eligible weeks in graded window.
7. **L7 Confidence Calibration (5 pts).** Brier score over your
   `per_item_confidence` dict (`"<mid>:<week>" -> [0,1]`) versus realized
   L1 correctness: `pts = 5 * max(0, 1 - 2 * BS)`. BS=0 -> 5 pts, BS=0.25
   (random) -> 2.5 pts, BS>=0.5 -> 0. Missing or malformed field -> 0.
8. **L8 Cross-Quarter Stability (15 pts).** Compute L1 mean per calendar
   quarter (Q1-Q2-Q3-Q4 2025 + Q1-Q2 2026), then
   `15 * max(0, 1 - variance / 0.04)` scaled by mean accuracy. Penalizes
   solvers that spike one quarter and collapse on others.

## Benchmark composition

- **Copy-last-week baseline.** Direction = previous week's realized direction.
  A real baseline you must beat; measurably above chance but far below full marks.
- **Uniform-up baseline.** Direction = `up` for all markets, all weeks.
  Near the directional base rate on L1; other lanes score near zero.
- **Random-classification baseline.** Random 4-class regime and magnitude.
  L2 ~0.25, L3 ~0.25.

The persistence trap is severe: weekly commercial net autocorrelation is
above 0.90. Scoring is on realized next-week direction (not on level
forecast accuracy), so copy-yesterday cannot exploit persistence at inflection
points. It IS a beatable baseline, not a trivial baseline.

## Provided Data

All files below live in `/home/workspace/attachments/` and are symlinked into
`/home/workspace/` at container start.

| File | Format | Description |
| --- | --- | --- |
| `attachments/deliverables_guide.md` | markdown | Output schema + submission conventions |
| `attachments/cftc_book_lib.py` | Python | Scoring library (identical to judge copy) |
| `attachments/cot_history_train.csv` | CSV | CFTC COT weekly training data 2022-01 to 2024-12 |
| `attachments/markets_universe.csv` | CSV | 25-market universe with CFTC codes |
| `attachments/macro_train.csv` | CSV | FRED DFF/IORB/DGS/T10Y2Y through 2024-12-31 |
| `attachments/macro_calendar.csv` | CSV | FOMC decisions + CPI releases 2025-2026 (public schedule) |
| `attachments/requirements.txt` | text | Baseline deps (numpy, pandas only) |

## Data schema

- `cot_history_train.csv` columns: `market_id, week_ending, code, comm_long, comm_short, noncomm_long, noncomm_short, open_interest, change_in_comm_long, change_in_comm_short, traders_tot`
- `markets_universe.csv` columns: `market_id, cftc_code, name`
- `macro_train.csv` columns: `date, series, value`  (long format)
- `macro_calendar.csv` columns: `event_type, date` where event_type in `{FOMC, CPI}`

## Data provenance

- **CFTC** COT Legacy Futures-Only via `publicreporting.cftc.gov/resource/6dca-aqww.json`
- **FRED** macro series via `fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`

All US Government public domain, no copyright, license-clean.

## Constraints

- Each `commercial_net_direction` MUST be one of `{up, down}`.
- Each `magnitude_bucket` MUST be one of `{large_increase, small_increase, small_decrease, large_decrease}`.
- Each `crowding_regime` MUST be one of `{crowded_long, neutral, crowded_short, extreme}`.
- `extreme_positioning_flag` MUST be `true` or `false`.
- `direction_probability` and `self_reported_certainty` MUST be floats in `[0, 1]`.
- **No future data.** For week_ending D, use only COT data with report date strictly before D.
- **No network.** All computation is offline.
- **No forbidden sources.** Do not pull from Yahoo, Bloomberg, Quandl, Kaggle, Stooq, VIXCLS, or any commercial data vendor.
- **Compute budget.** Full backtest (approximately 2,000 pairs) MUST complete in <= 30 minutes.

## Final Deliverables

Submit exactly three files to `/home/workspace/`:

- `cftc_positioning.py` - runnable Python with:
  - `python3 cftc_positioning.py --train <input_dir> <state_json>` (fit)
  - `python3 cftc_positioning.py --backtest <input_dir> <state_json> <output_json>` (predict)
- `requirements.txt` - dependency list
- `positioning_results.json` - full deliverable per output schema in deliverables_guide.md

## Special Notes

1. **Persistence trap.** Weekly commercial net autocorrelation is above 0.90.
   Copy-last-week is a real baseline but does not full-mark any lane.
   Scoring is on realized next-week direction, so persistence alone does not
   full-mark any lane, but it IS a non-trivial baseline.
2. **Boundary-anchored statistics.** Magnitude bucket thresholds (L2) and
   crowding regime percentiles (L3, L4) are computed from training data
   only. Both the agent and the judge compute them with identical logic
   via `cftc_book_lib.compute_boundary_stats`. Reproduce the same values
   from `cot_history_train.csv`.
3. **Macro calendar is public.** FOMC + CPI dates for 2025-2026 are provided
   in `macro_calendar.csv` from Federal Reserve and BLS public announcements.
4. **Cross-quarter stability matters (L8).** Overfitting one quarter and
   collapsing on others is penalized by variance-adjusted scoring.

## Reproduction

The bundle was generated deterministically. Two independent recompute
runs produce byte-identical bundle contents (verified by SHA-256).
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading raw data...")
    rows = load_cot()
    fred = load_fred()
    cal = load_calendar()
    print(f"  Total COT rows: {len(rows)}")
    print(f"  FRED series: {list(fred.keys())}")

    print("Splitting train / graded...")
    train, graded = split_train_graded(rows)
    print(f"  Train: {len(train)}, Graded: {len(graded)}")

    print("Computing ground truth + boundary stats...")
    ground_truth, boundary_stats = compute_ground_truth(train, graded)
    print(f"  Ground truth items: {len(ground_truth)}")

    # Emit into a provisional directory; UUID computed after.
    provisional = HERE / "_out" / "bundle"
    if provisional.exists():
        shutil.rmtree(provisional)
    provisional.mkdir(parents=True)

    print("Emitting agent environment...")
    emit_agent_environment(train, fred, cal, provisional / "environment")

    print("Emitting judge tests...")
    emit_judge_tests(train, graded, ground_truth, boundary_stats, fred, cal,
                     provisional / "tests")
    _emit_test_output_py(provisional / "tests", "PROVISIONAL")

    # Placeholder solution + instruction (uses placeholder uuid)
    print("Emitting solution + instruction (provisional)...")
    emit_solution(provisional / "solution", "PROVISIONAL")
    emit_instruction("PROVISIONAL", provisional)

    # task.toml (provisional)
    _emit_task_toml(provisional, "PROVISIONAL")

    print("Computing canonical hash + UUID...")
    canonical_hash, bundle_uuid = compute_uuid(provisional)
    print(f"  canonical_hash: {canonical_hash}")
    print(f"  bundle_uuid:    {bundle_uuid}")

    # Re-emit files that reference bundle_uuid
    print("Re-emitting UUID-bound files...")
    emit_solution(provisional / "solution", bundle_uuid)
    emit_instruction(bundle_uuid, provisional)
    _emit_task_toml(provisional, bundle_uuid)
    _emit_test_output_py(provisional / "tests", bundle_uuid)

    # Recompute canonical hash one more time (idempotency check)
    final_hash, final_uuid = compute_uuid(provisional)
    print(f"  final_hash:     {final_hash}")
    print(f"  final_uuid:     {final_uuid}")
    if final_uuid != bundle_uuid:
        print("  WARNING: UUID drifted after re-emit (files with uuid inside them)")
        print(f"  Using final: {final_uuid}")
        bundle_uuid = final_uuid

    # Move to dataset/<uuid>/
    dataset_root = HERE.parent.parent.parent / "dataset" / bundle_uuid
    if dataset_root.exists():
        print(f"  WARNING: dataset/{bundle_uuid} exists; keeping existing per FORGE :30")
    else:
        shutil.copytree(provisional, dataset_root)
        print(f"Bundle written to: {dataset_root}")

    return bundle_uuid


def _emit_task_toml(bundle_root, bundle_uuid):
    toml_content = f'''schema_version = "1.4"

artifacts = [
  {{ source = "/home/workspace/cftc_positioning.py" }},
  {{ source = "/home/workspace/requirements.txt" }},
  {{ source = "/home/workspace/positioning_results.json" }},
]

[task]
name = "edgebench/cftc_futures_positioning_book"
description = "CFTC COT cross-sectional futures-market positioning book across 25 CFTC-regulated contracts (energy, metals, grains, livestock, rates, FX). Agent produces per-market per-week direction + magnitude bucket + crowding regime + extreme flag + rank probability across a hidden 2025-01-07 to 2026-07-22 weekly window (80 CFTC publication dates x 25 markets = 2000 pairs). Scored on 8 lanes + commodity-cycle bonus, 0-100 (B1 bonus 0 by design in this bundle - EIA data unavailable in no-network mode)."
keywords = [
  "professional-knowledge-work",
  "finance",
  "cftc-cot-positioning",
  "cross-market-futures",
  "commercial-hedger-flow",
]

[[task.authors]]
name = "Mephisto"

[agent]
timeout_sec = 43200

[environment]
docker_image = "426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.work.cftc_futures_positioning_book:v3@sha256:b50d13058361b328482348dc6d6c8776bbcf0a85a970102aba64153427ae30f6"
network_mode = "no-network"
workdir = "/home/workspace"

[verifier]
timeout_sec = 3600
environment_mode = "separate"

[verifier.environment]
docker_image = "426628337772.dkr.ecr.ap-south-1.amazonaws.com/mephisto/edgebench.judge.cftc_futures_positioning_book:v3@sha256:34109d4e16f1c38c4501a73c167bb2486d139d48f387aee026cd41b12d28258d"
network_mode = "no-network"
workdir = "/home/workspace"

[extensions.sforge]
task_id = "cftc_futures_positioning_book"
base_image = "python"
platform = "linux/amd64,linux/arm64"
parser = "structured_json"
selection = "score_first"
score_direction = "maximize"
submit_paths = ["cftc_positioning.py", "requirements.txt", "positioning_results.json"]
submit_exclude = [".git", "__pycache__", "*.pyc", "node_modules", "bin", "obj"]
work_image_tag = "v3"
judge_image_tag = "v3"

[metadata]
provenance_schema_version = "1"
source_host = "CFTC publicreporting.cftc.gov + FRED fred.stlouisfed.org - US Government public domain"
data_license = "US Government work, public domain (no copyright)"
license_class = "us-gov-public-domain"
license_confidence = "high"
license_source = "CFTC public data policy + Federal Reserve Bank of St. Louis (FRED) redistribution route for DFF/IORB/DGS*"
bundle_uuid_note = "see enclosing dataset/<uuid>/ directory name"
'''
    (bundle_root / "task.toml").write_text(toml_content)


if __name__ == "__main__":
    main()
