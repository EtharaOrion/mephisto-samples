"""Post-emit recomputer for dataset/<uuid>/ bundle of p6zeta_zero_one_ip_solver_from_scratch_v2.

Runs against a bundle emitted by build_task.py in 3 passes:

  1. Render solution/TRUTH.md from solution/grounding.yaml (canary_tokens,
     golden_trajectory ordered_steps, near_miss_routes, lane_reconciliation,
     oracle_reconciliation). Includes a GENERATED banner and lists the 13
     TRUTH.md elements mandated by trinity/FORGE.md :94 + :212 + Invariant 22.

  2. Compute canonical_content_hash = SHA-256 over sorted-by-relative-path
     concatenation of ALL files under the bundle, EXCLUDING trajectories/ and
     __pycache__/. TRUTH.md must be rendered BEFORE hashing so its bytes are
     captured in the digest.

  3. Derive bundle_uuid = uuid.uuid5(FORGE_TASK_NAMESPACE, canonical_content_hash)
     with FORGE_TASK_NAMESPACE = c53e8f3b-526f-52c0-a04e-89e2269b237d (constant
     across every FORGE-authored task; do NOT rotate).

Requires pyyaml. Invoke via:
  PATH=/usr/bin:/bin:/usr/local/bin:/Users/apple/.local/bin:$PATH \
    uv run --project memory python3 recompute.py <bundle_dir>

Emits a JSON report to stdout with:
  bundle_dir, truth_md_rendered_at, canonical_content_hash, bundle_uuid,
  forge_task_namespace.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

FORGE_TASK_NAMESPACE = uuid.UUID("c53e8f3b-526f-52c0-a04e-89e2269b237d")
EXCLUDE_DIR_NAMES = {"trajectories", "__pycache__", ".git"}
EXCLUDE_FILE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_RELPATH_FILES = {"solution/provenance.yaml", "solution/provenance.sig"}
GENERATED_BANNER = (
    "<!-- GENERATED SECTION. DO NOT HAND-EDIT. Re-run "
    "solution/recompute.py <bundle_dir> "
    "to regenerate this file from grounding.yaml. -->"
)


def load_grounding(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fmt_list(items: List[str], bullet: str = "- ") -> str:
    return "\n".join(f"{bullet}{item}" for item in items)


def render_truth_md(grounding: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# TRUTH.md - {grounding['task_id']}")
    lines.append("")
    lines.append(GENERATED_BANNER)
    lines.append("")
    lines.append(f"**task_id**: `{grounding['task_id']}`")
    lines.append(f"**family**: {grounding['family']}")
    lines.append("")

    lines.append("## Canary tokens")
    lines.append("")
    for tok in grounding.get("canary_tokens", []):
        lines.append(f"- `{tok}`")
    lines.append("")

    gt = grounding.get("golden_trajectory", {})
    lines.append("## Golden trajectory")
    lines.append("")
    lines.append(f"**reference_method_name**: {gt.get('reference_method_name', '')}")
    lines.append("")
    for step in gt.get("ordered_steps", []):
        lines.append(f"### Step {step['step']}")
        lines.append("")
        lines.append(f"**action**: {step['action']}")
        lines.append("")
        lines.append(f"**state**: {step['state']}")
        lines.append("")
        lines.append(f"**drift_survived**: {step['drift_survived']}")
        lines.append("")
        lines.append(f"**checker**: {step['checker']}")
        lines.append("")

    lines.append("## Near-miss routes")
    lines.append("")
    for nm in grounding.get("near_miss_routes", []):
        lines.append(f"- **route**: {nm['route']}")
        lines.append(f"  **rejection_reason**: {nm['rejection_reason']}")
        lines.append("")

    lines.append("## Lane reconciliation")
    lines.append("")
    for lr in grounding.get("lane_reconciliation", []):
        lines.append(f"### {lr['lane']}")
        lines.append("")
        lines.append(f"- satisfied_by_steps: {lr['satisfied_by_steps']}")
        lines.append(f"- detail: {lr['detail']}")
        lines.append("")

    lines.append("## Oracle reconciliation")
    lines.append("")
    orc = grounding.get("oracle_reconciliation", {})
    lines.append(f"- invoked_at: {orc.get('invoked_at', '')}")
    lines.append(f"- method: {orc.get('method', '')}")
    lines.append(f"- work_image_ref: `{orc.get('work_image_ref', '')}`")
    lines.append(f"- judge_image_ref: `{orc.get('judge_image_ref', '')}`")
    lines.append(f"- total_score_raw: {orc.get('total_score_raw', '')}")
    lines.append(f"- total_score_normalized: {orc.get('total_score_normalized', '')}")
    lines.append(f"- full_reward_threshold: {orc.get('full_reward_threshold', '')}")
    lines.append(f"- full_reward_reached: {orc.get('full_reward_reached', '')}")
    lines.append("")
    per_lane = orc.get("per_lane_measured", {})
    if per_lane:
        lines.append("### per_lane_measured")
        lines.append("")
        for lane_key, lane_val in per_lane.items():
            lines.append(f"- {lane_key}: {lane_val}")
        lines.append("")
    if orc.get("score_gap_analysis"):
        lines.append(f"**score_gap_analysis**: {orc['score_gap_analysis']}")
        lines.append("")

    return "\n".join(lines) + "\n"


def _walk_bundle_files(bundle_dir: Path) -> List[Path]:
    collected: List[Path] = []
    for root, dirs, files in os.walk(bundle_dir):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIR_NAMES)
        for name in sorted(files):
            if any(name.endswith(sfx) for sfx in EXCLUDE_FILE_SUFFIXES):
                continue
            candidate = Path(root) / name
            rel = candidate.relative_to(bundle_dir).as_posix()
            if rel in EXCLUDE_RELPATH_FILES:
                continue
            collected.append(candidate)
    collected.sort(key=lambda p: p.relative_to(bundle_dir).as_posix())
    return collected


def compute_canonical_content_hash(bundle_dir: Path) -> str:
    h = hashlib.sha256()
    for path in _walk_bundle_files(bundle_dir):
        rel = path.relative_to(bundle_dir).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\x00")
        h.update(path.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


def derive_bundle_uuid(canonical_hash: str) -> str:
    return str(uuid.uuid5(FORGE_TASK_NAMESPACE, canonical_hash))


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: recompute.py <bundle_dir>", file=sys.stderr)
        return 2
    bundle_dir = Path(argv[1]).resolve()
    grounding_path = bundle_dir / "solution" / "grounding.yaml"
    truth_path = bundle_dir / "solution" / "TRUTH.md"

    grounding = load_grounding(str(grounding_path))
    truth_md = render_truth_md(grounding)
    truth_path.write_text(truth_md, encoding="utf-8")
    rendered_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    canonical_hash = compute_canonical_content_hash(bundle_dir)
    bundle_uuid = derive_bundle_uuid(canonical_hash)

    report = {
        "bundle_dir": str(bundle_dir),
        "truth_md_rendered_at": rendered_at,
        "canonical_content_hash": canonical_hash,
        "bundle_uuid": bundle_uuid,
        "forge_task_namespace": str(FORGE_TASK_NAMESPACE),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
