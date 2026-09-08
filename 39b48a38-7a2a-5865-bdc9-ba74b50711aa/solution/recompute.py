"""Private recomputation script. Derives every generated canonical artifact in this bundle.

One source, `solution/grounding.yaml`, produces all of them:

  tests/harness/refimpl.py        the verifier's copy of the reference engine
  tests/grading.json              the configuration the verifier reads
  environment/public_probes/*     the public probe fixtures and their expected bytes
  solution/TRUTH.md               the generated ground truth
  solution/rubrics.json           the generated reference-based rubric
  tests/test_output.py            the deterministic tests compiled from that rubric
  solution/solve.sh               the oracle entry point
  solution/provenance.yaml        the per-unit provenance carrier

Because the oracle, the human readable truth, the rubric, and the compiled tests all
descend from one file, they cannot disagree with each other or with the fixtures.

This script invokes no model, no network, no clock, no locale, and no random source. Run it
twice under two host identities and the bytes agree.

Usage:
    python solution/recompute.py [--check]

`--check` regenerates into memory and reports drift without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import pathlib
import re
import sys

import yaml

BUNDLE = pathlib.Path(__file__).resolve().parents[1]
GROUNDING = BUNDLE / "solution" / "grounding.yaml"

CANARY_BEGIN = "CANARY-BLOCK-BEGIN"
CANARY_END = "CANARY-BLOCK-END"

# Bytes outside the identity domain. Rollout evidence must never change bundle identity,
# and the provenance binding block is applied after the hash by construction.
HASH_EXCLUDED = ("trajectories/", "solution/provenance.yaml", "solution/provenance.sig")


# ---------------------------------------------------------------------------
# canonical hashing under canary normalization
# ---------------------------------------------------------------------------


def placeholder(index: int, spec: dict) -> str:
    return spec["placeholder_template"].format(index=index)


# One designated slot. The value alone is substitutable; the label, the punctuation around
# it, and everything else on the line stay inside the hash domain. The optional quotes let
# one slot form serve both a plain-text carrier and a JSON one.
SLOT = re.compile(
    r'^(?P<pre>\s*"?canary_slot_(?P<idx>\d+)"?\s*:\s*"?)(?P<val>[A-Za-z0-9_\-]*)(?P<post>"?,?\s*)$'
)


def _rewrite_slots(text: str, value_for) -> str:
    """Rewrite every designated slot value between the block markers."""
    if CANARY_BEGIN not in text:
        return text
    out = []
    inside = False
    for line in text.splitlines(keepends=True):
        if CANARY_BEGIN in line:
            inside = True
            out.append(line)
            continue
        if CANARY_END in line:
            inside = False
            out.append(line)
            continue
        if inside:
            body = line.rstrip("\r\n")
            newline = line[len(body) :]
            match = SLOT.match(body)
            if match:
                index = int(match.group("idx"))
                out.append(
                    f"{match.group('pre')}{value_for(index)}{match.group('post')}{newline}"
                )
                continue
        out.append(line)
    return "".join(out)


def normalize_canaries(text: str, spec: dict) -> str:
    """Replace each designated slot value with its fixed public placeholder.

    Only the value inside a designated slot moves. Slot count, ordering, position, and
    every byte outside a slot stay inside the hash domain, so a token-shaped string
    somewhere else is ordinary content and is never normalized away.
    """
    return _rewrite_slots(text, lambda index: placeholder(index, spec))


def bundle_files(root: pathlib.Path) -> list[pathlib.Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) or rel == prefix for prefix in HASH_EXCLUDED):
            continue
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        files.append(path)
    return files


def canonical_content_hash(root: pathlib.Path, spec: dict) -> str:
    """Path-independent hash over every runtime-relevant byte, canary normalized."""
    digest = hashlib.sha256()
    for path in bundle_files(root):
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            body = raw
        else:
            body = normalize_canaries(text, spec).encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel.encode("utf-8"))
        digest.update(len(body).to_bytes(8, "big"))
        digest.update(body)
    return digest.hexdigest()


def derive_tokens(content_hash: str, spec: dict) -> list[str]:
    """A per-bundle token set, reproducible under frozen bytes and unique to the bundle."""
    key = bytes.fromhex(content_hash)
    tokens = []
    for index in range(spec["slot_count"]):
        message = f"{spec['normalization_domain_version']}:canary:{index}".encode("ascii")
        tokens.append("MEPH-" + hmac.new(key, message, hashlib.sha256).hexdigest()[:32])
    return tokens


def plant_tokens(text: str, tokens: list[str], spec: dict) -> str:
    return _rewrite_slots(text, lambda index: tokens[index])


def slot_values(text: str) -> dict[int, str]:
    """Every designated slot value in a carrier, for the conformance gate to check."""
    found: dict[int, str] = {}
    inside = False
    for line in text.splitlines():
        if CANARY_BEGIN in line:
            inside = True
            continue
        if CANARY_END in line:
            inside = False
            continue
        if inside:
            match = SLOT.match(line)
            if match:
                found[int(match.group("idx"))] = match.group("val")
    return found


# ---------------------------------------------------------------------------
# generators
# ---------------------------------------------------------------------------


def _reference():
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location(
        "reference_codec", BUNDLE / "solution" / "reference" / "codec.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gen_refimpl(g: dict) -> dict[str, str]:
    source = (BUNDLE / "solution" / "reference" / "codec.py").read_text(encoding="utf-8")
    header = (
        "# GENERATED SECTION. DO NOT HAND-EDIT.\n"
        "# Verbatim copy of solution/reference/codec.py, emitted by solution/recompute.py.\n"
        "# The verifier grades against these bytes, so the oracle and the checkers cannot\n"
        "# disagree about what the encoder does.\n"
    )
    return {"tests/harness/refimpl.py": header + source}


def gen_grading(g: dict) -> dict[str, str]:
    payload = {
        "_banner": "GENERATED SECTION. DO NOT HAND-EDIT. Source: solution/grounding.yaml",
        "format_revision": g["format_revision"],
        "reward_path": g["reward"]["path"],
        "submission_path": g["paths"]["submission"],
        "sealed_seed": g["sealed_seed"],
        "public_seed": g["public_seed"],
        "public_batch": g["batches"][0]["name"],
        "lanes": g["reward"]["lanes"],
        "gates": g["reward"]["gates"],
        "baselines": g["reward"]["baselines"],
        "denominator": g["reward"]["denominator"],
        "adversarial_count": g["adversarial_count"],
        "bonus_count": g["bonus_count"],
        "batches": g["batches"],
    }
    return {"tests/grading.json": json.dumps(payload, indent=2, sort_keys=True) + "\n"}


def gen_corpus(g: dict) -> dict[str, str]:
    sys.path.insert(0, str(BUNDLE / "tests"))
    from harness import workloads  # noqa: PLC0415

    reference = _reference()
    columns = workloads.columns(
        g["public_seed"].encode("ascii"), g["public_corpus_columns"], graded=False
    )
    out = [
        {
            "id": c["id"],
            "shape": c["shape"],
            "values": c["values"],
            "encoded_hex": reference.encode(c["values"]).hex(),
            "block_encodings": reference.block_choices(c["values"]),
        }
        for c in columns
    ]
    payload = {
        "_banner": "GENERATED SECTION. DO NOT HAND-EDIT. Source: solution/grounding.yaml",
        "note": "A sample of the encoder's behaviour, not a specification of it.",
        "count": len(out),
        "columns": out,
    }
    return {"environment/corpus/corpus.json": json.dumps(payload, indent=1) + "\n"}


def gen_truth(g: dict) -> dict[str, str]:
    spec = g["canary"]
    lines = ["# TRUTH", "", "GENERATED SECTION. DO NOT HAND-EDIT.", ""]
    lines.append("Source of truth: `solution/grounding.yaml`. Emitted by `solution/recompute.py`. Private artifact: never mounted into the agent image, and any byte of it on the agent-visible surface is a blocking defect.")
    lines.append("")
    lines.append(CANARY_BEGIN)
    for index in range(spec["slot_count"]):
        lines.append(f"canary_slot_{index}: {placeholder(index, spec)}")
    lines.append(CANARY_END)
    lines += ["", "## The rules that appear in no agent-visible byte", "",
              "| Id | Name | Rule | Bites on |", "|---|---|---|---|"]
    for rule in g["undocumented_rules"]:
        lines.append(f"| {rule['id']} | {rule['name']} | {' '.join(rule['rule'].split())} | {rule['bites_on']} |")
    lines += ["", "## The ordered path", "",
              "| Step | Action | Establishes | Survives | Checker |", "|---|---|---|---|---|"]
    for step in g["truth_steps"]:
        lines.append(
            f"| {step['id']} | {step['action']} | {' '.join(step['established'].split())} "
            f"| {' '.join(step['survives'].split())} | {step['checker']} |"
        )
    lines += ["", "## Rejected routes", "", "| Route | Control | Why it fails |", "|---|---|---|"]
    for route in g["rejected_routes"]:
        lines.append(f"| {route['route']} | {route['control']} | {' '.join(route['why'].split())} |")
    lines += ["", "## Reward", "",
              f"Denominator {g['reward']['denominator']}. A hundred points is not the ceiling.",
              "", "| Lane | Points |", "|---|---|"]
    for lane, weight in g["reward"]["lanes"].items():
        lines.append(f"| {lane} | {weight} |")
    lines += ["", " ".join(g["reward"]["denominator_rationale"].split()), "",
              " ".join(g["reward"]["publication_rule"].split()), ""]
    return {"solution/TRUTH.md": "\n".join(lines)}


def gen_rubrics(g: dict) -> dict[str, str]:
    spec = g["canary"]
    items = [
        {
            "id": i["id"], "dimension": i["dimension"], "weight": i["weight"],
            "evaluation_target": i["evaluation_target"],
            "criterion": " ".join(i["criterion"].split()),
            "judgment": i["judgment"], "evidence": i["evidence"], "mode": i["mode"],
        }
        for i in g["rubric_items"]
    ]
    payload = {
        "_banner": "GENERATED SECTION. DO NOT HAND-EDIT. Source: solution/grounding.yaml",
        "canary_block": (
            [CANARY_BEGIN]
            + [f"canary_slot_{i}: {placeholder(i, spec)}" for i in range(spec["slot_count"])]
            + [CANARY_END]
        ),
        "compiled_weight": round(sum(i["weight"] for i in items if i["mode"] == "compiled"), 6),
        "total_weight": round(sum(i["weight"] for i in items), 6),
        "evaluation_targets": sorted({i["evaluation_target"] for i in items}),
        "items": items,
    }
    return {"solution/rubrics.json": json.dumps(payload, indent=2, sort_keys=True) + "\n"}


def gen_test_output(g: dict) -> dict[str, str]:
    """Compile every deterministically reducible rubric item into a test.

    Each test asserts over the report the scorer actually emits: a lane earns its full points
    or the item fails. The compiled test carries the relation alone, never criterion prose and
    never reference text, because tests/ travels with the bundle.
    """
    lines = [
        '"""Compiled rubric tests. GENERATED SECTION. DO NOT HAND-EDIT.',
        "",
        "Source: solution/grounding.yaml through solution/recompute.py.",
        '"""',
        "",
        "import json",
        "import pathlib",
        "",
        "import pytest",
        "",
        'REPORT = pathlib.Path("/logs/verifier/report.json")',
        "",
        "",
        "@pytest.fixture(scope='module')",
        "def report():",
        "    if not REPORT.exists():",
        "        pytest.skip('verifier report absent')",
        "    return json.loads(REPORT.read_text())",
        "",
        "",
        "def _full(report, lane):",
        "    maxima = report.get('lane_maxima', {})",
        "    points = report.get('points', {})",
        "    if lane not in maxima:",
        "        return False",
        "    return abs(points.get(lane, 0.0) - maxima[lane]) < 1e-6",
        "",
        "",
        "def _gate(report, lane):",
        "    entry = report.get('lanes', {}).get(lane)",
        "    if not isinstance(entry, dict) or 'passed' not in entry:",
        "        return False",
        "    return bool(entry['passed'])",
        "",
    ]
    for item in g["rubric_items"]:
        if item["mode"] != "compiled":
            continue
        lane = item["evidence"][0]
        lines.append("")
        lines.append(f"def test_{item['id'].lower()}(report):")
        if lane == "RL1":
            lines.append("    assert not report.get('red_line')")
        elif lane in g["reward"]["gates"]:
            # A gate lane carries zero weight, so asserting it earned its maximum would
            # compare zero against zero and hold for every submission ever written. The
            # relation that still has content is whether the gate was cleared.
            lines.append(f"    assert _gate(report, {lane!r})")
        else:
            lines.append(f"    assert _full(report, {lane!r})")
    lines.append("")
    return {"tests/test_output.py": "\n".join(lines)}


def gen_solve(g: dict) -> dict[str, str]:
    return {"solution/solve.sh": (
        "#!/usr/bin/env bash\n"
        "# GENERATED SECTION. DO NOT HAND-EDIT. Source: solution/grounding.yaml\n"
        "set -euo pipefail\n\n"
        f"target=\"{g['paths']['submission']}\"\n"
        "mkdir -p \"$(dirname \"${target}\")\"\n"
        "cp /solution/reference/codec.py \"${target}\"\n"
        "echo \"oracle installed reference codec at ${target}\"\n"
    )}


GENERATORS = (gen_refimpl, gen_grading, gen_corpus, gen_truth, gen_rubrics, gen_test_output, gen_solve)


def gen_provenance(g: dict, content_hash: str, uuid: str) -> str:
    payload = {
        "_banner": "GENERATED SECTION. DO NOT HAND-EDIT. Source: solution/grounding.yaml",
        "schema_version": "1",
        "task_id": g["task_id"],
        "bundle_uuid": uuid,
        "canary_normalization_domain_version": g["canary"]["normalization_domain_version"],
        "upstream_provenance": {
            "origin": "original",
            "provenance_date": "2026-08-12",
            "upstream_identity": None,
            "license": "project-owned",
            "modifications": None,
            "source": {
                "source_kind": "synthetic",
                "generator_identity": "mephisto.forge.chronopack",
                "generation_inputs_digest": hashlib.sha256(GROUNDING.read_bytes()).hexdigest(),
                "canonical_repository_identity": None,
                "fork_ancestry_snapshot_digest": None,
                "base_commit_sha": None,
                "task_generating_event_timestamp": "2026-08-12T00:00:00Z",
                "ancestry_attestation_digest": None,
                "ancestry_attestation_signer": None,
                "event_attestation_digest": None,
                "event_attestation_signer": None,
                "attestation_status": "attestation-unavailable",
            },
        },
        "screening_roots": {
            "exclusion_list": {"root_identity": "mephisto.exclusion-list", "content_digest": "6ce0b70292a2238202708f6c396edf56308264437eb30d1bdd6604d29a289c56"},
            "freeze_date_table": {"root_identity": "mephisto.freeze-date-table", "content_digest": "98d7b4be261633453c13eaebba04ca13b29888e4e298750f97fdef86147c04ec"},
            "neardup_index": {"root_identity": "mephisto.neardup-index", "content_digest": "b461a9c87c38afa30b211ff85716baf612f5630985ff031cd6ff4b562cb95460"},
            "source_attestation": {"root_identity": "mephisto.source-attestation-trust-root", "content_digest": "726647ade219fe466b078f2b7424a26e7bf9d81beed394d79c64b5ff92a0e672"},
        },
        "screening_measured_at": "2026-08-12T00:00:00Z",
        "screening_interval_days": 90,
        "screening_expires_at": "2026-11-10T00:00:00Z",
        "producer_claim_note": (
            "Every outcome recorded here is a producer claim rather than evidence. A reader "
            "recomputes it from the committed bytes and the named roots."
        ),
        "binding": {"canonical_bundle_hash": content_hash, "pinned_image_digest": None, "binding_envelope": None},
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args()

    g = yaml.safe_load(GROUNDING.read_text(encoding="utf-8"))
    spec = g["canary"]

    generated: dict[str, str] = {}
    for generator in GENERATORS:
        generated.update(generator(g))

    drift = []
    for rel, text in sorted(generated.items()):
        path = BUNDLE / rel
        current = path.read_text(encoding="utf-8") if path.exists() else None
        # Compare under canary normalization, because planted tokens are derived from the
        # hash of the normalized bytes and a generator emits placeholders by construction.
        if current is None or normalize_canaries(current, spec) != normalize_canaries(text, spec):
            drift.append(rel)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Generators emit placeholders. Planting happens after the hash, below.
            path.write_text(text, encoding="utf-8")

    if args.check:
        print(json.dumps({"drift": drift}, indent=2))
        return 1 if drift else 0

    content_hash = canonical_content_hash(BUNDLE, spec)
    tokens = derive_tokens(content_hash, spec)

    # Plant only into the declared carriers. A file that merely mentions the block marker,
    # this script among them, is ordinary content and is never treated as a carrier.
    planted = []
    for rel in spec["carriers"]:
        path = BUNDLE / rel
        text = path.read_text(encoding="utf-8")
        if CANARY_BEGIN not in text:
            raise SystemExit(f"declared canary carrier {rel} has no canary block")
        path.write_text(plant_tokens(text, tokens, spec), encoding="utf-8")
        planted.append(rel)

    import uuid as _uuid  # noqa: PLC0415

    namespace = _uuid.UUID("c53e8f3b-526f-52c0-a04e-89e2269b237d")
    bundle_uuid = str(_uuid.uuid5(namespace, content_hash))

    (BUNDLE / "solution" / "provenance.yaml").write_text(
        gen_provenance(g, content_hash, bundle_uuid), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "canonical_content_hash": content_hash,
                "bundle_uuid": bundle_uuid,
                "generated": sorted(generated),
                "canary_carriers": sorted(planted),
                "drift_before_write": drift,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
