import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BANNER = "GENERATED SECTION. DO NOT HAND-EDIT."


def load_grounding():
    with open(HERE / "grounding.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def render_truth_md(g):
    lanes = g["scoring"]["lanes"]
    kills = g["scoring"]["kill_bands"]
    traj = g["golden_trajectory"]
    controls = g["controls"]
    lines = []
    lines.append(BANNER)
    lines.append("")
    lines.append("Source of truth: solution/grounding.yaml via solution/recompute.py.")
    lines.append("")
    lines.append(f"# TRUTH - {g['task_id']}")
    lines.append("")
    lines.append("## Scoring lanes")
    lines.append("")
    lines.append("| Lane | Max | Rule |")
    lines.append("| --- | --- | --- |")
    for lane in lanes:
        rule = " ".join(str(lane["rule"]).split())
        lines.append(f"| {lane['id']} | {lane['max']} | {rule} |")
    lines.append("")
    lines.append("## Kill bands")
    lines.append("")
    lines.append("| Id | Condition | Effect |")
    lines.append("| --- | --- | --- |")
    for kb in kills:
        lines.append(
            f"| {kb['id']} | {' '.join(str(kb['condition']).split())} |"
            f" {' '.join(str(kb['effect']).split())} |"
        )
    lines.append("")
    lines.append("## Environment gate")
    lines.append("")
    lines.append(" ".join(str(g["scoring"]["environment_gate"]["rule"]).split()))
    lines.append("")
    lines.append("## Golden trajectory")
    lines.append("")
    for step in traj:
        lines.append(f"- **{step['id']}**: {' '.join(str(step['action']).split())}")
        lines.append(f"  - yields: {' '.join(str(step['yields']).split())}")
    lines.append("")
    lines.append("## Rejected routes")
    lines.append("")
    for route in g["rejected_routes"]:
        lines.append(
            f"- {route['route']} -> named control `{route['control']}`"
        )
    lines.append("")
    lines.append("## Controls")
    lines.append("")
    for ctl in controls["negative"]:
        lines.append(
            f"- negative `{ctl['id']}`: {' '.join(str(ctl['behavior']).split())};"
            f" expected {' '.join(str(ctl['expected']).split())}"
        )
    for ctl in controls["positive"]:
        lines.append(
            f"- positive `{ctl['id']}`: {' '.join(str(ctl['behavior']).split())};"
            f" expected {' '.join(str(ctl['expected']).split())}"
        )
    lines.append("")
    lines.append("## Oracle")
    lines.append("")
    lines.append(" ".join(str(g["oracle"]["verified"]).split()))
    lines.append("")
    lines.append(
        f"Self-score target band: {g['oracle']['self_score_target_band']}."
    )
    lines.append("")
    return "\n".join(lines)


def render_rubrics(g):
    items = []
    for lane in g["scoring"]["lanes"]:
        items.append(
            {
                "id": lane["id"],
                "dimension": "outcome",
                "weight": lane["max"] / 100.0,
                "evaluation_target": lane["id"],
                "criterion": " ".join(str(lane["rule"]).split()),
                "judgment": "deterministic lane score emitted by tests/verify.py",
                "evidence": "STRUCTURED_RESULT_JSON lanes block",
                "mode": "compiled",
            }
        )
    for kb in g["scoring"]["kill_bands"]:
        items.append(
            {
                "id": kb["id"],
                "dimension": "integrity",
                "weight": 0.0,
                "evaluation_target": kb["id"],
                "criterion": " ".join(str(kb["condition"]).split()),
                "judgment": " ".join(str(kb["effect"]).split()),
                "evidence": "STRUCTURED_RESULT_JSON kill_bands block",
                "mode": "compiled",
            }
        )
    return {
        "banner": BANNER,
        "task_id": g["task_id"],
        "compilation_floor": 1.0,
        "compiled_weight": sum(i["weight"] for i in items),
        "items": items,
    }


def main():
    g = load_grounding()
    truth = render_truth_md(g)
    (HERE / "TRUTH.md").write_text(truth, encoding="utf-8")
    rubrics = render_rubrics(g)
    (HERE / "rubrics.json").write_text(
        json.dumps(rubrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("wrote TRUTH.md and rubrics.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
