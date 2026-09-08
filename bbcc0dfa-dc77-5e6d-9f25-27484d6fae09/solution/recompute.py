#!/usr/bin/env python3
"""Regenerate TRUTH.md and rubrics.json from solution/grounding.yaml.

This is the only writer of those two files. It consumes no model, network,
clock, or randomness. Criterion prose comes verbatim from grounding.yaml.
"""
import json
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BANNER = "GENERATED SECTION. DO NOT HAND-EDIT."


def load_grounding():
    return yaml.safe_load((HERE / "grounding.yaml").read_text())


def render_truth_md(g):
    lines = []
    lines.append(f"<!-- {BANNER} -->")
    lines.append("<!-- Source of truth: solution/grounding.yaml via solution/recompute.py -->")
    lines.append(f"# TRUTH - {g['task_id']}")
    lines.append("")
    lines.append("## Scoring lanes")
    lines.append("")
    lines.append("| Lane | Max | Rule |")
    lines.append("| --- | --- | --- |")
    for lane in g["scoring"]["lanes"]:
        rule = " ".join(str(lane["rule"]).split())
        lines.append(f"| {lane['id']} | {lane['max']} | {rule} |")
    lines.append("")
    lines.append("## Kill bands")
    lines.append("")
    lines.append("| Id | Condition | Effect |")
    lines.append("| --- | --- | --- |")
    for band in g["scoring"]["kill_bands"]:
        cond = " ".join(str(band["condition"]).split())
        eff = " ".join(str(band["effect"]).split())
        lines.append(f"| {band['id']} | {cond} | {eff} |")
    lines.append("")
    lines.append("## Environment gate")
    lines.append("")
    lines.append(" ".join(str(g["scoring"]["environment_gate"]["rule"]).split()))
    lines.append("")
    lines.append("## Golden trajectory")
    lines.append("")
    for step in g["golden_trajectory"]:
        action = " ".join(str(step["action"]).split())
        yields = " ".join(str(step["yields"]).split())
        lines.append(f"- {step['id']}: {action} Yields: {yields}")
    lines.append("")
    lines.append("## Rejected routes")
    lines.append("")
    for rr in g["rejected_routes"]:
        route = " ".join(str(rr["route"]).split())
        lines.append(f"- {route} Control: {rr['control']}")
    lines.append("")
    lines.append("## Controls")
    lines.append("")
    for ctl in g["controls"]["negative"]:
        behavior = " ".join(str(ctl["behavior"]).split())
        expected = " ".join(str(ctl["expected"]).split())
        lines.append(f"- negative {ctl['id']}: {behavior} Expected: {expected}")
    for ctl in g["controls"]["positive"]:
        behavior = " ".join(str(ctl["behavior"]).split())
        expected = " ".join(str(ctl["expected"]).split())
        lines.append(f"- positive {ctl['id']}: {behavior} Expected: {expected}")
    lines.append("")
    lines.append("## Oracle")
    lines.append("")
    verified = " ".join(str(g["oracle"]["verified"]).split())
    band = g["oracle"]["self_score_target_band"]
    lines.append(f"{verified} Self-score target band: [{band[0]}, {band[1]}].")
    lines.append("")
    lines.append(f"Canary: {g['canary_marker']}")
    lines.append("")
    return "\n".join(lines)


def render_rubrics(g):
    items = []
    total = sum(lane["max"] for lane in g["scoring"]["lanes"])
    compiled_weight = 0.0
    for lane in g["scoring"]["lanes"]:
        weight = lane["max"] / total
        compiled_weight += weight
        items.append(
            {
                "id": lane["id"],
                "dimension": "outcome",
                "weight": round(weight, 6),
                "evaluation_target": lane["id"],
                "criterion": " ".join(str(lane["rule"]).split()),
                "judgment": "deterministic lane score emitted by tests/verify.py",
                "evidence": "STRUCTURED_RESULT_JSON lanes block",
                "mode": "compiled",
            }
        )
    for band in g["scoring"]["kill_bands"]:
        items.append(
            {
                "id": band["id"],
                "dimension": "integrity",
                "weight": 0.0,
                "evaluation_target": band["id"],
                "criterion": " ".join(str(band["condition"]).split())
                + " Effect: "
                + " ".join(str(band["effect"]).split()),
                "judgment": "deterministic kill band emitted by tests/verify.py",
                "evidence": "STRUCTURED_RESULT_JSON kill_bands block",
                "mode": "compiled",
            }
        )
    return {
        "banner": BANNER,
        "task_id": g["task_id"],
        "compilation_floor": 1.0,
        "compiled_weight": round(compiled_weight, 6),
        "canary": g["canary_marker"],
        "items": items,
    }


def main():
    g = load_grounding()
    (HERE / "TRUTH.md").write_text(render_truth_md(g))
    (HERE / "rubrics.json").write_text(
        json.dumps(render_rubrics(g), indent=2, sort_keys=True) + "\n"
    )
    print("regenerated TRUTH.md and rubrics.json")


if __name__ == "__main__":
    main()
