from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent


def load_yaml_lite(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text)
    except Exception:
        parsed = _naive_yaml_parse(text)
        parsed["canary_tokens"] = _extract_top_level_list(text, "canary_tokens")
        parsed["scoring_weights_check"] = _extract_scalar_map(text, "scoring_weights_check")
        return parsed


def _extract_top_level_list(text: str, key: str) -> list:
    import re
    m = re.search(rf"^{key}:\s*\n((?:[ \t]+-.+\n)+)", text, flags=re.MULTILINE)
    if not m:
        return []
    items = []
    for ln in m.group(1).splitlines():
        s = ln.strip()
        if s.startswith("- "):
            v = s[2:].strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            items.append(v)
    return items


def _extract_scalar_map(text: str, key: str) -> dict:
    import re
    m = re.search(rf"^{key}:\s*\n((?:[ \t]+\w+:\s*\S+\s*\n)+)", text, flags=re.MULTILINE)
    if not m:
        return {}
    result: dict = {}
    for ln in m.group(1).splitlines():
        s = ln.strip()
        if ":" in s:
            k, _, v = s.partition(":")
            v = v.strip()
            try:
                result[k.strip()] = int(v)
            except ValueError:
                try:
                    result[k.strip()] = float(v)
                except ValueError:
                    result[k.strip()] = v
    return result


def _naive_yaml_parse(text: str) -> dict:
    obj: dict = {}
    stack: list[tuple[int, object]] = [(-1, obj)]
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    pending_list_for_key: tuple[int, str, dict] | None = None
    for ln in lines:
        indent = len(ln) - len(ln.lstrip())
        content = ln.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1] if stack else obj
        if content.startswith("- "):
            v = content[2:].strip()
            if pending_list_for_key and indent > pending_list_for_key[0]:
                key = pending_list_for_key[1]
                target_dict = pending_list_for_key[2]
                if not isinstance(target_dict.get(key), list):
                    target_dict[key] = []
                lst = target_dict[key]
                if ":" in v:
                    new_item: dict = {}
                    kk, _, vv = v.partition(":")
                    kk = kk.strip(); vv = vv.strip()
                    if vv:
                        new_item[kk] = _coerce_scalar(vv)
                    else:
                        new_item[kk] = {}
                    lst.append(new_item)
                    stack.append((indent, new_item))
                else:
                    lst.append(_coerce_scalar(v))
            elif isinstance(parent, list):
                parent.append(_coerce_scalar(v))
            continue
        if ":" in content:
            k, _, v = content.partition(":")
            k = k.strip(); v = v.strip()
            if not v:
                if isinstance(parent, dict):
                    parent[k] = {}
                    pending_list_for_key = (indent, k, parent)
                    stack.append((indent, parent[k]))
            else:
                if isinstance(parent, dict):
                    parent[k] = _coerce_scalar(v)
    return obj


def _coerce_scalar(v: str):
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(p.strip()) for p in inner.split(",")]
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if v.lower() == "null":
        return None
    try:
        if "." in v:
            return float(v)
        return int(v)
    except Exception:
        return v


def recompute_rubrics(grounding: dict, out_path: Path) -> None:
    weights = grounding.get("scoring_weights_check", {})
    if not weights:
        raise ValueError("grounding.yaml has no scoring_weights_check")

    canary_tokens = grounding.get("canary_tokens", []) or []

    items = [
        ("rubric_l1", "answer_format", 3, "answer_json_meta",
         "answer.json has all required fields with valid values",
         "score_L1_format", ["answer.json"], "INVARIANT"),
        ("rubric_l2", "parameter_bounds", 2, "answer_json_meta",
         "box/pixel/symmetry within declared ranges",
         "score_L2_bounds", ["answer.json", "public_problem_config.json"], "INVARIANT"),
        ("rubric_l3", "public_sanity", 10, "reconstructed_volume_mrc",
         "FSC-0.143 resolution smooth linear good=15A bad=30A",
         "score_L3_public_sanity", ["reconstruction.mrc"], "VALUE"),
        ("rubric_l4", "handedness_gate", 5, "reconstructed_volume_mrc",
         "correct chirality via Ewald/flip NCC detectability",
         "score_L4_handedness", ["reconstruction.mrc", "answer.json"], "INVARIANT"),
        ("rubric_l5", "symmetry_correctness", 5, "answer_json_meta",
         "declared symmetry vs true; abuse (higher order) = 0",
         "score_L5_symmetry", ["answer.json"], "INVARIANT"),
        ("rubric_l6", "method_workflow", 5, "method_description_free_text",
         "method text + non-baseline .py + recon-primitive keywords in code",
         "score_L6_method_workflow", ["answer.json", "*.py"], "INVARIANT"),
        ("rubric_l7", "reconstruction_quality", 55, "reconstructed_volume_mrc",
         "coarse+precise FSC + NCC + pose scores; DOMINANT lane",
         "score_L7_reconstruction", ["reconstruction.mrc", "poses.star"], "VALUE"),
        ("rubric_l8", "resolution_physics", 15, "reconstructed_volume_mrc",
         "phase-randomization + signal-present + local consistency; gated by L7>=10",
         "score_L8_resolution_physics", ["reconstruction.mrc", "answer.json"], "DIVERGENCE"),
    ]

    rubric_items = []
    total_weight = 0
    for rid, dim, weight, target, criterion, judge, evidence, taxonomy in items:
        rubric_items.append({
            "id": rid,
            "dimension": dim,
            "weight": weight,
            "evaluation_target": target,
            "criterion": criterion,
            "judgment": f"deterministic recomputation via evaluate.py {judge}",
            "evidence": evidence,
            "mode": "compiled",
            "checker_taxonomy": taxonomy,
        })
        total_weight += weight

    if total_weight != 100:
        raise ValueError(f"rubric weights sum to {total_weight}, expected 100")

    rubrics = {
        "_generated_header": (
            "GENERATED. Source: seed/build/cryoem_single_particle_reconstruction/grounding.yaml. "
            "Regenerator: seed/build/cryoem_single_particle_reconstruction/recompute.py."
        ),
        "task_id": grounding.get("task_id", "cryoem_single_particle_reconstruction"),
        "schema_version": 1,
        "compilation_floor": 0.7,
        "compiled_weight_share": 1.0,
        "canary_tokens": canary_tokens,
        "items": rubric_items,
    }
    out_path.write_text(json.dumps(rubrics, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} ({total_weight} weight units, {len(rubric_items)} items)")


def regenerate_data() -> None:
    script = BUNDLE / "_generate_data.py"
    if not script.exists():
        print(f"WARN: {script} not found; skipping data regeneration")
        return
    print(f"Running data generator: {script}")
    subprocess.check_call([sys.executable, str(script)])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rubrics_only", action="store_true", help="skip data regeneration")
    args = parser.parse_args()

    grounding_path = HERE / "grounding.yaml"
    if not grounding_path.exists():
        raise SystemExit(f"grounding.yaml not found at {grounding_path}")
    grounding = load_yaml_lite(grounding_path)

    recompute_rubrics(grounding, HERE / "rubrics.json")

    if not args.rubrics_only:
        regenerate_data()

    print("recompute.py done.")


if __name__ == "__main__":
    main()
